# Kanata Configuration

Split-keyboard remap for [kanata](https://github.com/jtroo/kanata) that turns the
thumb keys into real OS-level **Ctrl / Super / Shift** modifiers. Window management
lives in Omarchy (`~/.config/hypr/bindings.lua`), not here. Runs as a systemd user
service on Omarchy/Arch.

## The system in one glance

| Thumb | Tap | Hold |
|---|---|---|
| `lalt` | `C-bspc` (delete word) | **Ctrl** (real `lctl` emitted) |
| `spc` | space | **Super** (real `lmet` emitted) |
| `ralt` | `ret` | **Shift** (real `lsft`, + thin `sft` layer) |
| `rctl` | `esc` | **num** layer (`lalt` inside → **sym** layer) |

Hold modifiers **compose** — kanata emits real keycodes, so the OS combines them:

| Hold | Then press | Result |
|---|---|---|
| `lalt` | any key | `Ctrl-x` |
| `spc` | any key | `Super-x` (Omarchy binds) |
| `ralt` | any key | `Shift-x` |
| `spc` then `lalt` — rest the blade on `spc`, drop the knuckle onto `lalt` | any key | `Ctrl+Super-x` → Omarchy grammar: `v` clipboard manager, `a` audio, `n` network, `l` lock … |
| `lalt` then `spc` | any key | `Ctrl+Shift-x` → app grammar: `n` incognito / go-to-file, `t` reopen tab, `v` paste plain, terminal `c/v` copy-paste |
| any combo | `d`+`f` | Tab with those modifiers (`C-tab`, `M-tab`, `C-S-tab`, …) |
| `ralt` | tap `lalt` | plain `bspc` (char delete; `lalt` tap alone is word delete) |
| `lalt` | digits | `Ctrl-1..0` (browser tab jumping; digits pass through) |

**One chord: `d+f` = Tab** (100ms; works under every modifier combo).

**Documented asymmetries:** `rctl` then `lalt` → sym layer; `lalt` then `rctl` →
`Ctrl+digit`. Press the sym thumb (`rctl`) first for symbols. `lalt`+`spc` is
order-split along the thumb roll: one roll rests the blade on `spc` and drops
the first knuckle onto `lalt` → **Ctrl+Super** (Omarchy panels/menus); leading
with `lalt` → **Ctrl+Shift** (the app-shortcut grammar — the laptop-safe pair,
since the matrix only blocks `,` here). Whichever end of the thumb lands first
picks the namespace.

**Num (rctl + key):** `a s d f g` → `1 2 3 4 5`, `z x c v b` → `6 7 8 9 0`,
top row = operator strip: `q w e r t` → `/ * - + =`, `y u i o p` → `( ) % < >`
(`( ) %` avoid digit-row reaches; `< >` make `<=`/`>=` one-hold rolls against
`=` at `t`). `h j k l` → ←↓↑→ (vim), `;`/`'` → word jumps (`C-left`/`C-right` —
also browser back/forward), `n m` → PgUp/PgDn; `, . /` fall through, so decimals,
paths, and `1.5e3` notation type natively. Hold `ralt` too and any motion
**selects** instead. **Sym (rctl, then lalt):** only symbols outside the alpha
cluster; blanks inherit the num layer underneath (`< >` at `o p`, word jumps,
PgUp/PgDn) — the overlay card resolves it. See `sym-layer-cheatsheet.txt`.

## Window management (Omarchy side)

`spc` emits Super, so Omarchy binds ARE the nav layer. Grammar: **plain Super
navigates, Super+Shift moves.** Defined in `~/.config/hypr/bindings.lua`:

| Keys | Action |
|---|---|
| `spc` + `a s d f g` | workspace 1–5 (digits: 6–10) |
| `spc+ralt` + `a s d f g` | move window → workspace 1–5 (digits: 6–10) |
| `spc` + `h j k l` | focus left/down/up/right (vim grammar) |
| `spc+ralt` + `h j k l` | swap window |
| `spc` + `n` | Omarchy menu |
| `spc` + `semicolon` | scratchpad (`spc+ralt+;` = move window to it) |
| `spc` + `h b r u z y` | fullscreen / grouping / split / layout / keybinds |
| `spc+ralt` + `b` | full-width |
| `spc+ralt` + `v t r` | browser / tmux / herdr — the launch cluster (native `SUPER+SHIFT/ALT/CTRL+RETURN` defaults stay as fallbacks) |
| `spc` + `i` | input language (`spc+ralt+i` = back) — Omarchy defaults |

Omarchy defaults that already work with no bind: `spc+q/w` close, `spc+t` float,
`spc+m` minimize, `spc+c/v/x/a` universal clipboard, `spc+tab` next workspace,
`spc` + tap `ralt` (Super+Return) terminal.

**Launch cluster:** Tmux (`spc+ralt+t`) and Herdr (`spc+ralt+r`) join browser
(`spc+ralt+v`) on the move layer; their native `SUPER+ALT/CTRL+RETURN`
defaults stay as fallbacks. `spc+r` (toggle grouping) is vestigial — groups
unused. The Apps dock is unused.

## Files

| Path | Purpose |
|------|---------|
| `config.kbd` | **The one config** |
| `sym-layer-cheatsheet.txt` | Symbol layer quick reference |
| `restart-kanata.sh` / `setup-kanata.sh` | Validate+restart / permissions setup |
| `~/.config/systemd/user/kanata.service` | Runs `--cfg ~/.config/kanata/config.kbd` (port 7070 for the layer overlay) |
| `tools/layer_map.py` / `tools/layer-overlay.py` | Render a layer / drive the overlay card |
| `~/.config/hypr/bindings.lua` | The Omarchy companion binds (nav grammar above) |
| `archive/2026-11-20-legacy/` | Previous design: game layer, Windows/GlazeWM port, nav-layer remaps |

## Layer overlay

Holding a thumb layer shows that layer's key map in a card at the bottom of the
screen. Since the redesign, the only layers left are deliberate ones, so the
card appears with **no delay**: `rctl` (num), then `lalt` (sym). `base` is never
shown, and a layer that barely changes the map is skipped automatically —
`sft` remaps one key, so a card for it would just be noise (`MIN_MAPPED` in
`tools/layer-overlay.py`; raise it or set a per-layer delay in `DELAYS` if a
layer starts flashing when you don't want it).

```bash
tools/layer_map.py sym                      # print a layer's map
systemctl --user restart kanata-layer-overlay
journalctl --user -u kanata-layer-overlay -e
```

Card rendering lives in `~/.config/omarchy/plugins/chris.kanata-layers/` and
reads its content from `config.kbd` at show time, so it never drifts.

## Editing workflow

```bash
# Kanata side
kanata --check --cfg ~/.config/kanata/config.kbd   # validate
~/.config/kanata/restart-kanata.sh                 # apply

# Omarchy side (bindings.lua) — auto-reloads on save; then validate:
hyprctl reload && hyprctl configerrors
omarchy menu keybindings --print                   # inspect live binds
```

## Permissions on Omarchy

Kanata's config runs as a user service and needs raw keyboard access. Omarchy
migration `1787865477.sh` removes the user from the `input` group on upgrade, so
an upgrade can silently break kanata:

```
[ERROR] failed to open keyboard device(s): No keyboard devices were found.
```

Fix by re-running `bash ~/.config/kanata/setup-kanata.sh`, then log out/in and
`systemctl --user start kanata`. It uses a dedicated `kanata` group + udev rule
(`/etc/udev/rules.d/99-kanata.rules`) — upgrade- and reinstall-proof, and keeps
the user out of the keylogging-capable `input` group.

## Hardware notes

- Split keyboard (QMK/Vial): `chord-timeout` is 100ms for cross-half latency —
  don't lower it.
- **Laptop keyboard matrix limitation** — measured, not guessed (2026-11-20,
  deliberate passes ×3 letter rows, control pass 31/31 clean). Holding two
  thumb keys makes the laptop's built-in keyboard drop the third keypress; the
  press never reaches kanata, so nothing emits. This is a hardware
  matrix/rollover limit, not a kanata bug — the split keyboard does not have it.

  | held | blocked |
  |------|---------|
  | `lalt`+`spc` (Ctrl+Shift lalt-first; rolled spc-first = Ctrl+Super) | `,` |
  | `lalt`+`ralt` (Ctrl+Shift) | `a f x c v b n ; ' , . /` |
  | `lalt`+`rctl` (Ctrl, then sym) | **nothing** — symbols are safe |
  | `ralt`+`spc` (Shift+Super) | `i j k m` |
  | `spc`+`rctl` (Super, then num) | `j` |
  | `ralt`+`rctl` (Shift+Ctrl) | nothing |

  House rule: **thumb pairs are for `sym`/`num`; `Ctrl+Shift` chords have a
  thumb path — `lalt` first, then `spc` (the clean pair; only `,` blocked, and
  nothing common lives on `Ctrl+Shift+,`); `Super+Shift` chords stay native
  on the laptop.** The rows the matrix still bites: `Ctrl+Shift` via
  `lalt`+`ralt` (use the `spc` roll instead) and `Super+Shift+J/K` via
  `ralt`+`spc` — `Super+Shift+H/L` (swap left/right) survive.
  Two entries are intermittent rather than solid — `,` only failed in the three
  pairs without `rctl`, and `e` dropped once and passed once — so treat those
  as unconfirmed.
  When in doubt, verify on the split or with `kanata_simulated_input` before
  debugging the config.
- The digit row isn't mapped — physical digits (and F-keys, arrows, etc.)
  pass through and pick up held modifiers.
- Validation: `kanata --check …`, `systemctl --user status kanata`,
  `journalctl --user -u kanata -e`.
