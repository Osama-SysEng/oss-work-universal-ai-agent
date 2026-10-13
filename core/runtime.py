"""
OSS Work — Unified Runtime Entry Point.

This file decides how to run the agent based on the settings:
- telegram: link the agent to Telegram (tasks from the phone to the desktop)
- desktop: run the agent on the desktop without Telegram (like any AI model)
- hybrid: both modes together
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import asyncio
import json
import sys
from typing import Any

from core.config import VERSION, AgentConfig, load_config
from core.processor import TaskProcessor

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def print_header(title: str, width: int = 60) -> None:
    """Print a decorated header."""
    print()
    print("═" * width)
    print(f"  {title}")
    print("═" * width)
    print()


def print_status_box(config: AgentConfig) -> None:
    """Print the status box."""
    print(f"  الوضع:          {config.mode}")
    print(f"  المحاكاة:        {'ON' if config.simulation_only else 'OFF'}")
    if config.telegram_enabled and config.bot_token:
        print(f"  التلجرام:        نشط ({config.bot_username or '@unknown'})")
    if config.api_enabled:
        print(f"  API محلي:        http://{config.api_host}:{config.api_port}")
    print()


# ═══════════════════════════════════════════════════════════════════
# Shared Processor Helper
# ═══════════════════════════════════════════════════════════════════


async def process_task(processor: TaskProcessor, task: str) -> dict[str, Any]:
    """Process a task and display the result."""
    result = await processor.process(task)

    status = result.get("status", "unknown")
    data = result.get("data", {})
    errors = result.get("errors", [])

    if status == "completed":
        print("\n✅ *تم بنجاح:*")
        if data:
            for k, v in data.items():
                key = k.replace("_", " ")
                val = str(v)
                if len(val) > 300:
                    val = val[:300] + "..."
                print(f"   {key}: {val}")
        else:
            print("   لا توجد بيانات.")
    elif status == "failed":
        print(f"\n❌ فشل: {errors[0] if errors else 'خطأ غير معروف'}")
    elif status == "busy":
        print(f"\n⏳ مشغول: {result.get('error', 'مهمة قيد المعالجة')}")
    else:
        print("\n📋 النتيجة:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    print()

    return result


# ═══════════════════════════════════════════════════════════════════
# Desktop CLI Mode
# ═══════════════════════════════════════════════════════════════════


class DesktopCLIMode:
    """
    Run the agent as a standalone CLI on the desktop.

    Without Telegram — like any other AI model.
    Direct interaction via the command line.
    """

    def __init__(self, config: AgentConfig, processor: TaskProcessor):
        self.config = config
        self.processor = processor

    async def start(self) -> None:
        """Run the interactive CLI mode."""
        print_header("OSS Work — Desktop CLI Mode (Standalone Agent)")

        print("  استخدم هذا للاستخدام المحلي دون التلجرام")
        print("  اكتب مهمة واضغط Enter لمعالجتها")
        print("  هذا يعمل مثل أي نموذج ذكاء اصطناعي آخر")
        print()
        print("  أوامر مساعدة:")
        print("    status     — عرض حالة الوكيل")
        print("    clear      — مسح السجل")
        print("    models     — عرض النماذج المتاحة")
        print("    quit / exit — خروج")
        print()

        while True:
            try:
                task = input("📝 المهمة: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Goodbye!")
                break

            if not task:
                continue

            if task.lower() in ("quit", "exit", "خروج", " exit"):
                print("👋 Goodbye!")
                break

            if task.lower() == "status":
                status = self.processor.get_status()
                print("\n📊 الحالة:")
                for k, v in status.items():
                    print(f"   {k}: {v}")
                print()
                continue

            if task.lower() == "clear":
                self.processor.reset()
                print("✅ السجل تم مسحه")
                print()
                continue

            if task.lower() == "models":
                try:
                    from core.services.model_router import get_router

                    router = get_router()
                    print("\n🤖 النماذج المتاحة:")
                    for m in router._model_map.values():
                        print(f"   • {m.name} ({m.provider.value})")
                        print(f"     المجال: {m.category}")
                        if m.browser_url:
                            print(f"     الرابط: {m.browser_url}")
                        print()
                except Exception as e:
                    logger.exception("Unhandled exception in runtime.py")
                    print(f"❌ خطأ: {e}")
                print()
                continue

            # Process the task
            print("⏳ جاري المعالجة...")
            await process_task(self.processor, task)


# ═══════════════════════════════════════════════════════════════════
# Desktop API Mode
# ═══════════════════════════════════════════════════════════════════


class DesktopAPIMode:
    """
    Run the agent as a local API on the desktop.

    Other desktop applications use it via HTTP requests.
    Works like any AI model — send a task, receive a reply.
    """

    def __init__(self, config: AgentConfig, processor: TaskProcessor):
        self.config = config
        self.processor = processor

    async def start(self) -> None:
        """Run the local API."""
        import uvicorn
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel, Field

        app = FastAPI(
            title="OSS Work — Desktop Local API",
            description="API محلي للوكيل — استخدمه مثل أي نموذج ذكاء اصطناعي",
            version=VERSION,
        )

        class TaskRequest(BaseModel):
            task: str = Field(..., min_length=2, max_length=10000)
            user_id: str = Field(default="local")
            context: dict = Field(default_factory=dict)

        class TaskResponse(BaseModel):
            status: str
            data: dict = Field(default_factory=dict)
            errors: list = Field(default_factory=list)
            task_id: str = ""
            latency_ms: float = 0

        @app.get("/health")
        async def health():
            return {"status": "ok", "service": "oss-work-desktop-api"}

        @app.get("/status")
        async def status():
            return self.processor.get_status()

        @app.post("/task", response_model=TaskResponse)
        async def task(request: TaskRequest):
            result = await self.processor.process(request.task, request.user_id)
            return TaskResponse(
                status=result.get("status", "unknown"),
                data=result.get("data", {}),
                errors=result.get("errors", []),
                task_id=result.get("task_id", ""),
                latency_ms=result.get("latency_ms", 0),
            )

        @app.get("/models")
        async def list_models(limit: int = 50, offset: int = 0):
            limit = max(1, min(limit, 500))
            offset = max(0, offset)
            try:
                from core.services.model_router import get_router

                router = get_router()
                all_models = [
                    {
                        "id": m.id,
                        "name": m.name,
                        "provider": m.provider.value,
                        "category": m.category,
                        "context_window": m.context_window,
                        "supports_vision": m.supports_vision,
                        "cost_per_1k_tokens": m.cost_per_1k_tokens,
                        "api_available": m.api_available,
                        "browser_url": m.browser_url,
                    }
                    for m in router._model_map.values()
                ]
                return {
                    "models": all_models[offset : offset + limit],
                    "total": len(all_models),
                    "limit": limit,
                    "offset": offset,
                }
            except Exception as e:
                logger.exception("Unhandled exception in runtime.py")
                raise HTTPException(500, f"فشل: {e}")

        @app.get("/")
        async def root():
            return {
                "service": "OSS Work — Desktop Local API",
                "version": VERSION,
                "endpoints": {
                    "POST /task": "إرسال مهمة",
                    "GET /health": "فحص الحالة",
                    "GET /status": "حالة الوكيل",
                    "GET /models": "عرض النماذج",
                    "/docs": "توثيق API",
                },
            }

        print_header("OSS Work — Desktop API Mode")

        print(f"  API URL:  http://{self.config.api_host}:{self.config.api_port}")
        print(f"  Docs:     http://{self.config.api_host}:{self.config.api_port}/docs")
        print()
        print("  استخدم من أي تطبيق:")
        print()
        print(f"    curl -X POST http://{self.config.api_host}:{self.config.api_port}/task \\")
        print("      -H 'Content-Type: application/json' \\")
        print('      -d \'{"task": "تصميم نظام إشعارات"، "user_id": "تطبيقي"}\'')
        print()
        print("═" * 60)
        print()

        uvicorn.run(
            app,
            host=self.config.api_host,
            port=self.config.api_port,
            log_level="info",
        )


# ═══════════════════════════════════════════════════════════════════
# Telegram Mode
# ═══════════════════════════════════════════════════════════════════


class TelegramMode:
    """
    Run the agent as a Telegram bot — a link between phone and desktop.

    Tasks arrive from the phone via Telegram,
    are processed on the desktop via the shared processor,
    and the results return to the phone via Telegram.
    """

    def __init__(self, config: AgentConfig, processor: TaskProcessor):
        self.config = config
        self.processor = processor

    async def start(self) -> None:
        """Run the Telegram bot."""
        if not self.config.bot_token:
            print("❌ TELEGRAM_BOT_TOKEN غير مضبوط في .env")
            print("   احصل على التوكن من @BotFather على التلجرام")
            print("   ثم أضفه إلى .env: TELEGRAM_BOT_TOKEN=xxx")
            return

        print_header("OSS Work — Telegram Mode (Phone ↔ Desktop Link)")

        print(f"  التوكن:     {self.config.bot_token[:20]}...")
        print(f"  المستخدم:   {self.config.bot_username or '@unknown'}")
        print("  Flow:       tasks from phone -> desktop -> results to phone")
        print(f"  المحاكاة:   {'ON' if self.config.simulation_only else 'OFF'}")

        if self.config.simulation_only:
            print()
            print("  ⚠️  EVERYTHING IS SIMULATED")
            print("     لا تُنفذ أي عمليات حقيقية")
            print()

        print()
        print("  Send /start to the bot on Telegram to start using it")
        print("  أو أرسل أي رسالة مباشرة لمعالجة مهمة")
        print()
        print("═" * 60)
        print()

        # Import and run the bot
        from interfaces.telegram.bot import BotConfig, OSSWorkTelegramBot

        bot_cfg = BotConfig(
            token=self.config.bot_token,
            simulation_only=self.config.simulation_only,
        )
        bot = OSSWorkTelegramBot(config=bot_cfg, processor=self.processor)
        bot.setup()

        await bot.run()


# ═══════════════════════════════════════════════════════════════════
# Hybrid Mode
# ═══════════════════════════════════════════════════════════════════


class HybridMode:
    """Run Telegram and desktop together."""

    def __init__(self, config: AgentConfig, processor: TaskProcessor):
        self.config = config
        self.processor = processor

    async def start(self) -> None:
        """Run the hybrid mode."""
        print_header("OSS Work — Hybrid Mode (Telegram + Desktop)")

        tasks = []

        # Telegram
        if self.config.telegram_enabled and self.config.bot_token:
            from interfaces.telegram.bot import BotConfig, OSSWorkTelegramBot

            bot_cfg = BotConfig(
                token=self.config.bot_token,
                simulation_only=self.config.simulation_only,
            )
            bot = OSSWorkTelegramBot(config=bot_cfg, processor=self.processor)
            bot.setup()

            print("📱 Telegram: active — tasks from phone to desktop")
            tasks.append(bot.run())
        else:
            print("📱 التلغرام: غير مضبوط")

        # Desktop
        if self.config.desktop_mode == "api":
            import uvicorn
            from fastapi import FastAPI
            from pydantic import BaseModel, Field

            app = FastAPI(title="OSS Work Desktop API", version=VERSION)

            class TR(BaseModel):
                task: str = Field(..., min_length=2)
                user_id: str = "local"

            class TResp(BaseModel):
                status: str
                data: dict = Field(default_factory=dict)
                errors: list = Field(default_factory=list)

            @app.post("/task", response_model=TResp)
            async def task(request: TR):
                result = await self.processor.process(request.task, request.user_id)
                return TResp(
                    status=result.get("status", "unknown"),
                    data=result.get("data", {}),
                    errors=result.get("errors", []),
                )

            @app.get("/health")
            async def health():
                return {"status": "ok"}

            print(f"🌐 Desktop API: http://{self.config.api_host}:{self.config.api_port}")
            tasks.append(uvicorn.run(app, host=self.config.api_host, port=self.config.api_port, log_level="info"))
        else:
            print("💻 Desktop CLI: active")

        print()
        print("═" * 60)
        print()

        if not tasks:
            print("❌ لا يوجد وضع مضبوط.")
            print("   أضف TELEGRAM_BOT_TOKEN أو OSS_API_ENABLED=true في .env")
            return

        await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """Main entry point — runs the agent in the configured mode."""
    config = load_config()
    processor = TaskProcessor(config)

    mode = config.mode
    print("\n🚀 OSS Work v1.0.0-dev")
    print_status_box(config)
    print()

    if mode == "telegram":
        TelegramMode(config, processor).start()

    elif mode == "desktop":
        if config.api_enabled:
            DesktopAPIMode(config, processor).start()
        else:
            DesktopCLIMode(config, processor).start()

    elif mode == "hybrid":
        HybridMode(config, processor).start()

    else:
        print(f"❌ وضع غير معروف: {mode}")
        print("   الأوضاع الصحيحة: telegram, desktop, hybrid")
        print("   ضع OSS_WORK_MODE في .env")
        sys.exit(1)


if __name__ == "__main__":
    main()
