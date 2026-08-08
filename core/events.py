"""Minimal thread-safe event emitter.

The engines run their I/O on background threads, so callbacks fire from
whichever thread is doing the work. Consumers (a Qt/Kivy UI, a CLI, a
websocket server, whatever) are responsible for hopping back onto their
own thread if they need to -- this just guarantees the emit itself won't
corrupt the listener list under concurrent add/remove.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable


class EventEmitter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, callback: Callable) -> None:
        with self._lock:
            self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable) -> None:
        with self._lock:
            if callback in self._listeners[event]:
                self._listeners[event].remove(callback)

    def emit(self, event: str, *args, **kwargs) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event, ()))
        for cb in callbacks:
            try:
                cb(*args, **kwargs)
            except Exception:
                # A broken UI callback should never take down a download.
                pass
