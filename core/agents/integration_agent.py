"""
External service facade kept simulation-only until each provider is commissioned.
REWRITTEN: Real integration agent with Telegram, GitHub, webhooks, REST APIs.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

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


class IntegrationAgent(BaseAgent):
    """
    Real integration agent for external services.
    When OSS_WORK_SIMULATION_ONLY=1 or approval not granted: simulation mode.
    When approved and configured: Telegram, GitHub, webhooks, REST APIs.
    """

    SUPPORTED_INTEGRATIONS = [
        "telegram", "github", "webhook", "rest_api",
        "gmail", "google_calendar", "google_drive",
        "whatsapp", "slack", "notion",
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
        """Execute an integration task."""
        import time
        started = time.monotonic()

        integration = self.context.get("integration")
        action = self.context.get("action")
        approved = self.context.get("approved", False)

        if not integration:
            return self.finalize(
                TaskResult("failed", {
                    "error": "No integration specified",
                    "supported": self.SUPPORTED_INTEGRATIONS,
                }).as_dict(),
                started,
            )

        if integration not in self.SUPPORTED_INTEGRATIONS:
            return self.finalize(
                TaskResult("failed", {
                    "error": f"Integration '{integration}' not supported yet",
                    "supported": self.SUPPORTED_INTEGRATIONS,
                }).as_dict(),
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
                "Grant approved=True in context to enable external integrations.",
                False,
                decision.decision.value,
            )
            return self.finalize(
                TaskResult("requires_approval", {
                    "integration": integration,
                    "action": action,
                    "explanation": decision.reason,
                }, decision=record).as_dict(),
                started,
            )

        # Route to handler
        handlers = {
            "telegram": self._telegram_handler,
            "github": self._github_handler,
            "webhook": self._webhook_handler,
            "rest_api": self._rest_api_handler,
        }

        handler = handlers.get(integration)
        if handler:
            return awaitResult(handler, integration, action, started)
        else:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": f"Handler not implemented for {integration}",
                }).as_dict(),
                started,
            )

    def _is_simulation_only(self) -> bool:
        import os
        return os.getenv("OSS_WORK_SIMULATION_ONLY", "1") == "1"

    def _is_production_mode(self) -> bool:
        return not self._is_simulation_only()

    async def _telegram_handler(
        self, integration: str, action: str, started: float
    ) -> dict[str, Any]:
        """Handle Telegram integration — send messages, documents, photos."""
        import time
        from telegram import Bot

        token = self.context.get("telegram_token")
        chat_id = self.context.get("chat_id")

        if not token:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": "telegram_token not configured",
                }).as_dict(),
                started,
            )

        bot = Bot(token=token)

        if action == "send_message":
            text = self.context.get("text", "")
            parse_mode = self.context.get("parse_mode", "HTML")
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                )
                elapsed = (time.monotonic() - started) * 1000
                return self.finalize(
                    TaskResult("completed", {
                        "integration": integration,
                        "action": action,
                        "message_id": msg.message_id,
                        "chat_id": chat_id,
                        "text_preview": text[:200],
                        "external_action": True,
                        "elapsed_ms": round(elapsed, 2),
                    }).as_dict(),
                    started,
                )
            except Exception as e:
                return self.finalize(
                    TaskResult("failed", {
                        "integration": integration,
                        "action": action,
                        "error": f"Telegram API error: {e}",
                    }).as_dict(),
                    started,
                )

        elif action == "send_document":
            file_path = self.context.get("file_path")
            caption = self.context.get("caption", "")
            if not file_path:
                return self.finalize(
                    TaskResult("failed", {
                        "integration": integration,
                        "action": action,
                        "error": "file_path required for send_document",
                    }).as_dict(),
                    started,
                )
            try:
                with open(file_path, "rb") as f:
                    doc = await bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        caption=caption,
                    )
                elapsed = (time.monotonic() - started) * 1000
                return self.finalize(
                    TaskResult("completed", {
                        "integration": integration,
                        "action": action,
                        "document_file_id": doc.document.file_id,
                        "chat_id": chat_id,
                        "caption": caption,
                        "external_action": True,
                        "elapsed_ms": round(elapsed, 2),
                    }).as_dict(),
                    started,
                )
            except Exception as e:
                return self.finalize(
                    TaskResult("failed", {
                        "integration": integration,
                        "action": action,
                        "error": f"Telegram document error: {e}",
                    }).as_dict(),
                    started,
                )

        elif action == "send_photo":
            file_path = self.context.get("file_path")
            caption = self.context.get("caption", "")
            if not file_path:
                return self.finalize(
                    TaskResult("failed", {
                        "integration": integration,
                        "action": action,
                        "error": "file_path required for send_photo",
                    }).as_dict(),
                    started,
                )
            try:
                with open(file_path, "rb") as f:
                    photo = await bot.send_photo(
                        chat_id=chat_id,
                        photo=f,
                        caption=caption,
                    )
                elapsed = (time.monotonic() - started) * 1000
                return self.finalize(
                    TaskResult("completed", {
                        "integration": integration,
                        "action": action,
                        "photo_file_id": photo.photo[-1].file_id,
                        "chat_id": chat_id,
                        "external_action": True,
                        "elapsed_ms": round(elapsed, 2),
                    }).as_dict(),
                    started,
                )
            except Exception as e:
                return self.finalize(
                    TaskResult("failed", {
                        "integration": integration,
                        "action": action,
                        "error": f"Telegram photo error: {e}",
                    }).as_dict(),
                    started,
                )

        else:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": f"Unknown Telegram action: {action}. Supported: send_message, send_document, send_photo",
                }).as_dict(),
                started,
            )

    async def _github_handler(
        self, integration: str, action: str, started: float
    ) -> dict[str, Any]:
        """Handle GitHub integration — create issues, push files, create PRs."""
        import time
        import httpx

        token = self.context.get("github_token")
        if not token:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": "github_token not configured",
                }).as_dict(),
                started,
            )

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
            if action == "create_issue":
                owner = self.context.get("owner", "Osama-SysEng")
                repo = self.context.get("repo", "oss-work-universal-ai-agent")
                title = self.context.get("title", "")
                body = self.context.get("body", "")
                labels = self.context.get("labels", [])
                if not title:
                    return self.finalize(
                        TaskResult("failed", {
                            "integration": integration,
                            "action": action,
                            "error": "title required for create_issue",
                        }).as_dict(),
                        started,
                    )
                url = f"https://api.github.com/repos/{owner}/{repo}/issues"
                r = await client.post(url, json={"title": title, "body": body, "labels": labels})
                if r.status_code == 201:
                    issue = r.json()
                    elapsed = (time.monotonic() - started) * 1000
                    return self.finalize(
                        TaskResult("completed", {
                            "integration": integration,
                            "action": action,
                            "issue_number": issue["number"],
                            "issue_url": issue["html_url"],
                            "title": title,
                            "external_action": True,
                            "elapsed_ms": round(elapsed, 2),
                        }).as_dict(),
                        started,
                    )
                else:
                    return self.finalize(
                        TaskResult("failed", {
                            "integration": integration,
                            "action": action,
                            "error": f"GitHub API error {r.status_code}: {r.text[:200]}",
                        }).as_dict(),
                        started,
                    )

            elif action == "create_file":
                owner = self.context.get("owner", "Osama-SysEng")
                repo = self.context.get("repo", "oss-work-universal-ai-agent")
                path = self.context.get("path", "")
                content = self.context.get("content", "")
                message = self.context.get("commit_message", "Add file via OSS Work")
                if not path or not content:
                    return self.finalize(
                        TaskResult("failed", {
                            "integration": integration,
                            "action": action,
                            "error": "path and content required for create_file",
                        }).as_dict(),
                        started,
                    )
                content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
                url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
                r = await client.put(url, json={
                    "message": message,
                    "content": content_b64,
                })
                if r.status_code in (200, 201):
                    data = r.json()
                    elapsed = (time.monotonic() - started) * 1000
                    return self.finalize(
                        TaskResult("completed", {
                            "integration": integration,
                            "action": action,
                            "path": path,
                            "sha": data.get("content", {}).get("sha", ""),
                            "url": data.get("content", {}).get("html_url", ""),
                            "commit_message": message,
                            "external_action": True,
                            "elapsed_ms": round(elapsed, 2),
                        }).as_dict(),
                        started,
                    )
                else:
                    return self.finalize(
                        TaskResult("failed", {
                            "integration": integration,
                            "action": action,
                            "error": f"GitHub API error {r.status_code}: {r.text[:200]}",
                        }).as_dict(),
                        started,
                    )

            elif action == "create_pr":
                owner = self.context.get("owner", "Osama-SysEng")
                repo = self.context.get("repo", "oss-work-universal-ai-agent")
                title = self.context.get("title", "")
                body = self.context.get("body", "")
                head = self.context.get("head", "main")
                base = self.context.get("base", "main")
                if not title:
                    return self.finalize(
                        TaskResult("failed", {
                            "integration": integration,
                            "action": action,
                            "error": "title required for create_pr",
                        }).as_dict(),
                        started,
                    )
                url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
                r = await client.post(url, json={"title": title, "body": body, "head": head, "base": base})
                if r.status_code == 201:
                    pr = r.json()
                    elapsed = (time.monotonic() - started) * 1000
                    return self.finalize(
                        TaskResult("completed", {
                            "integration": integration,
                            "action": action,
                            "pr_number": pr["number"],
                            "pr_url": pr["html_url"],
                            "title": title,
                            "external_action": True,
                            "elapsed_ms": round(elapsed, 2),
                        }).as_dict(),
                        started,
                    )
                else:
                    return self.finalize(
                        TaskResult("failed", {
                            "integration": integration,
                            "action": action,
                            "error": f"GitHub API error {r.status_code}: {r.text[:200]}",
                        }).as_dict(),
                        started,
                    )

            else:
                return self.finalize(
                    TaskResult("failed", {
                        "integration": integration,
                        "action": action,
                        "error": f"Unknown GitHub action: {action}. Supported: create_issue, create_file, create_pr",
                    }).as_dict(),
                    started,
                )

    async def _webhook_handler(
        self, integration: str, action: str, started: float
    ) -> dict[str, Any]:
        """Handle webhook delivery."""
        import time
        import httpx

        url = self.context.get("url")
        if not url:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": "url required for webhook",
                }).as_dict(),
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
                    TaskResult("completed", {
                        "integration": integration,
                        "action": action,
                        "url": url,
                        "method": method,
                        "response_code": r.status_code,
                        "response_body": r.text[:500] if r.text else "",
                        "external_action": True,
                        "elapsed_ms": round(elapsed, 2),
                    }).as_dict(),
                    started,
                )
        except Exception as e:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": f"Webhook delivery failed: {e}",
                }).as_dict(),
                started,
            )

    async def _rest_api_handler(
        self, integration: str, action: str, started: float
    ) -> dict[str, Any]:
        """Handle generic REST API calls."""
        import time
        import httpx

        url = self.context.get("url")
        if not url:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": "url required for rest_api",
                }).as_dict(),
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
                except Exception:
                    data = r.text[:1000] if r.text else ""
                return self.finalize(
                    TaskResult("completed", {
                        "integration": integration,
                        "action": action,
                        "url": url,
                        "method": method,
                        "status_code": r.status_code,
                        "response": data,
                        "elapsed_ms": round(elapsed, 2),
                    }).as_dict(),
                    started,
                )
        except Exception as e:
            return self.finalize(
                TaskResult("failed", {
                    "integration": integration,
                    "action": action,
                    "error": f"API call failed: {e}",
                }).as_dict(),
                started,
            )

    def _simulate(
        self, integration: str, action: str | None, started: float
    ) -> dict[str, Any]:
        """Simulation-mode fallback."""
        from core.contracts import DecisionRecord

        resolved_action = action or integration
        return self.finalize(
            TaskResult(
                "simulated",
                {
                    "integration": integration,
                    "action": resolved_action,
                    "note": f"No external request attempted for {integration}.{resolved_action}. "
                            f"Set OSS_WORK_SIMULATION_ONLY=0, configure credentials, "
                            f"and grant approval to enable real integration.",
                },
                decision=DecisionRecord(
                    classification="integration_simulation",
                    source_signals=["simulation_only"],
                    explanation="No external request attempted — simulation mode active.",
                    confidence=0.0,
                    recommended_human_action="Set OSS_WORK_SIMULATION_ONLY=0 and configure credentials to enable real integration.",
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
