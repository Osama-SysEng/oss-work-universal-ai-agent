"""
Telegram Bot — Full OSS Work Telegram interface.
text + voice + image + document → multi-agent pipeline → formatted response.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from core.contracts import TaskRequest
from core.agents.orchestrator import OrchestratorAgent


@dataclass
class BotConfig:
    token: str = ""
    admin_chat_ids: list[str] = field(default_factory=list)
    default_language: str = "ar"
    simulation_only: bool = True
    enable_voice: bool = True
    enable_image: bool = True
    enable_document: bool = True


class OSSWorkTelegramBot:

    WELCOME = """
🤖 *OSS Work — Universal AI Agent*

NASA Space Apps Challenge 2025 Local Winner
AI Hackathon 2025 1st Place (260+ projects)

أرسل أي مهمة بالعربية أو الإنجليزية وسأتعامل معها:

• تصفح المواقع واقتباس المحتوى
• كتابة وتشغيل الكود
• إدارة الملفات
• البحث عبر نماذج الذكاء الاصطناعي
• النشر على وسائل التواصل
• إرسال الرسائل والبريد
• تحليل الصور والوثائق

_صفر إعداد. صفر تكلفة. صفر حدود._
"""

    HELP = """
*الأوامر المتاحة:*

/start — بداية الاستخدام
/help — هذه الرسالة
/status — حالة النظام
/models — عرض النماذج المتاحة
/clear — مسح سياق المحادثة

