#!/usr/bin/env python3
"""Aggregate-only keylogger for kanata's uinput output device.

What this is
  A passive reader on the virtual device named "kanata" — the remap's
  FINAL output: what your fingers produce, regardless of which physical
  keyboard or layer path produced it. Dictation (voxtype via ydotool)
  and espanso-style injectors bypass kanata, so they are invisible
  here; editor autocompletion never passes through any key device.

Privacy design (deliberate — do not "simplify" by adding raw logging)
  NO raw keystroke stream is ever written to disk. Counts accumulate in
  memory and only aggregates are flushed (every 5 min + on exit):
    keys    : repr -> [n, sum_ms, sumsq_ms, min_ms, max_ms, hist7]
    bigrams : "prev\x1fcur" -> [n, sum_ms]   (text-flow pairs only)
    buckets : "<class>/<title-head>" -> {repr: n}   (Hyprland windows)
  Passwords may pass through memory, but nothing reconstructable hits
  disk. Purge everything with:  rm -rf ~/.local/state/kanata-keylog

Machine-typing filter
  A run of >=3 keypresses arriving <15ms apart is dropped before
  counting (voxtype types at 1ms/char via ydotool; humans bottom out
  around 20-30ms). The verdict for each keypress comes from the NEXT
  keypress's gap, so a burst's leading event is dropped too; a fast
  human roll of 2 (<15ms) commits intact. A 1-2 char machine burst can
  leak through — negligible. Verify the dictation path once with
  --watch (see keylog/README.md, Calibration).

Modes
  (none)      run the logger; flush aggregates every 5 min and on exit
  --watch     print reconstructed keys to stdout only (calibration)
  --selftest  synthetic-event tests; touches no devices
  --device P  read event device P ("/dev/input/eventN", or just "N")
"""

import glob
import json
import os
import select
import signal
import socket
import struct
import sys
import time

VERSION = 1
DEVICE_NAME = "kanata"
STATE_DIR = os.environ.get("KEYLOG_STATE_DIR") or os.path.expanduser(
    "~/.local/state/kanata-keylog"
)
FLUSH_SEC = 300.0
BURST_MS = 15.0  # inter-press gap below this = machine speed
BURST_K = 3      # >=3 consecutive fast presses confirms a burst
MAX_BUCKETS = 128
HIST_EDGES = (50, 100, 200, 500, 1000, 3000)  # ms; 7 buckets total

EV_KEY = 1
EVENT = struct.Struct("=qqHHI")  # input_event: sec, usec, type, code, value (64-bit)

# ── Key tables (US layout — kanata emits US keycodes) ────────────────────
CHARS = {
    2: ("1", "!"), 3: ("2", "@"), 4: ("3", "#"), 5: ("4", "$"), 6: ("5", "%"),
    7: ("6", "^"), 8: ("7", "&"), 9: ("8", "*"), 10: ("9", "("), 11: ("0", ")"),
    12: ("-", "_"), 13: ("=", "+"),
    16: ("q", "Q"), 17: ("w", "W"), 18: ("e", "E"), 19: ("r", "R"), 20: ("t", "T"),
    21: ("y", "Y"), 22: ("u", "U"), 23: ("i", "I"), 24: ("o", "O"), 25: ("p", "P"),
    26: ("[", "{"), 27: ("]", "}"),
    30: ("a", "A"), 31: ("s", "S"), 32: ("d", "D"), 33: ("f", "F"), 34: ("g", "G"),
    35: ("h", "H"), 36: ("j", "J"), 37: ("k", "K"), 38: ("l", "L"),
    39: (";", ":"), 40: ("'", '"'), 41: ("`", "~"), 43: ("\\", "|"),
    44: ("z", "Z"), 45: ("x", "X"), 46: ("c", "C"), 47: ("v", "V"), 48: ("b", "B"),
    49: ("n", "N"), 50: ("m", "M"), 51: (",", "<"), 52: (".", ">"), 53: ("/", "?"),
    57: ("spc", "spc"),
    # keypad merged with the digit row: same design meaning
    71: ("7", None), 72: ("8", None), 73: ("9", None), 75: ("4", None),
    76: ("5", None), 77: ("6", None), 79: ("1", None), 80: ("2", None),
    81: ("3", None), 82: ("0", None), 83: (".", None),
}

