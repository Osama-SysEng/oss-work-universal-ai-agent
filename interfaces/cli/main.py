"""
OSS Work — CLI Interface (local only).

واجهة سطر الأوامر للوكيل. وضع سطح المكتب المستقل.

الاستخدام:
    oss-work run              — تشغيل الوكيل بالوضع المضبوط
    oss-work chat "مهمة"     — معالجة مهمة عبر CLI
    oss-work status           — عرض حالة النظام
    oss-work models           — عرض النماذج المتاحة
    oss-work desktop          — تشغيل وضع سطح المكتب فقط
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import asyncio
import json
import os
from pathlib import Path

import typer

from core.config import VERSION, AgentConfig, load_config
from core.imagination.engine import UltraIQEngine
from core.processor import TaskProcessor
from core.services.model_router import get_router
from core.services.updater import get_updater

# ── CLI App ────────────────────────────────────────────────────

app = typer.Typer(
    name="oss-work",
    help="OSS Work — Open-Source Universal AI Agent CLI",
    short_help="Universal AI agent from the command line",
    add_completion=False,
)


# ── Helpers ────────────────────────────────────────────────────


def _run_async(coro):
    """تشغيل coroutine في سياق متزامن."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    return asyncio.run(coro)


def _get_data_dir() -> Path:
    return Path(os.getenv("OSS_WORK_DATA_DIR", "./data"))


def _get_processor() -> TaskProcessor:
    """الحصول على معالج مشترك."""
    return TaskProcessor(load_config())


# ── Commands ────────────────────────────────────────────────────


@app.command(name="run")
def run_cmd() -> None:
    """تشغيل الوكيل بالوضع المضبوط في .env."""
    config = load_config()
    processor = TaskProcessor(config)

    typer.echo(f"\n🚀 OSS Work v{VERSION}")
    typer.echo(f"   الوضع: {config.mode}")
    typer.echo(f"   المحاكاة: {'ON' if config.simulation_only else 'OFF'}")
    typer.echo()

    if config.mode == "desktop":
        if config.api_enabled:
            typer.echo("🌐 تشغيل وضع API المحلي...")
            typer.echo(f"   URL: http://{config.api_host}:{config.api_port}")
            typer.echo(f"   Docs: http://{config.api_host}:{config.api_port}/docs")
            typer.echo()
            import uvicorn

            from interfaces.api.server import app as api_app

            uvicorn.run(api_app, host=config.api_host, port=config.api_port, log_level="info")
        else:
            typer.echo("💻 تشغيل وضع CLI التفاعلي...")
            asyncio.run(DesktopCLIMode(config, processor).start())

    else:
        typer.echo(f"❌ وضع غير معروف: {config.mode}")
        raise typer.Exit(1)


@app.command(name="desktop")
def desktop_cmd() -> None:
    """تشغيل وضع سطح المكتب فقط (بدون تلجرام)."""
    config = load_config()
    processor = TaskProcessor(config)

    typer.echo("\n💻 OSS Work — Desktop Mode")
    typer.echo(f"   الوضع: {config.desktop_mode}")
    typer.echo(f"   المحاكاة: {'ON' if config.simulation_only else 'OFF'}")
    typer.echo()

    if config.api_enabled:
        typer.echo(f"   API URL: http://{config.api_host}:{config.api_port}")
        typer.echo(f"   Docs: http://{config.api_host}:{config.api_port}/docs")
        typer.echo()
        import uvicorn

        from interfaces.api.server import app as api_app

        uvicorn.run(api_app, host=config.api_host, port=config.api_port, log_level="info")
    else:
        asyncio.run(DesktopCLIMode(config, processor).start())


@app.command(name="chat")
def chat_cmd(
    task: str = typer.Argument(..., help="المهمة المراد معالجتها"),
    user: str = typer.Option("local", "--user", "-u", help="معرف المستخدم"),
) -> None:
    """معالجة مهمة عبر CLI (وضع سطح المكتب المستقل)."""
    typer.echo(f"\n🤖 معالجة: {task}")
    typer.echo("---")

    processor = _get_processor()
    result = _run_async(processor.process(task, user))

    status = result.get("status", "unknown")
    data = result.get("data", {})
    errors = result.get("errors", [])

    if status == "completed":
        typer.echo("\n✅ *تم بنجاح:*")
        if data:
            for k, v in data.items():
                key = k.replace("_", " ")
                val = str(v)
                if len(val) > 300:
                    val = val[:300] + "..."
                typer.echo(f"   {key}: {val}")
        else:
            typer.echo("   لا توجد بيانات.")
    elif status == "failed":
        typer.echo(f"\n❌ فشل: {errors[0] if errors else 'خطأ غير معروف'}")
    elif status == "busy":
        typer.echo(f"\n⏳ مشغول: {result.get('error', 'مهمة قيد المعالجة')}")
    else:
        typer.echo("\n📋 النتيجة:")
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))

    typer.echo()


