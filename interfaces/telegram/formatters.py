"""
Telegram Response Formatters.

Formats bot responses: status-based formatting, data display, markdown styling.
"""

from __future__ import annotations

import json
from typing import Any

from telegram import InlineKeyboardMarkup


class ResponseFormatter:
    """Formats bot responses for Telegram."""

    @staticmethod
    def format_completed(data: dict[str, Any]) -> str:
        """Format a completed task response."""
        lines = ["✅ *تم بنجاح*"]
        for key, value in data.items():
            formatted_key = key.replace("_", " ").replace("action", "الإجراء")
            if isinstance(value, str) and len(value) > 500:
                value = value[:500] + "..."
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, indent=2)[:500]
            lines.append(f"*{formatted_key}:* {value}")
        return "\n".join(lines)

    @staticmethod
    def format_failed(errors: list[str]) -> str:
        """Format a failed task response."""
        if errors:
            return f"❌ *فشل*\n\n{errors[0]}"
        return "❌ *فشل*\n\nحدث خطأ غير معروف."

    @staticmethod
    def format_requires_approval(explanation: str) -> str:
        """Format a requires-approval response."""
        return f"⚠️ *موافقة مطلوبة*\n\n{explanation or 'يرجى الموافقة على تنفيذ العملية.'}"

    @staticmethod
    def format_simulated(note: str) -> str:
        """Format a simulated response."""
        return f"🔵 *محاكاة*\n\n{note or 'هذه النتيجة محاكاة فقط.'}"

    @staticmethod
    def format_error(error: str) -> str:
        """Format an error response."""
        return f"❌ *خطأ*\n\n{error}"

    @staticmethod
    def format_unknown(result: dict[str, Any]) -> str:
        """Format an unknown status response."""
        return f"❓ *حالة غير معروفة*\n\n{str(result)[:500]}"

    @classmethod
    def format(cls, result: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup | None]:
        """Format a full response with optional keyboard."""
        status = result.get("status", "unknown")
        data = result.get("data", {})
        errors = result.get("errors", [])

        if status == "completed":
            text = cls.format_completed(data)
            keyboard = KeyboardBuilder.completion_keyboard()
        elif status == "requires_approval":
            text = cls.format_requires_approval(data.get("explanation", ""))
            keyboard = KeyboardBuilder.approval_keyboard()
        elif status == "simulated":
            text = cls.format_simulated(data.get("note", ""))
            keyboard = None
        elif status == "failed":
            text = cls.format_failed(errors)
            keyboard = KeyboardBuilder.error_keyboard()
        else:
            text = cls.format_unknown(result)
            keyboard = None

        return text, keyboard

    @staticmethod
    def format_welcome() -> str:
        """Format the welcome message for /start."""
        return """
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

    @staticmethod
    def format_help() -> str:
        """Format the help message."""
        return """
*الأوامر المتاحة:*

/start — بداية الاستخدام
/help — هذه الرسالة
/status — حالة النظام
/models — عرض النماذج المتاحة
/clear — مسح سياق المحادثة

*أرسل أي رسالة نصية* وسأحللها وأغذّيها لمحركUltra IQ ثم أنفذها.
أرسل *صوت* وسأحوله إلى نص وأنفذها.
أرسل *صورة* وسأحللها وأفهم محتواها.
أرسل *وثيقة* وسأقرأ محتواها وأعمل عليها.
"""

    @staticmethod
    def format_status(sim_only: bool = True) -> str:
        """Format status message."""
        mode = "Production" if not sim_only else "Simulation Only"
        return (
            "*حالة النظام:*\n\n"
            f"🤖 OSS Work v1.0.0-dev\n"
            f"📊 الوضع: {mode}\n"
            "\n"
            + ("🟢 العمليات حقيقية" if not sim_only else "🔴 جميع العمليات محاكاة")
        )

    @staticmethod
    def format_models(models: list[dict[str, Any]], count: int) -> str:
        """Format model list."""
        lines = [f"*النماذج المتاحة ({count}):*" ]
        for m in models[:15]:
            lines.append(f"• {m['name']} ({m['provider']}) — {m.get('category', 'general')}")
        if len(models) > 15:
            lines.append(f"... و{m['name']} نموذج آخر")
        return "\n".join(lines)
