# keylog — aggregate-only usage logging for the sym/num redesign

Answers "what do I actually press?" with data instead of argument, to
redesign the `num` and `sym` layers in `../config.kbd` from a week of
real usage.

## Privacy model (the point — read before changing anything)

**No raw keystroke stream ever hits disk.** `keylog.py` keeps counts in
memory and flushes only aggregates to
`~/.local/state/kanata-keylog/aggregates.json` (0600):

- `keys` — per-key counts + inter-press gap stats (mean/±sd, histogram)
- `bigrams` — text-flow pairs `prev\x1fcur` (counts + gap sums)
- `buckets` — per-window counts keyed by `<class>/<first title word>`

What is *not* on disk: any sequence of keys, any timing of individual
keys, passwords, anything reconstructable. Purge with:

```bash
rm -rf ~/.local/state/kanata-keylog
```

## What it sees and doesn't

| Source | Visible? | Why |
|---|---|---|
| Typing through kanata (any layer, any keyboard) | yes | it watches kanata's uinput *output* |
| Editor autocompletion | no | editor-internal, never passes a key device |
| Dictation (voxtype via ydotool) | no | bypasses kanata via its own uinput device |
| voxtype clipboard fallback | one `C-v` | harmless; arguably honest usage |
| 1–2 char machine bursts | can leak | filter needs ≥3 machine-speed presses |

## Deploy (after merging this branch to main)

```bash
cp ~/.config/kanata/keylog/kanata-keylog.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kanata-keylog
```

Stop after the week: `systemctl --user stop kanata-keylog` (stop, not
disable, if you might resume). Then:

```bash
python3 ~/.config/kanata/keylog/analyze.py > /tmp/opencode/keylog-report.md
```

## Calibration (run once, before trusting the week)

1. **Key reconstruction** — in a terminal:

   ```bash
   python3 ~/.config/kanata/keylog/keylog.py --watch
   ```

   Type a few words, a symbol (`!`, `[`, `_`), a digit via `rctl`, a
   word-jump (`;`/`'` on num). Check each printed token matches what
   appeared in the terminal.

2. **Dictation bypass** — with `--watch` still running, toggle dictation
   (`spc`+`lalt`+`x`, i.e. SUPER+CTRL+X) and dictate a sentence. Expect:
   **nothing printed** (ydotool bypasses kanata). If the dictated text
   *does* print at machine speed, the burst filter still keeps it out of
   the aggregates — but tell the agent so it can investigate the path.

3. **App buckets** — while `--watch` runs, focus a different window and
   check the `[window] class/title` line changes.

`--watch` prints to stdout only; it never writes state.

## Design notes for whoever reads the aggregates

- **Fast fraction beats mean gap.** Gap distributions are dominated by
  thinking pauses; "share of gaps <200ms" isolates true typing speed.
  A symbol with high count AND low fast-share is a friction victim —
  promoted *despite* pain, top redesign priority.
- **Bigrams, not just frequency.** `=>`, `->`, `<=`, `!=`, `()` decide
  which symbols must sit next to each other (one-hold rolls).
- **Digits keep their mnemonic order** (`a..g`/`z..b` in digit order) —
  the data may argue otherwise; mnemonics win that one deliberately.
- The log measures output characters, not layer paths (output-only by
  decision, 2026-11-21). Layer-abandonment — silently falling back to
  the physical digit row — is *not* measured; if the week shows low
  digit counts on the layers but high digit usage overall, that gap is
  the abandonment signal.
