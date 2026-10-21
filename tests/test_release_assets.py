"""The release itself: the claims have to match the code.

The specification is explicit that a marketing phrase becomes a release only
when it is tied to a number, and the team rule is that the README has to be
honest. These tests check the claims in the repository against the code.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from osv1.agents.domains import DOMAINS
from osv1.agents.registry import AGENTS, REGISTRY
from osv1.agents.specializations import SPECIALIZATIONS

ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_the_agent_count_in_the_readme_is_the_real_one() -> None:
    readme = _read("README.md")
    assert "300" in readme
    assert len(AGENTS) == 300
    assert len(DOMAINS) == 30
    assert len(SPECIALIZATIONS) == 10


def test_the_readme_documents_the_real_entry_points() -> None:
    readme = _read("README.md")
    assert "oss-v1" in readme
    assert "osv1.interface.api" in readme or "oss-v1-api" in readme
    assert "python -m pytest" in readme


def test_every_api_endpoint_in_the_prd_exists_in_the_code() -> None:
    prd = _read("PRD.md")
    api = _read("osv1/interface/api.py")
    tree = ast.parse(api)
    routes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if (
                    isinstance(deco, ast.Call)
                    and isinstance(deco.func, ast.Attribute)
                    and isinstance(deco.func.value, ast.Name)
                    and deco.func.value.id == "app"
                    and deco.args
                    and isinstance(deco.args[0], ast.Constant)
                ):
                    routes.add(str(deco.args[0].value))
    assert routes
    for route in routes:
        assert route in prd, f"{route} is missing from the PRD"


def test_no_secret_is_committed() -> None:
    pattern = re.compile(r"sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}")
    skip = {".git", "__pycache__", "data-osv1", "node_modules", ".pytest_cache", "workspace"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.suffix.lower() in (".png", ".jpg", ".ico", ".icns", ".zip", ".gguf", ".pdf"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert not pattern.search(text), f"a credential-looking string is in {path}"


def test_the_environment_template_has_no_real_values() -> None:
    text = _read(".env.example")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.endswith("_KEY") or name.endswith("_TOKEN") or name.endswith("_PASSWORD"):
            assert value in ("", "CHANGE-ME"), f"{name} holds a value"


def test_the_package_exposes_the_documented_entry_points() -> None:
    pyproject = _read("pyproject.toml")
    assert 'oss-v1 = "osv1.interface.cli:main"' in pyproject
    assert 'oss-v1-api = "osv1.interface.api:main"' in pyproject


def test_the_catalog_and_the_registry_agree() -> None:
    catalog = REGISTRY.catalog()
    assert catalog["total"] == len(AGENTS)
    assert sum(catalog["by_domain"].values()) == len(AGENTS)
    assert sum(catalog["by_specialization"].values()) == len(AGENTS)


def test_the_live_console_is_served_from_the_package() -> None:
    page = ROOT / "osv1" / "interface" / "web" / "index.html"
    assert page.is_file()
    text = page.read_text(encoding="utf-8")
    assert "EventSource" in text
    assert "/events" in text


@pytest.mark.parametrize("folder", ["core", "ossys", "interfaces", "memory", "db", "web"])
def test_the_removed_folders_are_gone(folder: str) -> None:
    """The old implementation is removed, not left beside the new one."""
    assert not (ROOT / folder).exists(), f"{folder} still exists"