NAMED = {
    1: "esc", 14: "bspc", 15: "tab", 28: "ret", 96: "ret", 58: "caps",
    59: "f1", 60: "f2", 61: "f3", 62: "f4", 63: "f5", 64: "f6",
    65: "f7", 66: "f8", 67: "f9", 68: "f10", 87: "f11", 88: "f12",
    102: "home", 103: "up", 104: "pgup", 105: "left", 106: "right",
    107: "end", 108: "down", 109: "pgdn", 110: "ins", 111: "del",
}

# Modifier keycodes -> tracked state tag. kanata's thumbs emit REAL
# modifier keycodes (lctl/lsft/lmet), so shortcut chords are visible.
MOD_CODES = {
    29: "C", 97: "C",    # lctrl / rctrl
    42: "S", 54: "S",    # lshift / rshift
    56: "A", 100: "A",   # lalt / ralt
    125: "M", 126: "M",  # lmeta / rmeta (Super on Omarchy)
}


def key_repr(code, mods):
    """Canonical repr for one keypress. Text keys render as characters
    (shift applied: "A", "!"); C-/M-/A- chords render as kanata-style
    tokens ("C-left", "C-S-a"). Bare modifier presses return None."""
    ctrl, meta, alt, shift = mods
    if code in MOD_CODES:
        return None
    chorded = ctrl or meta or alt
    entry = CHARS.get(code)
    if entry is not None:
        lo, hi = entry
        if not chorded:
            return hi if (shift and hi is not None) else lo
        parts = [p for p, on in (("C", ctrl), ("M", meta), ("A", alt), ("S", shift)) if on]
        return "-".join(parts) + "-" + lo
    name = NAMED.get(code) or ("k%d" % code)
    parts = [p for p, on in (("C", ctrl), ("M", meta), ("A", alt), ("S", shift)) if on]
    return ("-".join(parts) + "-" + name) if parts else name


def bucket_of(class_, title):
    """App context bucket: window class + first word of the title
    (terminals set the title to the running command; passwords never
    matter here — only the bucket NAME is stored, capped by caller)."""
    head = title.split(maxsplit=1)[0][:32] if title else ""
    if head:
        return class_ + "/" + head
    return class_ or "__nowindow__"


class Aggregator:
    """In-memory count tables + the machine-burst filter.

    Every keypress is held in `pending` until the NEXT keypress's gap
    gives its verdict: a human-speed gap commits the pending run; a
    <15ms run that reaches BURST_K is discarded as machine typing."""

    def __init__(self):
        self.keys = {}      # repr -> [n, sum, sumsq, min, max, hist7]
        self.bigrams = {}   # "prev\x1fcur" -> [n, sum]
        self.buckets = {}   # bucket -> {"total": n, "keys": {repr: n}}
        self.total = 0
        self.filtered = 0
        self.pending = []
        self.machine = False
        self.last_ts = None
        self.prev_commit = None  # (repr, ts_ms, text_flow)
        self.started = time.time()
        self.device = None

    def feed(self, repr_, ts_ms, bucket, text_flow):
        gap = (ts_ms - self.last_ts) if self.last_ts is not None else None
        self.last_ts = ts_ms
        if self.machine:
            if gap is not None and gap < BURST_MS:
                self.filtered += 1
                return
            self.machine = False  # human-speed key ends the burst
        ev = (repr_, ts_ms, bucket, text_flow)
        if gap is not None and gap < BURST_MS:
            self.pending.append(ev)
            if len(self.pending) >= BURST_K:
                self.filtered += len(self.pending)
                self.pending.clear()
                self.machine = True
        else:
            for e in self.pending:
                self._commit(*e)
            self.pending.clear()
            self.pending.append(ev)

    def _commit(self, repr_, ts_ms, bucket, text_flow):
        self.total += 1
        gap = None
        if self.prev_commit is not None:
            gap = ts_ms - self.prev_commit[1]
        st = self.keys.get(repr_)
        if st is None:
            st = self.keys[repr_] = [0, 0.0, 0.0, float("inf"), 0.0,
                                     [0] * (len(HIST_EDGES) + 1)]
        st[0] += 1
        if gap is not None:
            st[1] += gap
            st[2] += gap * gap
            st[3] = min(st[3], gap)
            st[4] = max(st[4], gap)
            for i, edge in enumerate(HIST_EDGES):
                if gap < edge:
                    st[5][i] += 1
                    break
            else:
                st[5][-1] += 1
        if text_flow and self.prev_commit and self.prev_commit[2]:
            pair = self.prev_commit[0] + "\x1f" + repr_
            bg = self.bigrams.get(pair)
            if bg is None:
                bg = self.bigrams[pair] = [0, 0.0]
            bg[0] += 1
            bg[1] += gap or 0.0
        b = self.buckets.get(bucket)
        if b is None and len(self.buckets) >= MAX_BUCKETS:
            bucket = "__overflow__"
            b = self.buckets.get(bucket)
        if b is None:
            b = self.buckets[bucket] = {"total": 0, "keys": {}}
        b["total"] += 1
        b["keys"][repr_] = b["keys"].get(repr_, 0) + 1
        self.prev_commit = (repr_, ts_ms, text_flow)

    def drain(self):
        # leftover pending at flush/exit: assume human
        for e in self.pending:
            self._commit(*e)
        self.pending.clear()

    def flush(self, path):
        self.drain()
        data = {
            "meta": {
                "version": VERSION,
                "started": self.started,
                "flushed": time.time(),
                "device": self.device,
                "total_presses": self.total,
                "filtered_presses": self.filtered,
            },
            "keys": self.keys,
            "bigrams": self.bigrams,
            "buckets": self.buckets,
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)  # atomic


