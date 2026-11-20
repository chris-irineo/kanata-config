#!/usr/bin/env python3
"""Watch kanata layer changes and show the Omarchy shell layer overlay.

kanata runs with `--port 127.0.0.1:7070`, which streams newline-terminated
JSON events. On every LayerChange we wait a per-layer delay before showing
(500ms by default, 120ms for `sym`; see DELAYS) so quick taps of a layer
key you already know don't flash anything. Changes between layers while the
overlay is visible update it immediately; returning to `base` hides it.

The key map itself comes from layer_map.py, which reads config.kbd, so the
overlay never drifts from the actual configuration.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layer_map  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("KANATA_TCP_PORT", "7070"))
HIDDEN = {"base", "game"}

# Delay before the card appears, per layer, measured from the moment the layer
# becomes active. Layers not listed use DEFAULT_DELAY. Short values make a
# layer feel instant; the point of the delay is only to keep quick taps you
# already know from flashing a card. `sym` is the one that needs help, so it
# gets a much shorter wait than the rest.
DEFAULT_DELAY = float(os.environ.get("KANATA_OVERLAY_DEBOUNCE", "0.5"))
DELAYS = {"sym": 0.12}
IPC_TARGET = "kanata-layers"


def delay_for(layer: str) -> float:
    return DELAYS.get(layer, DEFAULT_DELAY)


def log(message: str) -> None:
    print(message, flush=True)


def ipc(*args: str) -> None:
    try:
        subprocess.run(
            ["omarchy-shell", "-q", IPC_TARGET, *args],
            timeout=5,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


class Overlay:
    def __init__(self) -> None:
        self.layers = {}
        self.stamp = None
        self.shown = None
        self.pending = None  # (layer, deadline)
        self.load_maps()

    def load_maps(self) -> None:
        try:
            stamp = os.stat(layer_map.CONFIG).st_mtime_ns
        except OSError:
            return
        if stamp == self.stamp:
            return
        try:
            self.layers = layer_map.load()
            self.stamp = stamp
            log(f"loaded {len(self.layers)} layers from {layer_map.CONFIG}")
        except Exception as exc:  # noqa: BLE001 - never die on a bad edit
            log(f"could not parse config: {exc}")

    def run(self) -> None:
        if self.pending and time.monotonic() >= self.pending[1]:
            layer = self.pending[0]
            self.pending = None
            if layer in self.layers:
                self.show(layer)

    def show(self, layer: str) -> None:
        if self.shown == layer:
            return
        payload = json.dumps(
            {"layer": layer, "rows": self.layers[layer]["rows"]},
            ensure_ascii=False,
        )
        ipc("show", payload)
        self.shown = layer

    def hide(self) -> None:
        self.pending = None
        if self.shown is None:
            return
        ipc("hide")
        self.shown = None

    def on_layer(self, layer: str) -> None:
        self.load_maps()
        if layer in HIDDEN or layer not in self.layers:
            self.hide()
            return
        if self.shown is not None:
            # Already visible: switch content right away, no debounce flicker.
            self.show(layer)
            return
        if self.pending and self.pending[0] == layer:
            return
        self.pending = (layer, time.monotonic() + delay_for(layer))


def stream(overlay: Overlay) -> None:
    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        sock.settimeout(0.05)
        buf = b""
        while True:
            overlay.run()
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("kanata closed the connection")
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                change = message.get("LayerChange")
                if isinstance(change, dict) and "new" in change:
                    overlay.on_layer(str(change["new"]))


def main() -> int:
    overlay = Overlay()
    while True:
        try:
            stream(overlay)
        except (OSError, ConnectionError) as exc:
            overlay.hide()
            log(f"kanata not reachable on {HOST}:{PORT} ({exc}); retrying")
            time.sleep(2)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
