#!/usr/bin/env python3
"""Render kanata layers into display data for the layer overlay.

Reads ~/.config/kanata/config.kbd and produces, for every layer, a grid that
mirrors defsrc rows. Each cell carries the physical key and the label that key
produces on that layer (output chords resolved to glyphs for the `us` layout).

Used by layer-overlay.py (the watcher) and runnable on its own:

    ./layer_map.py              # everything
    ./layer_map.py sym          # one layer
    ./layer_map.py --json       # machine-readable dump
"""

from __future__ import annotations

import json
import os
import re
import sys

CONFIG = os.path.expanduser("~/.config/kanata/config.kbd")

# Physical key -> what it produces while shift is held (us layout).
SHIFTED = {
    "grv": "~", "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")", "-": "_", "=": "+",
    "[": "{", "]": "}", "\\": "|", ";": ":", "'": '"', ",": "<", ".": ">",
    "/": "?", "`": "~",
}

NAMED = {
    "spc": "Space", "ret": "⏎", "esc": "Esc", "bspc": "⌫", "tab": "Tab",
    "del": "Del", "caps": "Caps", "up": "↑", "down": "↓", "left": "←",
    "right": "→", "home": "Home", "end": "End", "pgup": "PgUp", "pgdn": "PgDn",
    "grv": "`", "lmet": "Super", "rmet": "Super", "lalt": "Alt", "ralt": "Alt",
    "lctl": "Ctrl", "rctl": "Ctrl", "lsft": "Shift", "rsft": "Shift",
}

# Physical key labels under each cell: what is printed on the key, lowercase.
PHYS = {
    "spc": "space", "ret": "enter", "bspc": "bksp", "grv": "`", "esc": "esc",
    "tab": "tab", "caps": "caps", "lalt": "alt", "ralt": "alt",
    "lctl": "ctrl", "rctl": "ctrl", "lsft": "shift", "rsft": "shift",
    "lmet": "super", "rmet": "super", "up": "↑", "down": "↓", "left": "←",
    "right": "→",
}

MOD_KEYS = {
    "lsft": "⇧", "rsft": "⇧", "lctl": "⌃", "rctl": "⌃",
    "lalt": "⌥", "ralt": "⌥", "lmet": "⌘", "rmet": "⌘",
}

# Longest first so RC- is not read as C- followed by "R".
MOD_PREFIXES = [
    ("RC-", "⌃"), ("RS-", "⇧"), ("RA-", "⌥"), ("RM-", "⌘"), ("AG-", "⌥"),
    ("C-", "⌃"), ("S-", "⇧"), ("A-", "⌥"), ("M-", "⌘"),
]
MOD_GLYPH = {"C-": "⌃", "S-": "⇧", "A-": "⌥", "M-": "⌘"}


