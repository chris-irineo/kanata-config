#!/usr/bin/env python3
"""Report from keylog aggregates: what you actually press, how fast,
and how that compares to the current num/sym layers.

Usage:
  analyze.py [--config ~/.config/kanata/config.kbd]
             [--state  ~/.local/state/kanata-keylog/aggregates.json]

Sections
  1. Totals + machine-filter sanity (voxtype leak check)
  2. Top keys by count (with typing-speed gap profile)
  3. Symbols + digits, ranked, with friction (slow-gap share)
  4. Bigrams involving symbols/digits — pairs worth one-hold rolls
  5. Modifier chords + named keys (word jumps, tab, pgup/pgdn...)
  6. Per-window-context top symbols (code vs prose vs shell)
  7. Layer audit: current num/sym slots vs logged usage

Friction metric: gaps are dominated by pauses (thinking, reading), so
"fast fraction" (share of gaps <200ms — real typing speed) is the
honest signal; mean gap alone is not.
"""

import argparse
import json
import math
import os
import sys

import keylog  # shared keycode tables / repr logic — single source of truth

# kanata key names not matching the evdev-derived tables
KANATA_EXTRA_NAMES = {"grv": 41}

NAME_TO_CODE = {}
for code, (lo, hi) in keylog.CHARS.items():
    NAME_TO_CODE.setdefault(lo, code)
for code, name in keylog.NAMED.items():
    NAME_TO_CODE.setdefault(name, code)
NAME_TO_CODE.update(KANATA_EXTRA_NAMES)

FAST_MS = 200.0  # "typing speed" threshold for the fast fraction


# ── Layer parsing (config.kbd) ────────────────────────────────────────────
def layer_rows(text, header):
    """Rows (token lists) of a `(defsrc` / `(deflayer <name>` block.
    Row structure comes from the file's physical lines — that is how
    the config is written (one matrix row per line)."""
    rows, started = [], False
    for line in text.splitlines():
        code = line.split(";;")[0].strip()
        if not started:
            if code.startswith("(" + header):
                started = True
            continue
        if code == ")":
            break
        toks = code.split()
        if toks and toks[-1] == ")":
            toks = toks[:-1]
        if toks:
            rows.append(toks)
    return rows


def token_outputs(token):
    """kanata deflayer token -> (label, [logger reprs it produces]).
    Transparent (_) and alias (@x) slots return a label, no reprs.
    Mod prefixes are stripped one at a time so "S--" (shift+minus,
    underscore) survives the dash splitting."""
    if token == "_":
        return ("(transparent)", [])
    if token.startswith("@"):
        return ("(alias " + token[1:] + ")", [])
    mod_letters = []
    rest = token
    while True:
        if rest[:2] in ("S-", "C-", "M-", "A-"):
            mod_letters.append(rest[0])
            rest = rest[2:]
        else:
            break
    code = NAME_TO_CODE.get(rest)
    if code is None:
        return (token, [])
    mods = ("C" in mod_letters, "M" in mod_letters, "A" in mod_letters,
            "S" in mod_letters)
    r = keylog.key_repr(code, mods)
    return (token, [r] if r else [])


def parse_layers(config_path):
    """[(layer_name, [(position_label, token, label, reprs)])] for the
    layers that matter to the sym/num redesign."""
    with open(config_path, encoding="utf-8") as f:
        text = f.read()
    src_rows = layer_rows(text, "defsrc")
    out = []
    for layer in ("num", "sym"):
        rows = layer_rows(text, "deflayer " + layer)
        if not rows:
            continue
        slots = []
        for src, lay in zip(src_rows, rows):
            if len(src) != len(lay):
                print("warning: %s row width mismatch (%s vs %s) — skipping row"
                      % (layer, len(src), len(lay)), file=sys.stderr)
                continue
            for pos, tok in zip(src, lay):
                label, reprs = token_outputs(tok)
                slots.append((pos, tok, label, reprs))
        out.append((layer, slots))
    return out


# ── Formatting helpers ───────────────────────────────────────────────────
def fmt_stats(st):
    n, tot, totsq = st[0], st[1], st[2]
    if not n:
        return "—"
    mean = tot / n
    sd = math.sqrt(max(0.0, totsq / n - mean * mean))
    return "%6.0f±%.0f" % (mean, sd)


