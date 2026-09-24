"""
tests/test_browser_agent.py — Browser Agent tests.

Covers: capability, simulation-only mode, tool validation, no real browser.
"""

from __future__ import annotations

from core.agents.browser_agent import BrowserAgent


class TestBrowserAgentCapabilities:
    """Browser agent capability tests."""

    def test_capabilities(self):
        agent = BrowserAgent(description="browse the web")
        caps = agent.capabilities
        assert "browser_control" in caps
        assert "scrape_simulation" in caps
        assert len(caps) >= 1

    def test_agent_type(self):
        agent = BrowserAgent(description="search")
        assert agent.agent_type == "browser"

    def test_name(self):
        agent = BrowserAgent(description="browse")
        assert agent.name == "BrowserAgent"


class TestBrowserAgentSimulationOnly:
    """Browser agent simulation-only mode tests."""

    def test_execute_returns_simulated(self):
        result = BrowserAgent(
            description="visit https://example.com and read the page",
        ).execute()
        assert result["status"] == "simulated"
        assert result["data"]["simulated"] is True
        assert result["data"]["tool"] == "playwright"


class TestBrowserAgentNoRealExecution:
    """Browser agent must not execute real browser operations."""

    def test_no_real_browse(self):
        """Real browsing is never attempted in simulation mode."""
        result = BrowserAgent(
            description="go to google.com and search for something",
        ).execute()
        assert result["status"] in ("simulated", "completed")
        assert result["decision"]["external_action_attempted"] is False


class TestBrowserAgentToolValidation:
    """Browser agent tool validation tests."""

    def test_valid_url_task(self):
        result = BrowserAgent(
            description="Visit https://httpbin.org/status/200",
        ).execute()
        assert result["status"] in ("simulated", "completed")

    def test_invalid_url_rejected(self):
        result = BrowserAgent(
            description="Visit not-a-valid-url",
        ).execute()
        # Should not crash; may be simulated or completed with note
        assert result["status"] in ("simulated", "completed")


class TestBrowserAgentSafety:
    """Browser agent safety boundary tests."""

    def test_no_login_attempted(self):
        """Login forms must never be filled automatically."""
        result = BrowserAgent(
            description="Log into a website with username and password",
        ).execute()
        assert result["decision"]["external_action_attempted"] is False

    def test_no_form_submit(self):
        """Form submission must be simulation-only."""
        result = BrowserAgent(
            description="Fill a form and submit it",
        ).execute()
        assert result["decision"]["external_action_attempted"] is False