def tokens_with_lines(text):
    """Yield (token, line_number). Nested lists come back as raw strings."""
    i, line = 0, 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        if text.startswith(";;", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "(":
            depth, j = 1, i + 1
            while j < n and depth:
                if text.startswith(";;", j):
                    k = text.find("\n", j)
                    j = n if k < 0 else k
                    continue
                if text[j] == '"':
                    j += 1
                    while j < n and text[j] != '"':
                        j += 2 if text[j] == "\\" else 1
                elif text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                j += 1
            yield text[i:j], line
            line += text.count("\n", i, j)
            i = j
            continue
        if c == ")":
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j += 1
            yield text[i:j], line
            i = j
            continue
        j = i
        while j < n and not text[j].isspace() and text[j] not in "()":
            j += 1
        yield text[i:j], line
        i = j


def parse_form(raw):
    """Parse one (possibly nested) raw form into str/list."""
    s = raw.strip()
    if not s.startswith("("):
        return s
    out, stack, i, n = [], [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
        elif s.startswith(";;", i):
            j = s.find("\n", i)
            i = n if j < 0 else j
        elif c == "(":
            stack.append([])
            i += 1
        elif c == ")":
            done = stack.pop()
            if stack:
                stack[-1].append(done)
            else:
                out.append(done)
            i += 1
        elif c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            j += 1
            stack[-1].append(s[i:j])
            i = j
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in "()":
                j += 1
            stack[-1].append(s[i:j])
            i = j
    return out[0] if len(out) == 1 else out


def read_blocks(text):
    """Split the file into {head-token: [forms]} using top-level parens."""
    blocks, current = {}, None
    for token, _ in tokens_with_lines(text):
        if not token.startswith("("):
            continue
        form = parse_form(token)
        if not isinstance(form, list) or not form:
            continue
        head = form[0]
        blocks.setdefault(head, []).append(form)
    return blocks


def block_rows(text, head, name=None):
    """Rows of a (defsrc ...) / (deflayer <name> ...) block, by source line."""
    start = re.compile(
        r"^\s*\(" + head + r"\b" + (r"\s+" + re.escape(name) + r"\b" if name else ""),
        re.M,
    )
    match = None
    for match in start.finditer(text):
        pass
    if match is None:
        return []
    pos = text.index("(", match.start())
    depth, i, n = 0, pos, len(text)
    while i < n:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = text[pos + 1:i]
    tokens = list(tokens_with_lines(body))
    # Drop the header: "defsrc" or "deflayer" plus the layer name.
    header = [head] + ([name] if name else [])
    while tokens and tokens[0][0] in header:
        tokens.pop(0)
    rows = {}
    for token, line in tokens:
        rows.setdefault(line, []).append(token)
    return [rows[k] for k in sorted(rows)]


def shift_glyph(key):
    if key in SHIFTED:
        return SHIFTED[key]
    if len(key) == 1 and key.isalpha():
        return key.upper()
    return None


def pretty_key(key):
    if key in NAMED:
        return NAMED[key]
    if len(key) == 1:
        return key.upper() if key.isalpha() else key
    return key


def pretty(form, aliases, depth=0):
    if depth > 8:
        return "…"
    if isinstance(form, list):
        if not form:
            return ""
        head = form[0]
        args = form[1:]
        if head in ("tap-hold", "tap-hold-press", "tap-hold-release", "tap-hold-release-keys"):
            # (tap-hold <t1> <t2> <tap-action> <hold-action>)
            tap = pretty(args[2], aliases, depth + 1) if len(args) > 2 else ""
            hold = pretty(args[3], aliases, depth + 1) if len(args) > 3 else ""
            return f"{tap}/{hold}" if hold else tap
        if head in ("layer-while-held", "layer-toggle"):
            return "⇧" + str(args[0]) if args else ""
        if head == "layer-switch":
            return "→" + str(args[0]) if args else ""
        if head == "multi":
            parts = []
            for a in args:
                if isinstance(a, str) and a in MOD_KEYS:
                    parts.append(MOD_KEYS[a])
                else:
                    parts.append(pretty(a, aliases, depth + 1))
            return "".join(p for p in parts if p)
        if head == "unicode" and args:
            return str(args[0]).strip('"')
        if head == "release-key" and args:
            return "↑" + pretty(args[0], aliases, depth + 1)
        if head == "release-layer" and args:
            return "↑" + str(args[0])
        if head in ("macro", "macro-repeat", "macro-release-cancel"):
            return "macro"
        if head == "cmd" or head == "cmd-log":
            return "cmd"
        return str(head)
    token = form
    if token == "_":
        return ""
    if token in ("XX", "✗", "∅", "•"):
        return "∅"
    if token.startswith("@"):
        name = token[1:]
        return pretty(aliases[name], aliases, depth + 1) if name in aliases else token
    mods = []
    rest = token
    changed = True
    while changed:
        changed = False
        for prefix, glyph in MOD_PREFIXES:
            if rest.startswith(prefix) and len(rest) > len(prefix):
                mods.append(glyph)
                rest = rest[len(prefix):]
                changed = True
                break
    if not mods:
        return pretty_key(token)
    if "⇧" in mods and len(mods) == 1:
        glyph = shift_glyph(rest)
        if glyph is not None:
            return glyph
    order = {"⌃": 0, "⇧": 1, "⌥": 2, "⌘": 3}
    mods = sorted(mods, key=lambda m: order.get(m, 9))
    return "".join(mods) + pretty_key(rest)


def load(path=CONFIG):
    text = open(path, encoding="utf-8").read()
    blocks = read_blocks(text)

    aliases = {}
    for block in blocks.get("defalias", []):
        pairs = block[1:]
        for i in range(0, len(pairs) - 1, 2):
            aliases[str(pairs[i])] = pairs[i + 1]

    src_rows = block_rows(text, "defsrc")
    layers = {}
    for block in blocks.get("deflayer", []):
        if len(block) < 2:
            continue
        name = str(block[1])
        rows = block_rows(text, "deflayer", name)
        rows = [r for r in rows if r]
        if not src_rows:
            continue
        grid = []
        for r, src_row in enumerate(src_rows):
            layer_row = rows[r] if r < len(rows) else []
            cells = []
            for c, key in enumerate(src_row):
                action = layer_row[c] if c < len(layer_row) else "_"
                label = pretty(parse_form(action), aliases)
                cells.append({"key": PHYS.get(key, key), "out": label or ""})
            grid.append(cells)
        layers[name] = {"name": name, "rows": grid}

    # Transparent cells (_) do not fall to the OS directly — they fall to
    # the layer below in the active stack. num sits on base (blank = the
    # physical key), and sym is only ever entered from num (rctl, then
    # lalt), so resolve sym's blanks against num. Alpha rows only: the
    # thumb row keeps its raw labels (that is where you switch layers).
    def key_glyph(r, c):
        return pretty_key(src_rows[r][c])

    def resolve(name, under_name):
        if name not in layers or under_name not in layers:
            return
        under = layers[under_name]["rows"]
        for r, row in enumerate(layers[name]["rows"][:3]):
            for c, cell in enumerate(row):
                if cell["out"]:
                    continue
                if r < len(under) and c < len(under[r]) and under[r][c]["out"]:
                    cell["out"] = under[r][c]["out"]
                else:
                    cell["out"] = key_glyph(r, c)

    resolve("num", "base")  # base labels are blank → physical key glyph
    resolve("sym", "num")   # after num is resolved
    return layers


def main(argv):
    layers = load()
    if "--json" in argv:
        print(json.dumps(layers, ensure_ascii=False))
        return 0
    wanted = [a for a in argv if not a.startswith("-")] or list(layers)
    for name in wanted:
        layer = layers.get(name)
        if not layer:
            print(f"unknown layer: {name}", file=sys.stderr)
            continue
        print(f"\n[{name}]")
        for row in layer["rows"]:
            print("  ".join(f"{c['out'] or '·':>3}" for c in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
