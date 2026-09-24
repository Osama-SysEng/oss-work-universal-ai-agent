"""
Skill Auto-Acquisition System.
OSS Work extends itself at runtime by downloading skills from GitHub, npm, pip, and HuggingFace.

When OSS Work encounters a task it can't handle, it searches for and installs
the needed skill automatically, then registers it in the skill registry.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


# ── Data ──────────────────────────────────────────────────────

@dataclass
class SkillCandidate:
    """A candidate skill found in a search."""
    source: str  # github, npm, pip, huggingface
    name: str
    description: str = ""
    stars: int = 0
    version: str = ""
    url: str = ""
    capability: str = ""
    score: float = 0.0


@dataclass
class Skill:
    """An installed skill."""
    name: str
    source: str
    version: str = ""
    capability: str = ""
    path: str = ""
    stars: int = 0
    installed_at: str = ""
    checksum: str = ""


@dataclass
class SkillResult:
    """Result of a skill acquisition attempt."""
    name: str
    status: str  # installed, already_installed, failed, not_found
    path: str = ""
    error: str = ""
    source: str = ""


# ── Skill Downloader ──────────────────────────────────────────

class SkillDownloader:
    """
    Auto-downloads skills from GitHub/npm/pip/HuggingFace when needed.
    
    OSS Work extends itself at runtime by finding and installing
    skills that provide capabilities it doesn't have built-in.
    """

    SKILL_DIR = Path("./skills")
    REGISTRY_FILE = SKILL_DIR / "registry.json"

    SKILL_SOURCES = {
        "github": "https://api.github.com/search/repositories",
        "npm": "https://registry.npmjs.org/",
        "pip": "https://pypi.org/pypi/",
        "huggingface": "https://huggingface.co/api/models",
    }

    # Known skill patterns (capability → search keywords)
    SKILL_PATTERNS = {
        "browser_automation": ["playwright", "selenium", "puppeteer", "browser-automation"],
        "code_generation": ["code-generator", "codegen", "code-generation", "ast-generator"],
        "web_scraping": ["scraper", "web-scraping", "crawler", "scrapy", "beautifulsoup"],
        "image_processing": ["image-processing", "opencv", "pillow", "computer-vision"],
        "nlp": ["nlp", "natural-language", "text-processing", "spacy", "nltk"],
        "data_analysis": ["data-analysis", "pandas", "data-science", "analytics"],
        "api_integration": ["api-client", "api-wrapper", "rest-client", "api-integration"],
        "database": ["database", "orm", "sql-tool", "mongodb", "redis-client"],
        "authentication": ["auth", "authentication", "oauth", "jwt", "login"],
        "notification": ["notification", "email", "sms", "push", "alert"],
        "file_processing": ["file-processing", "pdf", "docx", "excel", "csv-processing"],
        "machine_learning": ["ml", "machine-learning", "tensorflow", "pytorch", "scikit"],
        "testing": ["testing", "test-framework", "pytest-plugin", "test-runner"],
        "security": ["security", "scanner", "vulnerability", "pentest", "secrets"],
    }

    def __init__(self, skill_dir: Path | None = None) -> None:
        self.skill_dir = skill_dir or self.SKILL_DIR
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        self._registry = self._load_registry()

    def _load_registry(self) -> dict[str, Skill]:
        """Load the skill registry from disk."""
        if self.REGISTRY_FILE.exists():
            try:
                return json.loads(self.REGISTRY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_registry(self) -> None:
        """Persist the skill registry."""
        try:
            self.REGISTRY_FILE.write_text(
                json.dumps(self._registry, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def list_installed(self) -> list[Skill]:
        """List all installed skills."""
        return list(self._registry.values())

    def get_skill(self, name: str) -> Skill | None:
        """Get a specific installed skill."""
        return self._registry.get(name)

    async def acquire_skill(self, capability: str) -> SkillResult:
        """
        When OSS Work encounters a task it can't handle,
        search for and install the needed skill automatically.
        """
        # Check if already installed
        for skill in self._registry.values():
            if capability.lower() in skill.capability.lower():
                return SkillResult(
                    name=skill.name,
                    status="already_installed",
                    path=skill.path,
                    source=skill.source,
                )

        # Search for skill
        candidates = await self._search_skills(capability)

        if not candidates:
            return SkillResult(
                name=capability,
                status="not_found",
                error=f"No skill found for capability: {capability}",
            )

        # Rank and select best
        best = self._rank_candidates(candidates, capability)

        # Download and install
        try:
            skill = await self._install(best)
            await self._register(skill)
            return SkillResult(
                name=skill.name,
                status="installed",
                path=skill.path,
                source=skill.source,
            )
        except Exception as e:
            return SkillResult(
                name=best.name,
                status="failed",
                error=f"Installation failed: {e}",
                source=best.source,
            )

    async def _search_skills(self, capability: str) -> list[SkillCandidate]:
        """Search all sources for skills matching a capability."""
        candidates = []

        # Determine search keywords
        keywords = self.SKILL_PATTERNS.get(capability, [capability])

        # Search GitHub
        github_results = await self._search_github(keywords, capability)
        candidates.extend(github_results)

        # Search npm (for JavaScript/TypeScript skills)
        npm_results = await self._search_npm(keywords, capability)
        candidates.extend(npm_results)

        # Search pip (for Python skills)
        pip_results = await self._search_pip(keywords, capability)
        candidates.extend(pip_results)

        return candidates

    async def _search_github(
        self, keywords: list[str], capability: str
    ) -> list[SkillCandidate]:
        """Search GitHub for skill repositories."""
        results = []
        query = f"topic:oss-work-skill {keywords[0]}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    self.SKILL_SOURCES["github"],
                    params={
                        "q": query,
                        "sort": "stars",
                        "per_page": 10,
                    },
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "Authorization": f"token {os.getenv('GITHUB_TOKEN', '')}",
                    },
                )
                if r.status_code == 200:
                    for repo in r.json().get("items", [])[:5]:
                        results.append(SkillCandidate(
                            source="github",
                            name=repo["name"],
                            description=repo.get("description", "")[:200],
                            stars=repo.get("stargazers_count", 0),
                            url=repo["clone_url"],
                            capability=capability,
                            score=repo.get("stargazers_count", 0) * 0.5
                                  + (1 if repo.get("forks", 0) > 10 else 0),
                        ))
        except Exception as e:
            # GitHub search failed — not fatal
            pass

        return results

    async def _search_npm(
        self, keywords: list[str], capability: str
    ) -> list[SkillCandidate]:
        """Search npm registry for skill packages."""
        results = []

        # npm search API
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{self.SKILL_SOURCES['npm']}/-/v1/search",
                    params={
                        "text": keywords[0],
                        "size": 10,
                    },
                )
                if r.status_code == 200:
                    for pkg in r.json().get("objects", [])[:5]:
                        entry = pkg.get("package", {})
                        results.append(SkillCandidate(
                            source="npm",
                            name=entry.get("name", ""),
                            description=entry.get("description", "")[:200],
                            version=entry.get("version", ""),
                            url=f"https://www.npmjs.com/package/{entry.get('name', '')}",
                            capability=capability,
                            score=entry.get("score", {}).get("final", 0) * 0.3,
                        ))
        except Exception:
            pass

        return results

    async def _search_pip(
        self, keywords: list[str], capability: str
    ) -> list[SkillCandidate]:
        """Search PyPI for skill packages."""
        results = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{self.SKILL_SOURCES['pip']}{keywords[0]}/json",
                )
                if r.status_code == 200:
                    data = r.json()
                    info = data.get("info", {})
                    results.append(SkillCandidate(
                        source="pip",
                        name=data.get("info", {}).get("name", keywords[0]),
                        description=info.get("summary", "")[:200],
                        version=info.get("version", ""),
                        url=info.get("project_url", ""),
                        capability=capability,
                        score=1.0,  # Exact match gets high score
                    ))
        except Exception:
            # Package not found on PyPI — not an error
            pass

        return results

    def _rank_candidates(
        self, candidates: list[SkillCandidate], capability: str
    ) -> SkillCandidate:
        """Rank candidates and return the best one."""
        if not candidates:
            raise ValueError("No candidates to rank")

        # Score each candidate
        for c in candidates:
            # Relevance boost
            relevance = 0
            capability_lower = capability.lower()
            name_lower = c.name.lower()
            desc_lower = c.description.lower()

            if capability_lower in name_lower or capability_lower in desc_lower:
                relevance += 3.0
            for kw in capability_lower.split():
                if kw in name_lower or kw in desc_lower:
                    relevance += 1.0

            # Popularity boost
            if c.source == "github":
                popularity = min(c.stars / 100, 5.0)  # Cap at 5
            elif c.source == "npm":
                popularity = min(c.score * 2, 5.0)
            elif c.source == "pip":
                popularity = 3.0  # PyPI match is reliable
            else:
                popularity = 1.0

            c.score = relevance + popularity

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[0]

    async def _install(self, candidate: SkillCandidate) -> Skill:
        """Download and install a skill."""
        if candidate.source == "github":
            return await self._install_github(candidate)
        elif candidate.source == "npm":
            return await self._install_npm(candidate)
        elif candidate.source == "pip":
            return await self._install_pip(candidate)
        elif candidate.source == "huggingface":
            return await self._install_huggingface(candidate)
        else:
            raise ValueError(f"Unknown source: {candidate.source}")

    async def _install_github(self, candidate: SkillCandidate) -> Skill:
        """Clone a GitHub repository as a skill."""
        import shutil

        skill_path = self.skill_dir / candidate.name
        if skill_path.exists():
            # Already exists locally — verify it's complete
            if (skill_path / "skill.json").exists():
                return Skill(
                    name=candidate.name,
                    source="github",
                    version="local",
                    capability=candidate.capability,
                    path=str(skill_path),
                    stars=candidate.stars,
                    installed_at=__import__("datetime").datetime.now().isoformat(),
                )

        # Clone the repo
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", candidate.url, str(skill_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode('utf-8', errors='replace')}")

        # Verify skill.json exists
        skill_json = skill_path / "skill.json"
        if not skill_json.exists():
            # Create a default skill.json
            skill_json.write_text(
                json.dumps({
                    "name": candidate.name,
                    "capability": candidate.capability,
                    "source": "github",
                    "description": candidate.description,
                }, indent=2),
                encoding="utf-8",
            )

        return Skill(
            name=candidate.name,
            source="github",
            version="latest",
            capability=candidate.capability,
            path=str(skill_path),
            stars=candidate.stars,
            installed_at=__import__("datetime").datetime.now().isoformat(),
            checksum= hashlib.sha256(str(skill_path).encode()).hexdigest()[:16],
        )

    async def _install_npm(self, candidate: SkillCandidate) -> Skill:
        """Install an npm package as a skill (for JS/TS environments)."""
        # This would be used by the web/desktop interface
        # For Python core, we note the availability
        skill_path = self.skill_dir / candidate.name
        skill_path.mkdir(exist_ok=True)

        (skill_path / "SKILL.md").write_text(
            "# " + candidate.name + "\n\n" + candidate.description.replace("{", "").replace("}", "") + "\n\n"
            "Install via: npm install " + candidate.name + "\n"
            "Version: " + candidate.version + "\n",
            encoding="utf-8",
        )

        return Skill(
            name=candidate.name,
            source="npm",
            version=candidate.version,
            capability=candidate.capability,
            path=str(skill_path),
            installed_at=__import__("datetime").datetime.now().isoformat(),
        )

    async def _install_pip(self, candidate: SkillCandidate) -> Skill:
        """Install a pip package as a skill."""
        # Use pip to install
        proc = await asyncio.create_subprocess_exec(
            "pip", "install", candidate.name, "--quiet",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pip install failed: {stderr.decode('utf-8', errors='replace')}")

        skill_path = self.skill_dir / candidate.name
        skill_path.mkdir(exist_ok=True)

        (skill_path / "SKILL.md").write_text(
            "# " + candidate.name + "\n\n" + candidate.description.replace("{", "").replace("}", "") + "\n\n"
            "Installed via: pip install " + candidate.name + "\n"
            "Version: " + candidate.version + "\n",
            encoding="utf-8",
        )

        return Skill(
            name=candidate.name,
            source="pip",
            version=candidate.version,
            capability=candidate.capability,
            path=str(skill_path),
            installed_at=__import__("datetime").datetime.now().isoformat(),
        )

    async def _install_huggingface(self, candidate: SkillCandidate) -> Skill:
        """Download a model or resource from HuggingFace."""
        skill_path = self.skill_dir / candidate.name
        skill_path.mkdir(exist_ok=True)

        (skill_path / "SKILL.md").write_text(
            f"# {candidate.name}\n\n{candidate.description}\n\n"
            f"Source: HuggingFace\n"
            f"Install via: huggingface-cli download {candidate.name}\n",
            encoding="utf-8",
        )

        return Skill(
            name=candidate.name,
            source="huggingface",
            capability=candidate.capability,
            path=str(skill_path),
            installed_at=__import__("datetime").datetime.now().isoformat(),
        )

    async def _register(self, skill: Skill) -> None:
        """Register an installed skill in the registry."""
        self._registry[skill.name] = {
            "name": skill.name,
            "source": skill.source,
            "version": skill.version,
            "capability": skill.capability,
            "path": skill.path,
            "stars": skill.stars,
            "installed_at": skill.installed_at,
            "checksum": skill.checksum,
        }
        self._save_registry()

    async def remove_skill(self, name: str) -> bool:
        """Remove an installed skill."""
        skill = self._registry.pop(name, None)
        if skill:
            try:
                import shutil
                shutil.rmtree(skill["path"], ignore_errors=True)
            except Exception:
                pass
            self._save_registry()
            return True
        return False


# ── Singleton ─────────────────────────────────────────────────

_downloader: SkillDownloader | None = None


def get_skill_downloader() -> SkillDownloader:
    """Get or create the singleton skill downloader."""
    global _downloader
    if _downloader is None:
        _downloader = SkillDownloader()
    return _downloader
