"""
Browser Agent — Real Playwright automation.
Replaces the simulation-only stub with genuine browser control.

Capabilities (when approved):
- Navigate to URLs
- Scrape page content
- Fill and submit forms
- Take screenshots
- Click elements
- Extract links
- Query AI models via web UI (zero API cost)
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.agents.base import BaseAgent
from core.contracts import DecisionRecord, TaskResult
from core.policy import Decision


# ── Model URLs for browser-based AI queries ──────────────────

MODEL_URLS = {
    "gemini":     "https://gemini.google.com",
    "chatgpt":    "https://chat.openai.com",
    "claude":     "https://claude.ai",
    "kimi":       "https://kimi.moonshot.cn",
    "qwen":       "https://tongyi.aliyun.com",
    "grok":       "https://x.com/i/grok",
    "perplexity": "https://perplexity.ai",
}

# These selectors would be customized per model in production
INPUT_SELECTORS = {
    "gemini":     "textarea",
    "chatgpt":    "textarea",
    "claude":     "textarea",
    "kimi":       "textarea",
}

RESPONSE_SELECTORS = {
    "gemini":     "[data-test-id='chat-message']",
    "chatgpt":    "[data-testid='conversation-turn']",
    "claude":     "[data-testid='message']",
    "kimi":       ".stream-container",
}


@dataclass
class BrowserResult:
    """Structured browser operation result."""
    status: str
    action: str
    url: str | None = None
    title: str | None = None
    content: str | None = None
    screenshot_b64: str | None = None
    screenshot_size: int = 0
    links: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_ms: float = 0.0


class BrowserAgent(BaseAgent):
    """
    Real browser agent using Playwright.
    
    When OSS_WORK_SIMULATION_ONLY=1 or approval is not granted,
    operates in simulation mode (existing behavior).
    
    When approved and Playwright is available:
    - Launches real browser
    - Navigates, scrapes, clicks, fills forms
    - Takes screenshots
    - Queries AI models via web UI
    """

    def __init__(
        self,
        description: str = "",
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            "browser",
            name="BrowserAgent",
            description=description,
            context=context,
            **kwargs,
        )
        self._playwright = None
        self._browser = None

    @property
    def capabilities(self) -> tuple[str, ...]:
        if self._is_production_mode():
            return (
                "browser_control",
                "navigate",
                "scrape",
                "form_fill",
                "screenshot",
                "click",
                "extract_links",
                "ai_model_query",
            )
        return ("browser_control", "scrape_simulation", "form_preview")

    def execute(self) -> dict[str, Any]:
        """Execute a browser task."""
        import time
        started = time.monotonic()

        task = str(self.context.get("task", "navigate"))
        url = self.context.get("url")
        approved = self.context.get("approved", False)

        # Check simulation mode
        if self._is_simulation_only():
            return self._simulate(task, url, started)

        # Check approval gate
        decision = self.policy.evaluate(
            "browser_control",
            approval=approved,
        )
        if decision.decision == Decision.DENY:
            record = DecisionRecord(
                "browser_control",
                ["policy_deny", "approval_required"],
                decision.reason,
                None,
                "Grant approval in context to enable browser control.",
                False,
                decision.decision.value,
            )
            return self.finalize(
                TaskResult("requires_approval", {
                    "action": task,
                    "url": url,
                    "explanation": decision.reason,
                }, decision=record).as_dict(),
                started,
            )

        # Real execution
        try:
            from playwright.async_api import async_playwright
            result = asyncio_run(self._launch_and_execute(task, url, started))
            return result
        except ImportError:
            return self._simulate(task, url, started)
        except Exception as e:
            return self.finalize(
                TaskResult("failed", {
                    "action": task,
                    "url": url,
                    "error": str(e),
                }).as_dict(),
                started,
            )


    def _is_simulation_only(self) -> bool:
        """Check if running in simulation-only mode."""
        import os
        return os.getenv("OSS_WORK_SIMULATION_ONLY", "1") == "1"

    def _is_production_mode(self) -> bool:
        """Check if Playwright is available and not in simulation mode."""
        try:
            import playwright.async_api  # noqa: F401
            return not self._is_simulation_only()
        except ImportError:
            return False

    async def _execute_task(
        self, task: str, url: str | None, started: float, *, browser=None
    ) -> dict[str, Any]:
        """Execute the actual browser task."""
        import asyncio
        import time

        b = browser or self._browser
        if b is None:
            raise RuntimeError("No browser available")
        page = await b.new_page()
        elapsed = 0.0

        try:
            if task == "navigate":
                result = await self._navigate(page, url, started)
            elif task == "scrape":
                result = await self._scrape(page, url, self.context.get("selector", "body"), started)
            elif task == "fill_form":
                result = await self._fill_form(page, url, started)
            elif task == "screenshot":
                result = await self._screenshot(page, url, started)
            elif task == "click":
                result = await self._click(page, url, self.context.get("selector"), started)
            elif task == "extract_links":
                result = await self._extract_links(page, url, started)
            elif task == "ai_model_query":
                result = await self._ai_browser_query(page, started)
            else:
                result = self._unknown_task(task, url, started)
        finally:
            await page.close()

        return result

    async def _navigate(self, page, url: str | None, started: float) -> dict[str, Any]:
        """Navigate to a URL and return page info."""
        import time
        if not url:
            return self.finalize(
                TaskResult("failed", {"error": "No URL provided for navigation"}).as_dict(),
                started,
            )

        await page.goto(url, wait_until="networkidle", timeout=30000)
        elapsed = (time.monotonic() - started) * 1000
        title = await page.title()

        return self.finalize(
            TaskResult("completed", {
                "action": "navigate",
                "url": page.url,
                "title": title,
                "status": "navigated",
                "elapsed_ms": round(elapsed, 2),
            }).as_dict(),
            started,
        )

    async def _scrape(
        self, page, url: str | None, selector: str, started: float
    ) -> dict[str, Any]:
        """Scrape content from a page."""
        import time
        if not url:
            return self.finalize(
                TaskResult("failed", {"error": "No URL provided for scraping"}).as_dict(),
                started,
            )

        await page.goto(url, wait_until="networkidle", timeout=30000)
        content = await page.inner_text(selector)
        elapsed = (time.monotonic() - started) * 1000

        # Truncate large content
        truncated = content[:10000] + ("..." if len(content) > 10000 else "")

        return self.finalize(
            TaskResult("completed", {
                "action": "scrape",
                "url": page.url,
                "selector": selector,
                "content": truncated,
                "full_length": len(content),
                "elapsed_ms": round(elapsed, 2),
            }).as_dict(),
            started,
        )

    async def _fill_form(self, page, url: str | None, started: float) -> dict[str, Any]:
        """Fill and optionally submit a form."""
        import time
        if not url:
            return self.finalize(
                TaskResult("failed", {"error": "No URL provided"}).as_dict(),
                started,
            )

        await page.goto(url, wait_until="networkidle", timeout=30000)
        fields = self.context.get("fields", {})
        submit_selector = self.context.get("submit")

        for field_selector, value in fields.items():
            try:
                await page.fill(field_selector, str(value))
            except Exception as e:
                return self.finalize(
                    TaskResult("failed", {
                        "action": "fill_form",
                        "error": f"Failed to fill field {field_selector}: {e}",
                    }).as_dict(),
                    started,
                )

        if submit_selector:
            try:
                await page.click(submit_selector)
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                return self.finalize(
                    TaskResult("failed", {
                        "action": "fill_form",
                        "error": f"Failed to submit: {e}",
                    }).as_dict(),
                    started,
                )

        elapsed = (time.monotonic() - started) * 1000
        return self.finalize(
            TaskResult("completed", {
                "action": "fill_form",
                "fields_filled": list(fields.keys()),
                "submitted": bool(submit_selector),
                "elapsed_ms": round(elapsed, 2),
            }).as_dict(),
            started,
        )

    async def _screenshot(self, page, url: str | None, started: float) -> dict[str, Any]:
        """Take a screenshot of a page."""
        import time
        if not url:
            return self.finalize(
                TaskResult("failed", {"error": "No URL provided"}).as_dict(),
                started,
            )

        await page.goto(url, wait_until="networkidle", timeout=30000)
        screenshot = await page.screenshot(full_page=True, type="png")
        elapsed = (time.monotonic() - started) * 1000

        b64 = base64.b64encode(screenshot).decode("ascii") if screenshot else None

        return self.finalize(
            TaskResult("completed", {
                "action": "screenshot",
                "url": page.url,
                "screenshot_b64": b64,
                "screenshot_size_bytes": len(screenshot) if screenshot else 0,
                "elapsed_ms": round(elapsed, 2),
            }).as_dict(),
            started,
        )

    async def _click(
        self, page, url: str | None, selector: str | None, started: float
    ) -> dict[str, Any]:
        """Click an element on a page."""
        import time
        if not url or not selector:
            return self.finalize(
                TaskResult("failed", {
                    "error": "URL and selector required for click",
                }).as_dict(),
                started,
            )

        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.click(selector)
        elapsed = (time.monotonic() - started) * 1000

        return self.finalize(
            TaskResult("completed", {
                "action": "click",
                "url": page.url,
                "selector": selector,
                "elapsed_ms": round(elapsed, 2),
            }).as_dict(),
            started,
        )

    async def _extract_links(self, page, url: str | None, started: float) -> dict[str, Any]:
        """Extract all links from a page."""
        import time
        if not url:
            return self.finalize(
                TaskResult("failed", {"error": "No URL provided"}).as_dict(),
                started,
            )

        await page.goto(url, wait_until="networkidle", timeout=30000)
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.href)"
        )
        elapsed = (time.monotonic() - started) * 1000

        # Deduplicate and limit
        unique = list(dict.fromkeys(links))[:100]

        return self.finalize(
            TaskResult("completed", {
                "action": "extract_links",
                "url": page.url,
                "links_count": len(unique),
                "links": unique,
                "elapsed_ms": round(elapsed, 2),
            }).as_dict(),
            started,
        )

    async def _ai_browser_query(self, page, started: float) -> dict[str, Any]:
        """
        Query an AI model via its web interface.
        Zero API cost — uses the model's web UI directly.
        Requires user to be logged into the model's website.
        """
        import time
        model = self.context.get("model", "gemini")
        prompt = self.context.get("prompt", "")

        if not prompt:
            return self.finalize(
                TaskResult("failed", {"error": "No prompt provided for AI query"}).as_dict(),
                started,
            )

        url = MODEL_URLS.get(model)
        if not url:
            return self.finalize(
                TaskResult("failed", {
                    "error": f"Unknown model: {model}. Supported: {list(MODEL_URLS.keys())}",
                }).as_dict(),
                started,
            )

        input_sel = INPUT_SELECTORS.get(model, "textarea")
        resp_sel = RESPONSE_SELECTORS.get(model, ".response")

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.fill(input_sel, prompt)
            await page.press(input_sel, "Enter")

            # Wait for response (model-specific timing)
            try:
                await page.wait_for_selector(resp_sel, timeout=60000)
                response = await page.inner_text(resp_sel)
            except Exception:
                # Response might not have loaded yet
                await asyncio.sleep(5)
                response = await page.inner_text("body")

            elapsed = (time.monotonic() - started) * 1000

            return self.finalize(
                TaskResult("completed", {
                    "action": "ai_model_query",
                    "model": model,
                    "prompt_length": len(prompt),
                    "response_preview": response[:2000],
                    "response_full_length": len(response),
                    "elapsed_ms": round(elapsed, 2),
                }).as_dict(),
                started,
            )
        except Exception as e:
            elapsed = (time.monotonic() - started) * 1000
            return self.finalize(
                TaskResult("failed", {
                    "action": "ai_model_query",
                    "model": model,
                    "error": str(e),
                    "note": "Ensure you are logged into the model's website in the browser.",
                    "elapsed_ms": round(elapsed, 2),
                }).as_dict(),
                started,
            )

    async def _launch_and_execute(self, task: str, url: str | None, started: float) -> dict[str, Any]:
        """Launch browser and execute task — async entry point from sync execute()."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.context.get("headless", True),
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            try:
                result = await self._execute_task(task, url, started, browser=browser)
            finally:
                await browser.close()
        return result

    def _unknown_task(self, task: str, url: str | None, started: float) -> dict[str, Any]:
        """Handle unknown browser tasks."""
        return self.finalize(
            TaskResult("failed", {
                "action": task,
                "url": url,
                "error": f"Unknown browser task: {task}",
                "supported_tasks": [
                    "navigate", "scrape", "fill_form", "screenshot",
                    "click", "extract_links", "ai_model_query",
                ],
            }).as_dict(),
            started,
        )

    def _simulate(self, task: str, url: str | None, started: float) -> dict[str, Any]:
        """Simulation-mode fallback."""
        from core.contracts import DecisionRecord

        return self.finalize(
            TaskResult(
                "simulated",
                {
                    "action": task,
                    "url": url,
                    "note": "No browser session attempted. Set OSS_WORK_SIMULATION_ONLY=0 and grant approval to enable real browser control. Requires Playwright installation.",
                    "simulated": True,
                    "tool": "playwright",
                },
                decision=DecisionRecord(
                    classification="browser_control_simulation",
                    source_signals=["simulation_only_mode", "playwright_unavailable"],
                    explanation="No browser session attempted — simulation mode active. Requires OSS_WORK_SIMULATION_ONLY=0 and approval to enable real browser control.",
                    confidence=0.0,
                    recommended_human_action="Set OSS_WORK_SIMULATION_ONLY=0, install Playwright, and grant approval.",
                    external_action_attempted=False,
                    policy_decision="deny",
                ),
            ).as_dict(),
            started,
        )

    async def close(self) -> None:
        """Clean up browser resources."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.__aexit__(None, None, None)
            except Exception:
                pass
            self._playwright = None


# ── Async helper for sync contexts ───────────────────────────

async def _async_run(coro):
    """Run a coroutine and return its result."""
    return await coro


def asyncio_run(coro):
    """Run an async coroutine from a sync context."""
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        return asyncio.run(coro)
    except Exception:
        return None

