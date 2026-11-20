# Kanata Configuration — agent notes

## Ground truth

**The only config file is `~/.config/kanata/config.kbd`.** Edit it in place; never
create a second copy, and never work in `~/.kanata/` or `/etc/kanata/` — those
paths are historical and were removed (git history in this repo still has them,
which is why old notes may mention `kanata.kbd`).

- Git repo = this directory (remote: `chriskevini/kanata-config`, branch `main`)
- Hardware: split keyboard (QMK/Vial), hence the 100ms chord timeout
- Service: `~/.config/systemd/user/kanata.service`, started with
  `--cfg ~/.config/kanata/config.kbd`
- Derived file: `kanata-windows.kbd` is generated, never edited by hand

## Workflow

```bash
kanata --check --cfg ~/.config/kanata/config.kbd   # validate
systemctl --user restart kanata                    # apply
# after editing config.kbd for Windows users:
~/.config/kanata/generate-windows-config.sh
```

The service runs with `--port 127.0.0.1:7070`; `tools/layer-overlay.py`
(`kanata-layer-overlay.service`) subscribes to `LayerChange` events and shows
the layer card via the Omarchy plugin `chris.kanata-layers`. Show delay is
per-layer (`DELAYS` in the script): 120ms for `sym`, 500ms for the rest. The card's content
is rendered from `config.kbd` by `tools/layer_map.py` at show time, so a config
edit is reflected without touching the plugin. No TCP `msg` subcommand exists
in kanata 1.12.0 — the watcher speaks the protocol directly.

## Current config shape

- `defcfg`: `process-unmapped-keys yes`
- Timeouts: `tap-timeout 150`, `hold-timeout 300`, `short-hold-timeout 150`
  (ralt), `chord-timeout 100` (all chords)
- Tap-holds: `lalt` = tap `C-bspc`, hold `ctl` layer; `ralt` = tap `ret`, hold
  `sft`; `rctl` = tap `esc`, hold `num`; `spc` = tap `spc`, hold `nav`
  (all `tap-hold-release` except `rctl`, which is `tap-hold-press`)
- Chords (100ms): `q+w` esc, `d+f` tab, `w+x` game layer, `c+v` `M-spc`,
  `x+c` `M-A-spc`, `esc+tab` back to base
- Layers: `base`, `game`, `nav`, `num`, `sym`, `sft`, `ctl`
- `lalt` inside `num` → `sym`; `lalt` inside `sft` → `num`; `ralt` inside
  `ctl` → `sym`

## Constraints

- Split-keyboard latency: do not lower `chord-timeout` below 100ms for
  cross-hand chords.
- Sequential layer activation (`ralt`→`lalt`, `lalt`→`ralt`) blocks keys on the
  laptop keyboard (hardware matrix limit). Works on the split keyboard. Don't
  "fix" it in config.
- Keep aliases ≤8 chars, `[action][layer]` naming (e.g. `escgame`).

## Permissions

If kanata dies with "No keyboard devices were found", Omarchy stripped the
group grant. Re-run `bash ~/.config/kanata/setup-kanata.sh`, then log out/in.
Details in README.md.
