"""Own-VPS-style local hosting without Docker: serve registered static
folders over loopback only. Each app gets a 127.0.0.1 port. No LAN/WAN
exposure, no containers, stdlib HTTP server in a daemon thread.
"""

from __future__ import annotations

import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class HostingError(RuntimeError):
    pass


class HostedApp:
    def __init__(self, name: str, directory: str, port: int) -> None:
        self.name = name
        self.directory = directory
        self.port = port
        self.url = f"http://127.0.0.1:{port}/"
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        if self._server is not None:
            return self.url
        if not os.path.isdir(self.directory):
            raise HostingError(f"App directory missing: {self.directory!r}")
        handler = functools.partial(SimpleHTTPRequestHandler, directory=self.directory)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self._server = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._thread = thread
        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None

    @property
    def running(self) -> bool:
        return self._server is not None


class HostManager:
    """Registry of locally hosted static apps."""

    def __init__(self) -> None:
        self._apps: dict[str, HostedApp] = {}

    def register(self, name: str, directory: str, port: int = 0) -> HostedApp:
        key = name.strip().lower()
        if not key:
            raise HostingError("App needs a name.")
        if key in self._apps:
            raise HostingError(f"App already registered: {name!r}")
        app = HostedApp(name=key, directory=os.path.abspath(directory), port=port)
        self._apps[key] = app
        return app

    def serve(self, name: str) -> str:
        app = self._apps.get(name.strip().lower())
        if app is None:
            raise HostingError(f"Unknown app: {name!r}. Register it first.")
        return app.start()

    def stop(self, name: str) -> None:
        app = self._apps.get(name.strip().lower())
        if app is None:
            raise HostingError(f"Unknown app: {name!r}")
        app.stop()

    def unregister(self, name: str) -> None:
        key = name.strip().lower()
        app = self._apps.get(key)
        if app is None:
            raise HostingError(f"Unknown app: {name!r}")
        app.stop()
        del self._apps[key]

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": app.name,
                "directory": app.directory,
                "url": app.url,
                "running": app.running,
            }
            for app in self._apps.values()
        ]

    def stop_all(self) -> None:
        for app in self._apps.values():
            app.stop()


_manager = HostManager()


def get_manager() -> HostManager:
    return _manager
