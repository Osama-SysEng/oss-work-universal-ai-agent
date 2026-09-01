"""Review-only updater.

This module can inspect a local manifest and verify a supplied artifact hash. It
does not download, extract, install, execute, or hot-reload untrusted code.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


class Updater:
    def __init__(self, current_version: str = "0.2.0-safe") -> None:
        self.current_version = current_version

    def inspect_artifact(self, artifact: str | Path, expected_sha256: str) -> dict[str, object]:
        path = Path(artifact).expanduser().resolve()
        if not path.is_file():
            return {"status": "failed", "error": "artifact not found", "install_attempted": False}
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        valid = digest.lower() == expected_sha256.lower()
        return {"status": "review_required" if valid else "rejected", "sha256": digest, "hash_matches": valid, "install_attempted": False, "message": "Manual review and staged rollout are required; no installation was attempted."}

    def install_update(self, *_: object, **__: object) -> dict[str, object]:
        return {"status": "denied", "install_attempted": False, "reason": "Automatic update installation is disabled in the safe release."}


class SkillDownloader:
    def download_skill(self, *_: object, **__: object) -> dict[str, object]:
        return {"status": "denied", "install_attempted": False, "reason": "Runtime skill download and package installation are disabled."}


if __name__ == "__main__":
    print("Review-only updater: no download or installation is performed.")