def fast_fraction(st):
    n = st[0]
    if not n:
        return 0.0
    return sum(st[5][:3]) / n  # gaps < 50, <100, <200ms


def is_symbol(r):
    return len(r) == 1 and not r.isalnum()


def is_digit(r):
    return len(r) == 1 and r.isdigit()


def pct(x):
    return "%.1f%%" % (100.0 * x)


def bar(frac, width=10):
    return ("#" * int(round(frac * width))).ljust(width)


# ── Sections ─────────────────────────────────────────────────────────────
def sec_meta(data, out):
    m = data["meta"]
    days = max(0.02, (m["flushed"] - m["started"]) / 86400.0)
    out.append("## 1. Coverage\n")
    out.append("- device: `%s`" % m["device"])
    out.append("- span: %.1f days (%s → %s)"
               % (days, time_str(m["started"]), time_str(m["flushed"])))
    out.append("- presses counted: %d (%d/day), machine-filtered: %d"
               % (m["total_presses"], m["total_presses"] / days, m["filtered_presses"]))
    out.append("- machine-filter sanity: 0 filtered means no dictation/other "
               "injections flowed through kanata (expected for voxtype/ydotool). "
               "A large number means we caught injections — counts stay clean.")
    out.append("")


def top_table(keys, out, title, ranked, n=40):
    out.append("## %s\n" % title)
    out.append("| rank | key | count | share | mean±sd gap (ms) | fast(<200ms) |")
    out.append("|---:|:--|---:|---:|---:|:--|")
    total = sum(st[0] for st in keys.values())
    for i, (r, st) in enumerate(ranked[:n], 1):
        out.append("| %d | `%s` | %d | %s | %s | %s |"
                   % (i, r, st[0], pct(st[0] / total), fmt_stats(st),
                      pct(fast_fraction(st)) + " " + bar(fast_fraction(st))))
    out.append("")


def sec_bigrams(data, out):
    keys = data["keys"]
    total = sum(st[0] for st in keys.values()) or 1
    pairs = []
    for pair, (n, tot) in data["bigrams"].items():
        a, b = pair.split("\x1f")
        if is_symbol(a) or is_symbol(b) or is_digit(a) or is_digit(b):
            pairs.append((n, tot, a, b))
    pairs.sort(key=lambda x: -x[0])
    out.append("## 4. Symbol/digit bigrams — pairs worth one-hold rolls\n")
    out.append("| count | pair | share of all presses | mean gap |")
    out.append("|---:|:--|---:|---:|")
    for n, tot, a, b in pairs[:30]:
        out.append("| %d | `%s%s` | %s | %.0f ms |"
                   % (n, a, b, pct(2 * n / total), tot / n))
    slow = [p for p in pairs if p[0] >= 10]
    slow.sort(key=lambda x: -x[1] / x[0])
    out.append("\nSlowest (n≥10) — friction candidates for relocation:\n")
    for n, tot, a, b in slow[:15]:
        out.append("- `%s%s` — %.0f ms avg (%d)" % (a, b, tot / n, n))
    out.append("")


def sec_contexts(data, out):
    buckets = sorted(data["buckets"].items(),
                     key=lambda kv: -kv[1]["total"])[:8]
    out.append("## 6. Per-window-context top symbols/digits\n")
    for name, b in buckets:
        if name == "__overflow__":
            continue
        syms = [(r, c) for r, c in b["keys"].items()
                if is_symbol(r) or is_digit(r)]
        syms.sort(key=lambda x: -x[1])
        top = " ".join("`%s`×%d" % (r, c) for r, c in syms[:12])
        out.append("- **%s** — %d presses: %s" % (name, b["total"], top))
    out.append("")


