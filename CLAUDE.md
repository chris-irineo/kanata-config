# Kanata Configuration — agent notes

## Ground truth

**Two files define the whole input system:**

1. `~/.config/kanata/config.kbd` — the remap (this repo)
2. `~/.config/hypr/bindings.lua` — Omarchy keybinds that the remap targets

Never edit anything else: `archive/` is frozen history, and the `*.conf` files in
`~/.config/hypr/` are dead pre-quattro leftovers (Hyprland loads `hyprland.lua`,
which `require`s `bindings.lua`).

- Git repo = this directory (remote: `chriskevini/kanata-config`, branch `main`)
- Hardware: split keyboard (QMK/Vial), hence the 100ms chord timeout
- Service: `~/.config/systemd/user/kanata.service`, started with
  `--cfg ~/.config/kanata/config.kbd` and `--port 127.0.0.1:7070` (layer overlay
  watcher). The overlay card content renders from `config.kbd` at show time.
  No debounce by default (`num`/`sym` are deliberate); layers mapping fewer
  than `MIN_MAPPED` (3) keys are skipped, which is what keeps the thin `sft`
  and `ctl` layers from flashing a card.

## Architecture (do not "fix" into layers)

`lalt`, `spc`, `ralt` holds **emit real OS modifier keycodes** (`lctl`, `lmet`,
`lsft`). Combinations compose at the OS level — that is the design, so never
replace an emission with a `C-`/`M-` remap layer: a layer mapping produces
exactly one key and does NOT compose (the pre-2026-11 config did this and needed
six combo layers).

- `ralt` = `(multi lsft (layer-while-held sft))`: Shift emission + thin layer whose
  only remap is `lalt` (tap `bspc`, hold `lctl`). Everything else in `sft` is `_`.
- `lalt` = `(multi lctl (layer-while-held ctl))`: the mirrored idiom — the thin
  `ctl` layer's only remap is `spc` (hold `lsft`). `lalt`-first+`spc` = Ctrl+Shift
  (app-shortcut grammar; the laptop-safe pair); `spc`-first+`lalt` = Ctrl+Super,
  unchanged (Omarchy panels/menus/clipboard manager). Kanata locks a key's action
  at its press, so the thumb-roll order picks the namespace — deliberate, do not
  unify. This swaps WHICH real modifier is emitted, not a `C-`/`M-` remap layer.
- Tap-hold VARIANT POLICY — per key, do not unify (each choice fixes a real bug):
  - `spc` = `tap-hold-release`. Space is rolled into the next letter constantly
    while typing; release-commit keeps natural rolls (space released first) as
    taps. With `tap-hold-press`, every roll fired `SUPER+<letter>` and closed
    windows (`SUPER+W`). Consequence: `spc+d+f` gives plain tab (chords fire at
    the second keypress, before spc's release-commit) — pre-hold spc ≥300ms for
    `M-tab`, or use workspace binds instead.
  - `lalt`/`ralt`/`rctl`/`@laltsft` = `tap-hold-press`. Chords (`d+f`) fire at
    the second keypress, so a release-committed modifier lands AFTER the chord
    output (`lalt+d+f` was plain tab). Their tap values (C-bspc/ret/esc/bspc)
    are deliberate presses, not typed-through, so press-commit is typing-safe.
- `rctl` hold = num layer (digits/arrows); `lalt` inside num = sym layer.
  Order matters: rctl-first for sym; lalt-first then rctl gives `Ctrl+digit`
  (browser tab jumping). Documented, intentional.
- The physical digit row is intentionally unmapped (`process-unmapped-keys yes`):
  digits/symbols come from num/sym layers and the emission makes passthrough keys
  pick up held modifiers (`spc+6` → `SUPER+6`).
- One chord: `d+f` → tab. Chorded keys: `d`, `f` only.
- Layers: `base`, `sft` (thin), `ctl` (thin), `num`, `sym`.

## Workflow

```bash
kanata --list                                     # FIRST: which keyboard is kanata mapping?
kanata --check --cfg ~/.config/kanata/config.kbd   # validate
~/.config/kanata/restart-kanata.sh                 # apply (script also validates)

# Test behavior WITHOUT touching the keyboard — feed it an event script:
#   echo "t:500 d:lalt t:30 d:ralt t:200 d:d t:40 d:f" > /tmp/sim.txt
#   kanata_simulated_input -c ~/.config/kanata/config.kbd -s /tmp/sim.txt
# Format: t:<ms> delay, d:<key> press, u:<key> release.
# Built from https://github.com/jtroo/kanata/tree/main/simulated_input (v1.12.0).

# Omarchy side — auto-reloads on save, then validate:
hyprctl reload && hyprctl configerrors
omarchy menu keybindings --print                   # inspect live binds
```

When re-binding an existing Omarchy key: use `o.rebind(...)` (never plain
`o.bind` on a taken key), and tell the user what the key was bound to before.
Copy action expressions verbatim from the defaults in
`~/.local/share/omarchy/default/hypr/bindings/*.lua` (they use per-monitor
workspace helpers like `o.workspaces.focus(N)` — don't substitute raw
`workspace, N` dispatchers).

## Constraints

- Split-keyboard latency: do not lower `chord-timeout` below 100ms.
- Keep aliases ≤8 chars, `[action][layer]` naming (e.g. `laltnum`).
- Anything window-manager-ish belongs in `bindings.lua`, not `config.kbd`.
- **Laptop matrix limitation** (measured 2026-11-20; full table in README):
  holding two thumb keys drops the third keypress before kanata sees it.
  `lalt`+`ralt` blocks `a f x c v b n ; ' , . /`; `ralt`+`spc` blocks
  `i j k m`; `spc`+`rctl` blocks `j`; `lalt`+`spc` blocks `,`;
  `lalt`+`rctl` (sym) and `ralt`+`rctl` block nothing.
  Practical rule: thumb pairs are fine for `sym`/`num`; `Ctrl+Shift` has a
  thumb path (`lalt` first, then `spc` — only `,` blocked); `Super+Shift`
  chords stay native on the laptop. Do not chase these as config bugs —
  verify with `kanata_simulated_input` (config-level truth) or on the split
  keyboard.
- Before ANY combo debugging, run `kanata --list`: the split and the laptop
  are different hardware with different behavior, and most "mysterious"
  failures on the laptop turn out to be matrix blocks, not config bugs.

## TBD (documented in bindings.lua)

- Tmux/Herdr are re-homed on the SUPER+SHIFT launch cluster (`spc+ralt` + t/r,
  Launcher section of bindings.lua); native SUPER+ALT/CTRL+RETURN defaults
  remain as fallbacks.
- `omarchy_preinstalled_bindings = false` in `hyprland.lua` would free all
  unused app/webapp binds wholesale (user doesn't use app launches).

## Permissions

If kanata dies with "No keyboard devices were found", an Omarchy upgrade
stripped the group grant. Re-run `bash ~/.config/kanata/setup-kanata.sh`, then
log out/in. Details in README.md.
