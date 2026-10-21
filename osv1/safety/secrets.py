"""Encrypted secret storage (spec sections 12 and 19).

No secret is stored in plain text. On Windows the store uses DPAPI, so a
secret is encrypted against the current user account and cannot be read by
another account on the same machine. On other systems the store refuses to
save rather than falling back to plaintext.

The values never appear in the audit log: the audit layer redacts them, and
this module never returns a secret to a log or a result.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WINDOWS = os.name == "nt"


class SecretStoreError(RuntimeError):
    """The store cannot keep this secret safely."""


def _dpapi_protect(data: bytes) -> bytes:
    if not WINDOWS:
        raise SecretStoreError("no encrypted secret store is available on this platform")
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    input_blob = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = _Blob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(ctypes.byref(input_blob), None, None, None, None, 0x01, ctypes.byref(output_blob)):
        raise SecretStoreError("the operating system refused to encrypt the secret")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if not WINDOWS:
        raise SecretStoreError("no encrypted secret store is available on this platform")
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    input_blob = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = _Blob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, None, None, None, 0x01, ctypes.byref(output_blob)
    ):
        raise SecretStoreError("the operating system refused to decrypt the secret")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


@dataclass
class SecretStore:
    """Encrypted, per-user secret storage."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/secrets.enc"))
    available: bool = field(default_factory=lambda: WINDOWS)

    def _load_raw(self) -> dict[str, str]:
        """Read and decrypt the store. A file it cannot decrypt is treated as empty."""
        if not self.path.exists():
            return {}
        try:
            protected = base64.b64decode(self.path.read_bytes())
            document = _dpapi_unprotect(protected)
            payload = json.loads(document.decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError, SecretStoreError):
            return {}
        secrets = payload.get("secrets", {})
        return {str(k): str(v) for k, v in secrets.items()}

    def _save_raw(self, payload: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = json.dumps({"secrets": payload}, ensure_ascii=False, indent=2).encode("utf-8")
        if not self.available:
            raise SecretStoreError(
                "this platform has no encrypted secret store; refusing to write the secret in plain text"
            )
        protected = _dpapi_protect(document)
        self.path.write_bytes(base64.b64encode(protected))

    def set(self, name: str, value: str) -> None:
        if not name or not value:
            raise ValueError("a secret needs a name and a value")
        payload = self._load_raw()
        payload[name] = base64.b64encode(value.encode("utf-8")).decode("ascii")
        self._save_raw(payload)

    def get(self, name: str) -> str | None:
        payload = self._load_raw()
        encoded = payload.get(name)
        if encoded is None:
            return None
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")

    def delete(self, name: str) -> bool:
        payload = self._load_raw()
        if name not in payload:
            return False
        payload.pop(name)
        self._save_raw(payload)
        return True

    def names(self) -> list[str]:
        return sorted(self._load_raw())

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "backend": "windows-dpapi" if WINDOWS else "none",
            "path": str(self.path),
            "stored": len(self._load_raw()),
        }