@app.command(name="status")
def status_cmd() -> None:
    """عرض حالة نظام OSS Work."""
    typer.echo("\n=== OSS Work Status ===")
    typer.echo(f"Version: {VERSION}")
    typer.echo(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    typer.echo(f"Simulation Mode: {os.getenv('OSS_WORK_SIMULATION_ONLY', '1')}")

    config = load_config()
    typer.echo("\n--- Configuration ---")
    typer.echo(f"Mode: {config.mode}")
    typer.echo(f"Desktop: {config.desktop_mode} ({'API' if config.api_enabled else 'CLI'})")
    if config.api_enabled:
        typer.echo(f"API URL: http://{config.api_host}:{config.api_port}")

    data_dir = _get_data_dir()
    typer.echo(f"Data Directory: {data_dir}")

    checks = {
        "Playwright": _check_import("playwright"),
        "httpx": _check_import("httpx"),
        "asyncpg": _check_import("asyncpg"),
        "redis": _check_import("redis"),
        "qdrant_client": _check_import("qdrant_client"),
        "celery": _check_import("celery"),
        "scikit-learn": _check_import("sklearn"),
        "opencv": _check_import("cv2"),
    }

    typer.echo("\n--- Dependencies ---")
    all_ok = True
    for name, available in checks.items():
        status = "✅" if available else "❌"
        typer.echo(f"  {status} {name}")
        if not available:
            all_ok = False

    typer.echo(f"\nOverall: {'✅ All dependencies available' if all_ok else '❌ Some dependencies missing'}")


def _check_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


@app.command(name="models")
def models_cmd() -> None:
    """عرض النماذج المتاحة للخدمة."""
    router = get_router()
    typer.echo(f"\n=== Available Models ({len(router._model_map)}) ===\n")

    by_provider: dict[str, list] = {}
    for model in router._model_map.values():
        provider = model.provider.value
        if provider not in by_provider:
            by_provider[provider] = []
        by_provider[provider].append(model)

    for provider, models in sorted(by_provider.items()):
        typer.echo(f"--- {provider.upper()} ---")
        for m in sorted(models, key=lambda x: x.name):
            vision = "👁" if m.supports_vision else "  "
            free = "💰FREE" if m.cost_per_1k_tokens == 0 else f"💵${m.cost_per_1k_tokens}"
            typer.echo(f"  {vision} {m.name:30} {m.category:12} {free}  ctx:{m.context_window}")
        typer.echo()


@app.command(name="imagine")
def imagine_cmd(
    task: str = typer.Argument(..., help="مهمة لإنشاء حلول"),
    threads: int = typer.Option(50, "--threads", "-t", help="أقصى عدد خيوط"),
    depth: int = typer.Option(20, "--depth", "-d", help="عمق المحاكاة"),
) -> None:
    """تشغيل محرك Ultra IQ الخيال على مهمة."""
    typer.echo(f"\n🧠 إنشاء حلول لـ: {task}")
    typer.echo(f"Threads: {threads}, Depth: {depth}")
    typer.echo("---")

    engine = UltraIQEngine(max_threads=threads, simulation_depth=depth)
    result = _run_async(engine.process(task))

    typer.echo(f"\n✅ Solution (confidence: {result.confidence:.2f}):")
    typer.echo(f"\n{result.solution}")
    typer.echo("\n---")
    typer.echo(f"Threads explored: {result.threads_explored}")
    typer.echo(f"Invented: {result.invented}")
    typer.echo(f"Simulations: {result.simulation_branches}")
    typer.echo(f"Elapsed: {result.elapsed_ms:.0f}ms")

    if result.reasoning_chain:
        typer.echo("\n📋 Reasoning chain:")
        for i, step in enumerate(result.reasoning_chain, 1):
            typer.echo(f"  {i}. {step}")

    if result.cross_domain_bridges:
        typer.echo("\n🔗 Cross-domain bridges:")
        for bridge in result.cross_domain_bridges[:5]:
            typer.echo(f"  • {bridge}")


@app.command(name="skill")
def skill_cmd() -> None:
    """عرض المهارات المبنية ذاتيا (تبنى عبر oss-os skill-new)."""
    from ossys import skills as oss_skills

    built = oss_skills.list_built()
    typer.echo("\n--- Self-built skills (local) ---")
    if not built:
        typer.echo("  (none yet — build one with: oss-os skill-new <name> <purpose>)")
    for skill in built:
        typer.echo(f"  • {skill['name']} — {skill['summary']}")
    typer.echo()


@app.command(name="update")
def update_cmd(check_only: bool = typer.Option(False, "--check/--apply", help="فحص فقط أو تطبيق")) -> None:
    """فحص أو تطبيق تحديثات OSS Work."""
    updater = get_updater()

    typer.echo("فحص التحديثات...")

    if check_only:
        info = _run_async(updater.get_available_updates())
        if info.get("available"):
            typer.echo(f"\n✅ تحديث متاح: v{info['latest']}")
            typer.echo(f"Current: v{info['current']}")
            typer.echo(f"Release notes: {info.get('release_notes', '')[:200]}")
        else:
            typer.echo(f"\n✅ محدث: v{info.get('current', 'unknown')}")
        return

    result = _run_async(updater.check_and_update())
    typer.echo(f"\nنتيجة التحديث: {result.status}")
    if result.message:
        typer.echo(f"رسالة: {result.message}")
    if result.error:
        typer.echo(f"خطأ: {result.error}")


@app.command(name="data-dir")
def data_dir_cmd() -> None:
    """عرض دليل بيانات OSS Work."""
    typer.echo(str(_get_data_dir()))


# ── Modes (internal) ────────────────────────────────────────────


class DesktopCLIMode:
    """وضع CLI التفاعلي على سطح المكتب."""

    def __init__(self, config: AgentConfig, processor: TaskProcessor):
        self.config = config
        self.processor = processor

    async def start(self) -> None:
        """تشغيل وضع CLI التفاعلي."""
        typer.echo()
        typer.echo("═" * 60)
        typer.echo("  OSS Work — Desktop CLI Mode (Standalone Agent)")
        typer.echo("═" * 60)
        typer.echo()
        typer.echo("  اكتب مهمة واضغط Enter لمعالجتها")
        typer.echo("  هذا يعمل مثل أي نموذج ذكاء اصطناعي آخر")
        typer.echo()
        typer.echo("  أوامر مساعدة:")
        typer.echo("    status     — عرض حالة الوكيل")
        typer.echo("    clear      — مسح السجل")
        typer.echo("    models     — عرض النماذج المتاحة")
        typer.echo("    quit / exit — خروج")
        typer.echo()

        while True:
            try:
                task = input("📝 المهمة: ").strip()
            except (EOFError, KeyboardInterrupt):
                typer.echo("\n👋 Goodbye!")
                break

            if not task:
                continue

            if task.lower() in ("quit", "exit", "خروج", " exit"):
                typer.echo("👋 Goodbye!")
                break

            if task.lower() == "status":
                status = self.processor.get_status()
                typer.echo("\n📊 الحالة:")
                for k, v in status.items():
                    typer.echo(f"   {k}: {v}")
                typer.echo()
                continue

            if task.lower() == "clear":
                self.processor.reset()
                typer.echo("✅ السجل تم مسحه")
                typer.echo()
                continue

            if task.lower() == "models":
                try:
                    router = get_router()
                    typer.echo("\n🤖 النماذج المتاحة:")
                    for m in router._model_map.values():
                        typer.echo(f"   • {m.name} ({m.provider.value})")
                        typer.echo(f"     المجال: {m.category}")
                        typer.echo()
                except Exception as e:
                    logger.exception("Unhandled exception in main.py")
                    typer.echo(f"❌ خطأ: {e}")
                typer.echo()
                continue

            typer.echo("⏳ جاري المعالجة...")
            result = await self.processor.process(task)

            status = result.get("status", "unknown")
            if status == "completed":
                data = result.get("data", {})
                typer.echo("\n✅ *تم بنجاح:*")
                if data:
                    for k, v in data.items():
                        key = k.replace("_", " ")
                        val = str(v)
                        if len(val) > 300:
                            val = val[:300] + "..."
                        typer.echo(f"   {key}: {val}")
                    typer.echo()
                else:
                    typer.echo("   لا توجد بيانات.")
                    typer.echo()
            elif status == "failed":
                errors = result.get("errors", [])
                typer.echo(f"\n❌ فشل: {errors[0] if errors else 'خطأ غير معروف'}")
                typer.echo()
            elif status == "busy":
                typer.echo(f"\n⏳ مشغول: {result.get('error', 'مهمة قيد المعالجة')}")
                typer.echo()
            else:
                typer.echo("\n📋 النتيجة:")
                typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
                typer.echo()


# ── Entry Point ──────────────────────────────────────────────────


def main() -> None:
    """نقطة دخول CLI."""
    app()


if __name__ == "__main__":
    main()
