"""
Local integration agent (OS v1): loopback HTTP only.

Supported: webhook + rest_api against local URLs, and local_log
(append to the OS workspace). Cloud providers (Telegram, GitHub, Gmail,
Slack, ...) were removed — the OS never calls external services.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.agents.base import BaseAgent
from core.contracts import DecisionRecord, TaskResult
from core.policy import Decision


@dataclass
class IntegrationResult:
    """Structured integration operation result."""

    status: str
    integration: str
    action: str
    result_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: float = 0.0
    external_action: bool = False


def _is_loopback(url: str) -> bool:
    lowered = url.strip().lower()
    return lowered.startswith(("http://127.0.0.1", "https://127.0.0.1", "http://localhost", "https://localhost"))


class IntegrationAgent(BaseAgent):
    """
    Local integration agent. Webhook/rest_api targets must be loopback
    URLs; anything else is refused honestly. local_log writes inside the
    OS workspace.
    """

    SUPPORTED_INTEGRATIONS: ClassVar[list[str]] = [
        "webhook",
        "rest_api",
        "local_log",
    ]

    def __init__(
        self,
        description: str = "",
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            "integration",
            name="IntegrationAgent",
            description=description,
            context=context,
            **kwargs,
        )

    @property
    def capabilities(self) -> tuple[str, ...]:
        if self._is_production_mode():
            return tuple(self.SUPPORTED_INTEGRATIONS)
        return ("external_message", "receive_data", "sync_data", "webhook_delivery")

    def execute(self) -> dict[str, Any]:
        """Execute a local integration task."""
        import time

        started = time.monotonic()

        integration = self.context.get("integration")
        action = self.context.get("action")
        approved = self.context.get("approved", False)

        if not integration:
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "error": "No integration specified",
                        "supported": self.SUPPORTED_INTEGRATIONS,
                    },
                ).as_dict(),
                started,
            )

        if integration not in self.SUPPORTED_INTEGRATIONS:
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "error": f"Integration '{integration}' not supported (OS v1 is local-only)",
                        "supported": self.SUPPORTED_INTEGRATIONS,
                    },
                ).as_dict(),
                started,
            )

        # Simulation mode
        if self._is_simulation_only():
            return self._simulate(integration, action, started)

        # Check approval
        decision = self.policy.evaluate(
            "external_message",
            approval=approved,
        )
        if decision.decision in (Decision.DENY, Decision.SIMULATE):
            record = DecisionRecord(
                "external_integration",
                ["approval_required"],
                decision.reason,
                None,
                "Grant approved=True in context to enable local integrations.",
                False,
                decision.decision.value,
            )
            return self.finalize(
                TaskResult(
                    "requires_approval",
                    {
                        "integration": integration,
                        "action": action,
                        "explanation": decision.reason,
                    },
                    decision=record,
                ).as_dict(),
                started,
            )

        # Route to handler
        handlers = {
            "webhook": self._webhook_handler,
            "rest_api": self._rest_api_handler,
            "local_log": self._local_log_handler,
        }

        handler = handlers.get(integration)
        if handler:
            return awaitResult(handler, integration, action, started)
        else:
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": f"Handler not implemented for {integration}",
                    },
                ).as_dict(),
                started,
            )

    def _is_simulation_only(self) -> bool:
        import os

        return os.getenv("OSS_WORK_SIMULATION_ONLY", "1") == "1"

    def _is_production_mode(self) -> bool:
        return not self._is_simulation_only()

    async def _webhook_handler(self, integration: str, action: str, started: float) -> dict[str, Any]:
        """Deliver a webhook to a loopback URL only."""
        import time

        import httpx

        url = self.context.get("url")
        if not url:
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": "url required for webhook",
                    },
                ).as_dict(),
                started,
            )
        if not _is_loopback(url):
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": f"Only loopback URLs allowed, got: {url!r}",
                    },
                ).as_dict(),
                started,
            )

        payload = self.context.get("payload", {})
        headers = self.context.get("headers", {})
        method = self.context.get("method", "POST").upper()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.request(
                    method=method,
                    url=url,
                    json=payload,
                    headers=headers,
                )
                elapsed = (time.monotonic() - started) * 1000
                return self.finalize(
                    TaskResult(
                        "completed",
                        {
                            "integration": integration,
                            "action": action,
                            "url": url,
                            "method": method,
                            "response_code": r.status_code,
                            "response_body": r.text[:500] if r.text else "",
                            "external_action": False,
                            "elapsed_ms": round(elapsed, 2),
                        },
                    ).as_dict(),
                    started,
                )
        except Exception as e:
            logger.exception("Unhandled exception in integration_agent.py")
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": f"Webhook delivery failed: {e}",
                    },
                ).as_dict(),
                started,
            )

    async def _rest_api_handler(self, integration: str, action: str, started: float) -> dict[str, Any]:
        """Call a loopback REST API."""
        import time

        import httpx

        url = self.context.get("url")
        if not url:
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": "url required for rest_api",
                    },
                ).as_dict(),
                started,
            )
        if not _is_loopback(url):
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": f"Only loopback URLs allowed, got: {url!r}",
                    },
                ).as_dict(),
                started,
            )

        method = self.context.get("method", "GET").upper()
        body = self.context.get("body")
        headers = self.context.get("headers", {})
        params = self.context.get("params", {})
        timeout = self.context.get("timeout", 30)

        try:
            async with httpx.AsyncClient(timeout=timeout, **({"headers": headers} if headers else {})) as client:
                request_kwargs: dict[str, Any] = {
                    "method": method,
                    "url": url,
                    "timeout": timeout,
                }
                if headers:
                    request_kwargs["headers"] = headers
                if params:
                    request_kwargs["params"] = params
                if body is not None:
                    request_kwargs["json"] = body

                r = await client.request(**request_kwargs)
                elapsed = (time.monotonic() - started) * 1000
                try:
                    data = r.json()
                except Exception as _exc:
                    logger.exception("Unhandled exception in integration_agent.py")
                    data = r.text[:1000] if r.text else ""
                return self.finalize(
                    TaskResult(
                        "completed",
                        {
                            "integration": integration,
                            "action": action,
                            "url": url,
                            "method": method,
                            "status_code": r.status_code,
                            "response": data,
                            "elapsed_ms": round(elapsed, 2),
                        },
                    ).as_dict(),
                    started,
                )
        except Exception as e:
            logger.exception("Unhandled exception in integration_agent.py")
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": f"API call failed: {e}",
                    },
                ).as_dict(),
                started,
            )

    async def _local_log_handler(self, integration: str, action: str, started: float) -> dict[str, Any]:
        """Append a line to a log file inside the OS workspace."""
        import os
        import time

        from ossys import config as os_config

        name = str(self.context.get("file", "integrations.log"))
        line = str(self.context.get("text", action or "event"))
        base = os.path.abspath(os_config.workspace_dir())
        os.makedirs(base, exist_ok=True)
        target = os.path.abspath(os.path.join(base, name))
        if target != base and not target.startswith(base + os.sep):
            return self.finalize(
                TaskResult(
                    "failed",
                    {
                        "integration": integration,
                        "action": action,
                        "error": f"Path escapes workspace: {name!r}",
                    },
                ).as_dict(),
                started,
            )
        with open(target, "a", encoding="utf-8") as fh:  # noqa: ASYNC230 - single append, preserves sync agent API
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        elapsed = (time.monotonic() - started) * 1000
        return self.finalize(
            TaskResult(
                "completed",
                {
                    "integration": integration,
                    "action": action,
                    "path": target,
                    "external_action": False,
                    "elapsed_ms": round(elapsed, 2),
                },
            ).as_dict(),
            started,
        )

    def _simulate(self, integration: str, action: str | None, started: float) -> dict[str, Any]:
        """Simulation-mode fallback."""
        from core.contracts import DecisionRecord

        resolved_action = action or integration
        return self.finalize(
            TaskResult(
                "simulated",
                {
                    "integration": integration,
                    "action": resolved_action,
                    "note": f"No local request attempted for {integration}.{resolved_action}. "
                    f"Set OSS_WORK_SIMULATION_ONLY=0 and grant approval to enable.",
                },
                decision=DecisionRecord(
                    classification="integration_simulation",
                    source_signals=["simulation_only"],
                    explanation="No local request attempted — simulation mode active.",
                    confidence=0.0,
                    recommended_human_action="Set OSS_WORK_SIMULATION_ONLY=0 and grant approval.",
                    external_action_attempted=False,
                    policy_decision="deny",
                ),
            ).as_dict(),
            started,
        )


async def awaitResult(coro, *args, **kwargs):
    """Run async coroutine and return dict from sync context."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro(*args, **kwargs))
    return asyncio.run(coro(*args, **kwargs))
