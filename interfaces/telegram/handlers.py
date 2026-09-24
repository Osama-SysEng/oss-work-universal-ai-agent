"""
Telegram Bot Handlers — message, voice, image, document processing.

Handles: text messages, voice messages (transcription), images (analysis),
         documents (reading + processing).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from telegram import Update, Document, PhotoSize, Voice
from telegram.ext import ContextTypes


class BotHandlers:
    """Handler methods for Telegram bot messages."""

    def __init__(self, bot) -> None:
        self.bot = bot

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages."""
        user_id = str(update.effective_user.id)
        task = update.message.text

        if not task or len(task.strip()) < 2:
            await update.message.reply_text("الرسالة قصيرة جدًا. اكتب المهمة الكاملة.")
            return

        if self.bot._active_tasks.get(user_id):
            await update.message.reply_text("⏳ هناك مهمة قيد التنفيذ. انتظر اكتمالها أولاً.")
            return

        self.bot._active_tasks[user_id] = True

        try:
            await update.message.chat.send_action("typing")

            completed = await self.bot._complete_thought(task, user_id)
            request = self.bot._create_task_request(completed, user_id)
            result = await self.bot._execute_orchestrator(request)

            response_text, keyboard = self.bot._format_response(result)
            await update.message.reply_text(response_text, parse_mode="Markdown", reply_markup=keyboard)

            await self.bot._log_event(user_id, "task", task[:100], result.get("status", ""))
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}")
        finally:
            self.bot._active_tasks.pop(user_id, None)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages — transcribe then process."""
        user_id = str(update.effective_user.id)
        msg = update.message

        if self.bot._active_tasks.get(user_id):
            await msg.reply_text("⏳ مهمة قيد التنفيذ.")
            return

        self.bot._active_tasks[user_id] = True

        try:
            await msg.chat.send_action("recording")

            file = await context.bot.get_file(msg.voice.file_id)
            audio_bytes = await file.download_as_bytearray()

            text = await self.bot._transcribe_audio(audio_bytes)
            if not text:
                await msg.reply_text("❌ لم أتمكن من تحويل الصوت إلى نص")
                return

            await msg.reply_text(f"🎤 *نص التعرف على الصوت:* {text}", parse_mode="Markdown")
            msg.text = text
            await self.handle_message(update, context)
        except Exception as e:
            await msg.reply_text(f"❌ خطأ في معالجة الصوت: {str(e)}")
        finally:
            self.bot._active_tasks.pop(user_id, None)

    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle images — analyze then process."""
        user_id = str(update.effective_user.id)
        msg = update.message

        if self.bot._active_tasks.get(user_id):
            await msg.reply_text("⏳ مهمة قيد التنفيذ.")
            return

        self.bot._active_tasks[user_id] = True

        try:
            await msg.chat.send_action("typing")

            photo: PhotoSize = msg.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            image_bytes = await file.download_as_bytearray()

            caption = msg.caption or ""
            description = await self.bot._analyze_image(image_bytes, caption)

            await msg.reply_text(f"🖼 *وصف الصورة:* {description}", parse_mode="Markdown")
            msg.text = description
            await self.handle_message(update, context)
        except Exception as e:
            await msg.reply_text(f"❌ خطأ في معالجة الصورة: {str(e)}")
        finally:
            self.bot._active_tasks.pop(user_id, None)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle documents — read content then process."""
        user_id = str(update.effective_user.id)
        msg = update.message

        if self.bot._active_tasks.get(user_id):
            await msg.reply_text("⏳ مهمة قيد التنفيذ.")
            return

        self.bot._active_tasks[user_id] = True

        try:
            await msg.chat.send_action("typing")

            doc: Document = msg.document
            file = await context.bot.get_file(doc.file_id)
            data = await file.download_as_bytearray()

            name = doc.file_name or "document"
            ext = Path(name).suffix.lower()

            content = await self.bot._read_document(data, ext)

            task = f"Document '{name}' content:\n\n{content[:500]}"
            if msg.caption:
                task = msg.caption + "\n\n" + task

            await msg.reply_text(
                f"📄 *الوثيقة:* {name}\n*الحجم:* {len(data)} بايت\n*النوع:* {ext}",
                parse_mode="Markdown",
            )
            msg.text = task[:2000]
            await self.handle_message(update, context)
        except Exception as e:
            await msg.reply_text(f"❌ خطأ في معالجة الوثيقة: {str(e)}")
        finally:
            self.bot._active_tasks.pop(user_id, None)
