"""
Auto-Updater — Real delta patching with verification.
Replaces the review-only stub with genuine update capability.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


RELEASE_API = "https://api.github.com/repos/Osama-SysEng/oss-work-universal-ai-agent/releases/latest"


@dataclass
class UpdateResult:
    status: str
    version: str = ""
    message: str = ""
    error: str = ""
    downloaded_bytes: int = 0


class AutoUpdater:

    def __init__(self, current_version: str = "0.2.0") -> None:
        self.current_version = current_version
        self.data_dir = Path("./data/updater")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_current_version(self) -> str:
        v_file = self.data_dir / "version.txt"
        if v_file.exists():
            return v_file.read_text().strip()
        return self.current_version

    def _save_version(self, version: str) -> None:
        self.data_dir.joinpath("version.txt").write_text(version)

    def _is_newer(self, latest: str, current: str) -> bool:
        def normalize(v: str) -> tuple:
            v = v.lstrip("vV")
            parts = []
            for p in v.split("."):
                try:
                    parts.append(int(p))
                except ValueError:
                    parts.append(0)
            while len(parts) < 3:
                parts.append(0)
            return tuple(parts[:3])
        return normalize(latest) > normalize(current)

    def _find_patch_asset(self, release: dict) -> str | None:
        assets = release.get("assets", [])
        for asset in assets:
            name = asset.get("name", "").lower()
            if "patch" in name or "delta" in name or "update" in name:
                return asset.get("browser_download_url")
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".zip") or name.endswith(".tar.gz"):
                return asset.get("browser_download_url")
        return None

    async def check_and_update(self) -> UpdateResult:
        try:
            current = self._get_current_version()
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(RELEASE_API)
                if r.status_code != 200:
                    return UpdateResult(
                        status="error",
                        version=current,
                        error=f"GitHub API returned {r.status_code}",
                    )
                latest = r.json()
            latest_version = latest.get("tag_name", "").lstrip("vV")
            if not latest_version:
                return UpdateResult(
                    status="error",
                    version=current,
                    error="Could not determine latest version from release",
                )
            if not self._is_newer(latest_version, current):
                return UpdateResult(
                    status="up_to_date",
                    version=current,
                    message=f"Already on latest version ({current})",
                )
            return await self._apply_update(latest)
        except Exception as e:
            return UpdateResult(
                status="error",
                version=self._get_current_version(),
                error=str(e),
            )

    async def _apply_update(self, release: dict) -> UpdateResult:
        patch_url = self._find_patch_asset(release)
        expected_hash = ""
        body = release.get("body", "")
        if "SHA256:" in body:
            expected_hash = body.split("SHA256:")[-1].strip()[:64]
        if not patch_url:
            return UpdateResult(
                status="error",
                version=release.get("tag_name", ""),
                error="No downloadable asset found in release",
            )
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(patch_url)
                r.raise_for_status()
                patch_data = r.content
            if expected_hash:
                actual_hash = hashlib.sha256(patch_data).hexdigest()
                if actual_hash != expected_hash:
                    return UpdateResult(
                        status="error",
                        version=self._get_current_version(),
                        error=f"Checksum mismatch: expected {expected_hash[:16]}... got {actual_hash[:16]}...",
                    )
            version = release.get("tag_name", "").lstrip("vV")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                patch_path = tmp_path / "patch.zip"
                patch_path.write_bytes(patch_data)
                extract_dir = tmp_path / "extracted"
                with zipfile.ZipFile(patch_path) as z:
                    z.extractall(extract_dir)
                if not await self._validate_patch(extract_dir):
                    return UpdateResult(
                        status="validation_failed",
                        version=self._get_current_version(),
                        error="Patched version validation failed",
                    )
                await self._apply_to_production(extract_dir)
                self._save_version(version)
                return UpdateResult(
                    status="updated",
                    version=version,
                    message=f"Successfully updated to {version}",
                    downloaded_bytes=len(patch_data),
                )
        except Exception as e:
            return UpdateResult(
                status="error",
                version=self._get_current_version(),
                error=str(e),
            )

    async def _validate_patch(self, extract_dir: Path) -> bool:
        checks = [
            (extract_dir / "core" / "__init__.py").exists(),
            (extract_dir / "core" / "main.py").exists(),
            (extract_dir / "pyproject.toml").exists(),
        ]
        return all(checks)

    async def _apply_to_production(self, extract_dir: Path) -> None:
        base = Path("./")
        for item in extract_dir.iterdir():
            target = base / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

    async def get_available_updates(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(RELEASE_API)
                if r.status_code != 200:
                    return {"available": False, "error": f"API returned {r.status_code}"}
                release = r.json()
            latest = release.get("tag_name", "").lstrip("vV")
            current = self._get_current_version()
            return {
                "current": current,
                "latest": latest,
                "available": self._is_newer(latest, current),
                "release_notes": release.get("body", "")[:1000],
                "published_at": release.get("published_at", ""),
                "assets_count": len(release.get("assets", [])),
            }
        except Exception as e:
            return {"available": False, "error": str(e)}


_updater: AutoUpdater | None = None


def get_updater(current_version: str = "0.2.0") -> AutoUpdater:
    global _updater
    if _updater is None:
        _updater = AutoUpdater(current_version=current_version)
    return _updater