# ── Device / context discovery ───────────────────────────────────────────
def find_device():
    """Locate kanata's uinput node by name (event number changes across
    reboots and kanata restarts, so discover at runtime, every time)."""
    try:
        with open("/proc/bus/input/devices", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    in_block = False
    for line in lines:
        if line.startswith("N: Name="):
            in_block = line == 'N: Name="%s"' % DEVICE_NAME
        elif in_block and line.startswith("H: Handlers="):
            for h in line.split("=", 1)[1].split():
                if h.startswith("event"):
                    return "/dev/input/" + h
    return None


def open_hypr_socket():
    """Subscribe to Hyprland's socket2 for activewindow events."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
    for sigdir in sorted(glob.glob(os.path.join(runtime, "hypr", "*"))):
        path = os.path.join(sigdir, ".socket2.sock")
        if not os.path.exists(path):
            continue
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            return s
        except OSError:
            continue
    return None


# ── Main loop ────────────────────────────────────────────────────────────
def run(watch, device_arg=None, state_path=None):
    stop = {"flag": False}

    def on_signal(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    os.umask(0o077)
    if not watch:
        os.makedirs(STATE_DIR, exist_ok=True)
        state_path = state_path or os.path.join(STATE_DIR, "aggregates.json")

    agg = None if watch else Aggregator()
    mods = {"C": 0, "M": 0, "A": 0, "S": 0}
    bucket = "__nohypr__"

    last_flush = time.monotonic()
    last_reconnect = 0.0
    dev_fd = None
    dev_buf = b""
    hypr = None
    hypr_buf = b""

    while not stop["flag"]:
        if dev_fd is None:
            path = device_arg if device_arg else find_device()
            if path:
                try:
                    dev_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    if agg:
                        agg.device = path
                    print("listening: %s" % path, file=sys.stderr)
                except OSError as e:
                    print("cannot open %s: %s" % (path, e), file=sys.stderr)
            if dev_fd is None:
                time.sleep(2.0)
                continue

        if hypr is None and time.monotonic() - last_reconnect > 30.0:
            last_reconnect = time.monotonic()
            hypr = open_hypr_socket()
            if hypr:
                hypr.setblocking(False)
                print("hyprland: window context tracking on", file=sys.stderr)

        fds = [dev_fd] + ([hypr.fileno()] if hypr else [])
        try:
            ready, _, _ = select.select(fds, [], [], 2.0)
        except InterruptedError:
            continue

        if hypr is not None and hypr.fileno() in ready:
            try:
                chunk = hypr.recv(4096)
            except (BlockingIOError, InterruptedError):
                chunk = None
            if chunk == b"":
                hypr.close()
                hypr = None
                hypr_buf = b""
            elif chunk:
                hypr_buf += chunk
                while b"\n" in hypr_buf:
                    line, hypr_buf = hypr_buf.split(b"\n", 1)
                    if line.startswith(b"activewindow>>"):
                        # class,title — the context we bucket by
                        payload = line[len(b"activewindow>>"):].decode(
                            "utf-8", "replace")
                        class_, _, title = payload.partition(",")
                        bucket = bucket_of(class_, title)
                        if watch:
                            print("  [window] %s" % bucket)
                    elif line.startswith(b"activewindowv2>>"):
                        # address only; "unknown" means no focus
                        payload = line[len(b"activewindowv2>>"):].decode(
                            "utf-8", "replace").strip()
                        if payload == "unknown":
                            bucket = "__nowindow__"

        if dev_fd in ready:
            chunk = None
            try:
                chunk = os.read(dev_fd, 65536)
            except (BlockingIOError, InterruptedError):
                pass
            except OSError as e:
                print("device read failed (%s); rediscovering" % e,
                      file=sys.stderr)
                os.close(dev_fd)
                dev_fd = None
                dev_buf = b""
                continue
            if chunk == b"":
                print("device vanished (kanata restart?); rediscovering",
                      file=sys.stderr)
                os.close(dev_fd)
                dev_fd = None
                dev_buf = b""
                continue
            dev_buf += chunk
            while len(dev_buf) >= EVENT.size:
                sec, usec, typ, code, val = EVENT.unpack_from(dev_buf)
                dev_buf = dev_buf[EVENT.size:]
                if typ != EV_KEY:
                    continue
                if code in MOD_CODES:
                    if val == 1:
                        mods[MOD_CODES[code]] += 1
                    elif val == 0:
                        mods[MOD_CODES[code]] = max(0, mods[MOD_CODES[code]] - 1)
                    continue
                if val != 1:  # ignore release and autorepeat
                    continue
                repr_ = key_repr(code, (mods["C"], mods["M"], mods["A"], mods["S"]))
                if repr_ is None:
                    continue
                ts_ms = sec * 1000.0 + usec / 1000.0
                text_flow = not (mods["C"] or mods["M"] or mods["A"])
                if watch:
                    print(repr_)
                else:
                    agg.feed(repr_, ts_ms, bucket, text_flow)

        if not watch and time.monotonic() - last_flush > FLUSH_SEC:
            agg.flush(state_path)
            last_flush = time.monotonic()

    if agg:
        agg.flush(state_path)
        print("flushed %d presses (%d filtered) -> %s"
              % (agg.total, agg.filtered, state_path), file=sys.stderr)


# ── Selftest (no devices touched) ────────────────────────────────────────
def selftest():
    ok = True

    def check(name, got, want):
        nonlocal ok
        if got != want:
            ok = False
        print("%-42s %-4s got=%r want=%r"
              % (name, "ok" if got == want else "FAIL", got, want))

    check("shift+2 -> !", key_repr(2, (0, 0, 0, 1)), "!")
    check("plain a", key_repr(30, (0, 0, 0, 0)), "a")
    check("ctrl+left", key_repr(105, (1, 0, 0, 0)), "C-left")
    check("shift+tab", key_repr(15, (0, 0, 0, 1)), "S-tab")
    check("meta+x (SUPER+x)", key_repr(45, (0, 1, 0, 0)), "M-x")
    check("ctrl+shift+a", key_repr(30, (1, 0, 0, 1)), "C-S-a")
    check("space", key_repr(57, (0, 0, 0, 0)), "spc")
    check("bucket: class+title head", bucket_of("foot", "nvim ~/proj main.go"),
          "foot/nvim")

    agg = Aggregator()
    t = 1000.0
    for r in ("a", "spc", "b", "!"):
        agg.feed(r, t, "foot/vim", True)
        t += 120.0
    agg.drain()
    check("typing: total", agg.total, 4)
    check("typing: '!' counted", agg.keys["!"][0], 1)
    check("bigram a->spc", agg.bigrams.get("a\x1fspc", [0])[0], 1)
    check("bigram spc->b", agg.bigrams.get("spc\x1fb", [0])[0], 1)
    check("bucket total", agg.buckets["foot/vim"]["total"], 4)

    # machine burst: 12 chars at 1ms (voxtype speed) after human typing
    agg = Aggregator()
    t = 1000.0
    agg.feed("h", t, "x", True)
    t += 100.0
    for _ in range(12):
        agg.feed("q", t, "x", True)
        t += 1.0
    t += 400.0
    agg.feed("w", t, "x", True)
    agg.drain()
    check("burst: 12 filtered", agg.filtered, 12)
    check("burst: only h and w committed", agg.total, 2)

    # fast human roll of 2 (<15ms) commits intact
    agg = Aggregator()
    t = 1000.0
    agg.feed("d", t, "x", True)
    t += 500.0
    agg.feed("f", t, "x", True)
    t += 8.0
    agg.feed("g", t, "x", True)
    t += 400.0
    agg.feed("h", t, "x", True)
    agg.drain()
    check("fast roll: commits intact", agg.total, 4)
    check("fast roll: nothing filtered", agg.filtered, 0)

    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    watch = "--watch" in args
    device = None
    if "--device" in args:
        val = args[args.index("--device") + 1]
        device = val if val.startswith("/dev/") else "/dev/input/" + val
    run(watch, device)


if __name__ == "__main__":
    main()