*أرسل أي رسالة نصية* وسأحللها وأغذّيها لمحرك Ultra IQ ثم أنفذها.
أرسل *صوت* وسأحوله Nass إلى نص وأنفذها.
أرسل *صورة* وسأحللها وأفهم محتواها.
أرسل *وثيقة* وسأقرأ محتواها وأعمل عليها.
"""

    def __init__(self, config: BotConfig | None = None) -> None:
        self.config = config or BotConfig()
        self.application: Application | None = None
        self.orchestrator = OrchestratorAgent()
        self._history: dict[str, list[dict]] = {}
        self._busy: set[str] = set()

    def setup(self) -> None:
        app = Application.builder().token(self.config.token).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("models", self.cmd_models))
        app.add_handler(CommandHandler("clear", self.cmd_clear))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        if self.config.enable_voice:
            app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        if self.config.enable_image:
            app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        if self.config.enable_document:
            app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application = app

    async def run(self) -> None:
        if not self.config.token:
            raise ValueError("Telegram bot token not configured")
        self.setup()
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

    async def stop(self) -> None:
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        text = self.WELCOME
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 ابدأ الآن", callback_data="start_task")],
            [InlineKeyboardButton("❓ مساعدة", callback_data="help")],
        ])
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        await self._log(user.id, "command", "start")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(self.HELP, parse_mode="Markdown")
        await self._log(update.effective_user.id, "command", "help")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        mode = "Production" if not self.config.simulation_only else "Simulation Only"
        text = (
            "*حالة النظام:*\n\n"
            f"🤖 OSS Work v0.2.0\n"
            f"📊 الوضع: {mode}\n"
            f"👤 {update.effective_user.first_name or 'مجهول'}\n"
            f"🆔 {update.effective_user.id}\n"
            f"📝 المهام: {len(self._history.get(str(update.effective_user.id), []))}\n\n"
            + ("🟢 العمليات حقيقية" if not self.config.simulation_only else "🔴 جميع العمليات محاكاة")
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        await self._log(update.effective_user.id, "command", "status")

    async def cmd_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            from core.services.model_router import get_router
            router = get_router()
            models = "\n".join(
                "• " + m.name + " (" + m.provider.value + ") — " + m.category
                for m in list(router._model_map.values())[:15]
            )
            await update.message.reply_text(
                "*النماذج المتاحة (" + str(len(router._model_map)) + "):*\n\n" + models,
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text("خطأ: " + str(e))
        await self._log(update.effective_user.id, "command", "models")

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = str(update.effective_user.id)
        self._history.pop(uid, None)
        self._busy.discard(uid)
        await update.message.reply_text("✅ تم مسح السياق")
        await self._log(uid, "command", "clear")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = str(update.effective_user.id)
        msg = update.message
        if not msg or not msg.text:
            return
        if uid in self._busy:
            await msg.reply_text("⏳ هناك مهمة قيد التنفيذ. انتظر اكتمالها.")
            return
        self._busy.add(uid)
        try:
            await msg.chat.send_action("typing")
            task = msg.text.strip()
            if len(task) < 2:
                await msg.reply_text("الرسالة قصيرة جدًا.")
                return
            completed = await self._complete_thought(task, uid)
            request = TaskRequest.create(task=completed, user_id=uid)
            result = self.orchestrator.execute(request)
            text, kb = self._format(result)
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            await self._log(uid, "task", task[:100], result.get("status", ""))
            self._history.setdefault(uid, []).append({"task": task[:100], "status": result.get("status", "")})
        except Exception as e:
            await msg.reply_text("❌ خطأ: " + str(e))
        finally:
            self._busy.discard(uid)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = str(update.effective_user.id)
        msg = update.message
        if uid in self._busy:
            await msg.reply_text("⏳ مهمة قيد التنفيذ.")
            return
        self._busy.add(uid)
        try:
            await msg.chat.send_action("recording")
            file = await context.bot.get_file(msg.voice.file_id)
            audio = await file.download_as_bytearray()
            text = await self._transcribe(audio)
            if not text:
                await msg.reply_text("❌ لم أستطع تحويل الصوت")
                return
            await msg.reply_text("*نص الصوت:* " + text, parse_mode="Markdown")
            msg.text = text
            await self.handle_text(update, context)
        except Exception as e:
            await msg.reply_text("❌ خطأ: " + str(e))
        finally:
            self._busy.discard(uid)

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = str(update.effective_user.id)
        msg = update.message
        if uid in self._busy:
            await msg.reply_text("⏳ مهمة قيد التنفيذ.")
            return
        self._busy.add(uid)
        try:
            await msg.chat.send_action("typing")
            photo = msg.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            img = await file.download_as_bytearray()
            caption = msg.caption or ""
            desc = await self._describe_image(img, caption)
            await msg.reply_text("*وصف الصورة:* " + desc, parse_mode="Markdown")
            msg.text = desc
            await self.handle_text(update, context)
        except Exception as e:
            await msg.reply_text("❌ خطأ: " + str(e))
        finally:
            self._busy.discard(uid)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = str(update.effective_user.id)
        msg = update.message
        if uid in self._busy:
            await msg.reply_text("⏳ مهمة قيد التنفيذ.")
            return
        self._busy.add(uid)
        try:
            await msg.chat.send_action("typing")
            doc = msg.document
            file = await context.bot.get_file(doc.file_id)
            data = await file.download_as_bytearray()
            name = doc.file_name or "document"
            ext = Path(name).suffix.lower()
            content = await self._read_doc(data, ext)
            task = "Document '" + name + "' content:\n\n" + content[:500]
            if msg.caption:
                task = msg.caption + "\n\n" + task
            await msg.reply_text(
                "*الوثيقة:* " + name + "\n*الحجم:* " + str(len(data)) + " بايت\n*النوع:* " + ext,
                parse_mode="Markdown",
            )
            msg.text = task[:2000]
            await self.handle_text(update, context)
        except Exception as e:
            await msg.reply_text("❌ خطأ: " + str(e))
        finally:
            self._busy.discard(uid)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if q.data == "help":
            await q.message.reply_text(self.HELP, parse_mode="Markdown")
        elif q.data == "start_task":
            await q.message.reply_text("أرسل أي مهمة وسأقوم بها!")

    async def _complete_thought(self, task: str, uid: str) -> str:
        try:
            from core.imagination.engine import UltraIQEngine
            engine = UltraIQEngine(max_threads=10, simulation_depth=5)
            return engine.complete_thought(task, {"user_id": uid})
        except Exception:
            return task

    async def _transcribe(self, audio: bytes) -> str:
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(audio)
            return result.get("text", "")
        except ImportError:
            return "[ whisper غير مثبت ]"
        except Exception as e:
            return "[ خطأ: " + str(e) + " ]"

    async def _describe_image(self, img: bytes, caption: str) -> str:
        try:
            from core.services.model_router import get_router
            router = get_router()
            prompt = "Describe this image. Caption: " + caption
            r = await router.complete(prompt, {"max_tokens": 500})
            return r.get("response", "[ could not analyze ]")
        except Exception as e:
            return "[ error: " + str(e) + " ]"

    async def _read_doc(self, data: bytes, ext: str) -> str:
        if ext in (".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".xml"):
            try:
                return data.decode("utf-8", errors="replace")
            except Exception:
                return "[ تعذر فك التشفير ]"
        elif ext == ".docx":
            try:
                import docx as docx_mod
                d = docx_mod.Document(io.BytesIO(data))
                return "\n".join(p.text for p in d.paragraphs)
            except ImportError:
                return "[ يحتاج python-docx ]"
            except Exception as e:
                return "[ خطأ: " + str(e) + " ]"
        elif ext == ".pdf":
            try:
                import fitz
                d = fitz.open(stream=io.BytesIO(data), filetype="pdf")
                return "\n".join(page.get_text() for page in d)
            except ImportError:
                return "[ يحتاج PyMuPDF ]"
            except Exception as e:
                return "[ خطأ: " + str(e) + " ]"
        else:
            return "[ نوع غير مدعوم: " + ext + " ]"

    def _format(self, result: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
        status = result.get("status", "unknown")
        data = result.get("data", {})
        errors = result.get("errors", [])
        if status == "completed":
            text = "✅ *تم*\n\n" + self._fmt_data(data)
        elif status == "requires_approval":
            text = "⚠️ *موافقة مطلوبة*\n\n" + (data.get("explanation", "") or "")
        elif status == "simulated":
            text = "🔵 *محاكاة*\n\n" + (data.get("note", "") or "")
        elif status == "failed":
            text = "❌ *فشل*\n\n" + (errors[0] if errors else "خطأ غير معروف")
        else:
            text = str(result)[:500]
        kb = InlineKeyboardMarkup([])
        if status == "requires_approval":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ approve", callback_data="approve"),
                 InlineKeyboardButton("❌ رفض", callback_data="reject")],
            ])
        elif status == "completed":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 تكرار", callback_data="repeat"),
                 InlineKeyboardButton("📋 تفاصيل", callback_data="details")],
            ])
        return text, kb

    def _fmt_data(self, data: dict[str, Any]) -> str:
        if not data:
            return "لا توجد بيانات."
        lines = []
        for k, v in data.items():
            key = k.replace("_", " ")
            if isinstance(v, str) and len(v) > 500:
                v = v[:500] + "..."
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False, indent=2)[:500]
            lines.append("*" + key + ":* " + str(v))
        return "\n".join(lines)

    async def _log(self, uid: int, kind: str, data: Any, status: str = "") -> None:
        try:
            d = Path("./data/telegram_logs")
            d.mkdir(parents=True, exist_ok=True)
            f = d / (str(uid) + ".jsonl")
            entry = {"ts": time.time(), "kind": kind, "data": str(data)[:500], "status": status}
            existing = f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""
            f.write_text(existing + json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass


def create_bot(token: str, admin_ids: list[str] | None = None) -> OSSWorkTelegramBot:
    cfg = BotConfig(
        token=token,
        admin_chat_ids=admin_ids or [],
        simulation_only=os.getenv("OSS_WORK_SIMULATION_ONLY", "1") == "1",
    )
    return OSSWorkTelegramBot(config=cfg)
