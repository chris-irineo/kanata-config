# Kanata Configuration

Split-keyboard configuration for [kanata](https://github.com/jtroo/kanata) with custom layers, chords and tap-hold modifiers. Runs as a systemd user service on Omarchy/Arch, and is portable to Windows (GlazeWM).

## Files

| Path | Purpose |
|------|---------|
| `~/.config/kanata/config.kbd` | **The one config.** Edit this and nothing else. |
| `~/.config/kanata/kanata-windows.kbd` | Generated for Windows — do not edit |
| `~/.config/kanata/setup-kanata.sh` | One-time/idempotent permission + service setup |
| `~/.config/kanata/restart-kanata.sh` | Validate config and restart the service |
| `~/.config/kanata/tools/layer_map.py` | Render a layer from `config.kbd` (also used by the overlay) |
| `~/.config/kanata/tools/layer-overlay.py` | Watcher that drives the on-screen layer overlay |
| `~/.config/systemd/user/kanata.service` | The running service (`--cfg ~/.config/kanata/config.kbd --port 127.0.0.1:7070`) |
| `~/.config/systemd/user/kanata-layer-overlay.service` | Symlink to `tools/systemd/kanata-layer-overlay.service` |
| `/etc/udev/rules.d/99-kanata.rules` | Grants the `kanata` group keyboard + uinput access (root) |

There is a single copy of the config. Older notes referenced `~/.kanata/kanata.kbd` and `/etc/kanata/kanata-config.kbd`; both are gone — the git history of this repo still has them.

## Editing workflow

```bash
# 1. Edit ~/.config/kanata/config.kbd
# 2. Validate (cheap, no restart needed)
kanata --check --cfg ~/.config/kanata/config.kbd
# 3. Apply
~/.config/kanata/restart-kanata.sh        # or: systemctl --user restart kanata
```

If you change the Linux config, regenerate the Windows variant:

```bash
~/.config/kanata/generate-windows-config.sh
```

It converts every `M-` (Meta) binding to `A-` (Alt) for GlazeWM. Always edit `config.kbd` and regenerate; `kanata-windows.kbd` is overwritten.

## Layer overlay

While a special layer is held, a card at the bottom of the screen shows that
layer's key map — generated from `config.kbd`, so it cannot go stale.

How it fits together:

- `kanata.service` runs kanata with `--port 127.0.0.1:7070`, which streams
  newline-terminated JSON events (`{"LayerChange":{"new":"sym"}}`).
- `tools/layer-overlay.py` (unit: `kanata-layer-overlay.service`) subscribes to
  those events. Each layer has its own delay before it appears — 120ms for
  `sym`, `KANATA_OVERLAY_DEBOUNCE` (500ms) for everything else — so a quick tap
  of a layer you already know flashes nothing while the layer you keep
  forgetting is there almost instantly. Switching between layers while visible
  updates it immediately; returning to `base` hides it. Tune the per-layer
  values in the `DELAYS` map at the top of the script.
- `tools/layer_map.py` turns `defsrc` + `deflayer` into a display grid:
  output chords become glyphs for the `us` layout (`S-1` → `!`, `S-grv` → `~`),
  `tap-hold` shows `tap/hold`, aliases and `multi` are resolved.
- The card itself is the Omarchy shell plugin
  `~/.config/omarchy/plugins/chris.kanata-layers/` (IPC target
  `kanata-layers`), so it follows the current theme and never takes focus.

`base` and `game` are excluded (`HIDDEN` in `layer-overlay.py`); `game` is a
switched layer, so its overlay would stay up.

Handy commands:

```bash
~/.config/kanata/tools/layer_map.py sym     # print one layer's map
~/.config/kanata/tools/layer_map.py --json  # everything, machine-readable
systemctl --user status kanata-layer-overlay
journalctl --user -u kanata-layer-overlay -e
```

If the card ever fails to appear, check that the plugin is enabled in
`~/.config/omarchy/shell.json` (`plugins` → `{"id": "chris.kanata-layers"}`)
and that `omarchy-shell kanata-layers ping` answers `ok`.

## Permissions on Omarchy

Kanata's config runs as a user service and needs raw keyboard access. Omarchy migration `1787865477.sh` removes the user from the `input` group on upgrade (that group grants keylogging-level access, so Omarchy drops it unless `xpadneo-dkms` or `ydotool` is installed). Kanata legitimately needs it but isn't on the keep-list, so an upgrade silently breaks it:

```
[ERROR] failed to open keyboard device(s): No keyboard devices were found.
```

Fix by re-running the setup script:

```bash
bash ~/.config/kanata/setup-kanata.sh
# then log out and back in (group membership applies to new sessions only)
systemctl --user start kanata
kanata --list            # should list your keyboard
journalctl --user -u kanata -e
```

It creates a dedicated `kanata` group plus a udev rule granting that group read access to physical keyboards and write access to `/dev/uinput`.

| Approach | Survives upgrades | Survives fresh install | Security posture |
|----------|-------------------|------------------------|------------------|
| `usermod -aG input $USER` | yes (migration is one-shot, already marked done) | **no** — re-stripped on fresh install | reopens the keylogging risk Omarchy closed |
| dedicated `kanata` group + udev rule | yes | **yes** | least privilege; stays out of `input` |

The udev rule lives in `/etc/udev/rules.d/` (not touched by Omarchy) and no Omarchy migration references a `kanata` group, so this is upgrade- and reinstall-proof.

## Hardware

- Split keyboard (QMK/Vial) with timing delays between halves
- Chord timeouts are 100ms rather than 50ms to tolerate cross-hand latency
- Works on laptop keyboard with the documented limitations below

## Layers

### Base
- **lalt**: tap=`C-bspc`, hold=`ctl` layer
- **ralt**: tap=`ret`, hold=`sft` layer
- **rctl**: tap=`esc`, hold=`num` layer
- **spc**: tap=`spc`, hold=`nav` layer

### Nav (space + key)
- `i/j/k/l` → `M-up/M-left/M-down/M-right`
- `a/s/d/f/g` → `M-1` … `M-5`
- Other keys → `M-{key}` for window management

### Num (rctl + key)
- Home row: `1 2 3 4 5`
- Bottom row: `6 7 8 9 0`
- `i/j/k/l` → up/left/down/right arrows
- **lalt** in num layer → `sym` layer

### Sym (rctl + lalt + key)
See `sym-layer-cheatsheet.txt`.

### Sft (ralt + key)
- All keys shifted (`S-a`, `S-b`, …)
- **lalt** in sft layer → num layer (works on split keyboard, limited on laptop)

### Ctl (lalt + key)
- All keys with control (`C-a`, `C-b`, …)
- **ralt** in ctl layer → sym layer (works on split keyboard, limited on laptop)

## Chords

All chords share a 100ms timeout:

- `q+w` → esc
- `d+f` → tab
- `w+x` → switch to game layer
- `c+v` → `M-spc`
- `x+c` → `M-A-spc`
- `esc+tab` → back to base layer (from game layer)

## Timeouts

- `tap-timeout`: 150ms
- `hold-timeout`: 300ms
- `short-hold-timeout` (ralt): 150ms
- `chord-timeout`: 100ms (all chords)

## Known issue: sequential layer activation on laptop keyboards

Sequential activation (`ralt`→`lalt` for num, `lalt`→`ralt` for sym) blocks certain keys on laptop keyboards: `a f c v b n ; ' , . /` and digits `1 2 3 4 5`.

This is a laptop keyboard matrix/rollover limitation, not a kanata problem — the same config works flawlessly on the split keyboard. Workarounds: use the split keyboard, or use `rctl+lalt` for sym (rctl→num→lalt→sym works on both).

## Validation and status

```bash
kanata --check --cfg ~/.config/kanata/config.kbd
systemctl --user status kanata
journalctl --user -u kanata -e
```
