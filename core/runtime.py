"""
OSS Work — Unified Runtime Entry Point (local only).

Runs the agent on this machine: desktop CLI or local API.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

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
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """Main entry point — runs the agent in the configured desktop mode."""
    config = load_config()
    processor = TaskProcessor(config)

    mode = config.mode
    print("\n🚀 OSS Work v1.0.0-dev")
    print_status_box(config)
    print()

    if mode == "desktop":
        if config.desktop_mode == "api" or config.api_enabled:
            DesktopAPIMode(config, processor).start()
        else:
            DesktopCLIMode(config, processor).start()

    else:
        print(f"❌ وضع غير معروف: {mode}")
        print("   الوضع الوحيد: desktop")
        print("   ضع OSS_WORK_MODE=desktop في .env")
        sys.exit(1)


if __name__ == "__main__":
    main()
