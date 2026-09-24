"""
Telegram Inline Keyboard Builders.

Builds keyboards for: approval, repeat, details, navigation.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class KeyboardBuilder:
    """Builds Telegram inline keyboards."""

    @staticmethod
    def approval_keyboard() -> InlineKeyboardMarkup:
        """Keyboard for approval requests."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ approve", callback_data="approve"),
                InlineKeyboardButton("❌ رفض", callback_data="reject"),
            ]
        ])

    @staticmethod
    def completion_keyboard() -> InlineKeyboardMarkup:
        """Keyboard for completed tasks."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔁 تكرار", callback_data="repeat"),
                InlineKeyboardButton("📋 تفاصيل", callback_data="details"),
            ]
        ])

    @staticmethod
    def start_keyboard() -> InlineKeyboardMarkup:
        """Keyboard for /start command."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 ابدأ الآن", callback_data="start_task")],
            [InlineKeyboardButton("❓ مساعدة", callback_data="help")],
        ])

    @staticmethod
    def help_keyboard() -> InlineKeyboardMarkup:
        """Keyboard for /help command."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 العودة", callback_data="back")],
        ])

    @staticmethod
    def error_keyboard() -> InlineKeyboardMarkup:
        """Keyboard for error states."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 حاول مجددًا", callback_data="retry")],
            [InlineKeyboardButton("❓ مساعدة", callback_data="help")],
        ])

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Main menu keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 ابدأ مهمة", callback_data="start_task")],
            [InlineKeyboardButton("📊 الحالة", callback_data="status")],
            [InlineKeyboardButton("🤖 النماذج", callback_data="models")],
            [InlineKeyboardButton("🔧 الإعدادات", callback_data="settings")],
        ])