def sec_layers(data, config_path, out):
    keys = data["keys"]
    layers = parse_layers(config_path)
    sym_rank = {}
    ranked_syms = sorted(
        ((r, st[0]) for r, st in keys.items() if is_symbol(r) or is_digit(r)),
        key=lambda x: -x[1])
    for i, (r, _) in enumerate(ranked_syms, 1):
        sym_rank[r] = i
    n_syms = len(ranked_syms) or 1

    # where each char currently lives
    home = {}
    for layer_name, slots in layers:
        for pos, tok, label, reprs in slots:
            for r in reprs:
                home.setdefault(r, []).append("%s@%s" % (layer_name, pos))
    def home_label(r):
        if r in home:
            return " + ".join(home[r])
        for code, (lo, hi) in keylog.CHARS.items():
            if hi == r or lo == r:
                return "base %s%s (physical row)" % ("shift+" if hi == r else "", lo)
        return "unreachable"

    out.append("## 7. Layer audit — current num/sym slots vs usage\n")
    for layer_name, slots in layers:
        out.append("### %s layer\n" % layer_name)
        out.append("| pos | key | produces | logged | symbol rank |")
        out.append("|:--|:--|:--|---:|:--|")
        for pos, tok, label, reprs in slots:
            if not reprs:
                out.append("| %s | %s | %s | — | — |" % (pos, tok, label))
                continue
            r = reprs[0]
            st = keys.get(r)
            logged = st[0] if st else 0
            rank = sym_rank.get(r)
            rank_s = ("%d/%d" % (rank, n_syms)) if rank else "—"
            out.append("| %s | %s | `%s` | %d | %s |" % (pos, tok, r, logged, rank_s))
        out.append("")

    out.append("### Top 25 symbols/digits — and where they live now\n")
    out.append("| rank | char | count | fast | current home |")
    out.append("|---:|:--|---:|---:|:--|")
    for i, (r, c) in enumerate(ranked_syms[:25], 1):
        st = keys.get(r)
        out.append("| %d | `%s` | %d | %s | %s |"
                   % (i, r, c,
                      pct(fast_fraction(st)) if st else "—",
                      home_label(r)))
    out.append("")
    # prime slots wasted on rare keys; digits exempt (mnemonic order is
    # a deliberate policy, not a placement mistake to flag)
    out.append("### Demotion candidates — prime slots holding rare keys\n")
    prime = set("qwertyuiopasdfghjkl")
    for layer_name, slots in layers:
        for pos, tok, label, reprs in slots:
            if not reprs or is_digit(reprs[0]) or pos not in prime:
                continue
            r = reprs[0]
            if not is_symbol(r):  # hjkl arrows etc. are design, not waste
                continue
            st = keys.get(r)
            c = st[0] if st else 0
            if sym_rank.get(r, 10 ** 9) > 40:
                out.append("- %s@%s produces `%s` (%d uses, rank %s)"
                           % (layer_name, pos, r, c,
                              sym_rank.get(r, "unused")))
    out.append("")


def time_str(ts):
    import time
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config",
                    default=os.path.expanduser("~/.config/kanata/config.kbd"))
    ap.add_argument("--state",
                    default=os.path.join(keylog.STATE_DIR, "aggregates.json"))
    args = ap.parse_args()

    with open(args.state, encoding="utf-8") as f:
        data = json.load(f)
    keys = data["keys"]

    out = []
    sec_meta(data, out)

    ranked = sorted(keys.items(), key=lambda kv: -kv[1][0])
    top_table(keys, out, "2. Top keys", ranked)

    syms = [(r, st) for r, st in ranked if is_symbol(r)]
    digs = [(r, st) for r, st in ranked if is_digit(r)]
    top_table(keys, out, "3a. Symbols (friction = low fast-share)",
              syms, n=35)
    top_table(keys, out, "3b. Digits", digs, n=10)

    sec_bigrams(data, out)

    chords = [(r, st) for r, st in ranked
              if r[:2] in ("C-", "M-", "A-") or r[:4] in ("C-S-", "M-S-", "A-S-")]
    named = [(r, st) for r, st in ranked
             if not is_symbol(r) and not is_digit(r) and not chords
             and not (len(r) == 1 and (r.isalpha() or r == "spc"))]
    top_table(keys, out, "5a. Modifier chords (app grammar)", chords, n=15)
    top_table(keys, out, "5b. Named keys (navigation, edits)", named, n=20)

    sec_contexts(data, out)

    if os.path.exists(args.config):
        sec_layers(data, args.config, out)
    else:
        out.append("## 7. Layer audit skipped — no config at %s\n" % args.config)

    print("\n".join(out))


if __name__ == "__main__":
    main()
