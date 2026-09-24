"""
اختبارات أساسية لبوت Telegram
"""

import pytest


class TestBotConfig:
    def test_default_config(self):
        from interfaces.telegram.bot import BotConfig
        cfg = BotConfig()
        assert cfg.token == ""
        assert cfg.admin_chat_ids == []
        assert cfg.default_language == "ar"
        assert cfg.simulation_only is True
        assert cfg.enable_voice is True
        assert cfg.enable_image is True
        assert cfg.enable_document is True

    def test_custom_config(self):
        from interfaces.telegram.bot import BotConfig
        cfg = BotConfig(
            token="test_token",
            admin_chat_ids=["123", "456"],
            default_language="en",
            simulation_only=False,
            enable_voice=False,
        )
        assert cfg.token == "test_token"
        assert cfg.admin_chat_ids == ["123", "456"]
        assert cfg.default_language == "en"
        assert cfg.simulation_only is False
        assert cfg.enable_voice is False


class TestTelegramBotCreation:
    def test_bot_with_config(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot, BotConfig
        cfg = BotConfig(token="test_token")
        bot = OSSWorkTelegramBot(config=cfg)
        assert bot.config.token == "test_token"
        assert bot.orchestrator is not None

    def test_bot_without_config(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        assert bot.config.token == ""
        assert bot.orchestrator is not None

    def test_create_bot_factory(self):
        from interfaces.telegram.bot import create_bot
        bot = create_bot("test_token", ["admin1"])
        assert bot.config.token == "test_token"
        assert "admin1" in bot.config.admin_chat_ids


class TestBotMessages:
    def test_welcome_message_exists(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        assert "NASA Space Apps" in bot.WELCOME
        assert "AI Hackathon" in bot.WELCOME
        assert "OSS Work" in bot.WELCOME

    def test_help_message_exists(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        assert "/start" in bot.HELP
        assert "/help" in bot.HELP
        assert "/status" in bot.HELP


class TestFormatResponse:
    def test_completed_status(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        result = {"status": "completed", "data": {"result": "success"}}
        text, kb = bot._format(result)
        assert "✅" in text
        assert "تم" in text

    def test_failed_status(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        result = {"status": "failed", "errors": ["something went wrong"]}
        text, kb = bot._format(result)
        assert "❌" in text
        assert "فشل" in text

    def test_simulated_status(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        result = {"status": "simulated", "data": {"note": "simulated only"}}
        text, kb = bot._format(result)
        assert "🔵" in text
        assert "محاكاة" in text

    def test_requires_approval_status(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        result = {"status": "requires_approval", "data": {"explanation": "needs approval"}}
        text, kb = bot._format(result)
        assert "⚠️" in text
        assert "موافقة" in text

    def test_keyboard_for_completed(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        from telegram import InlineKeyboardMarkup
        bot = OSSWorkTelegramBot()
        result = {"status": "completed", "data": {}}
        _, kb = bot._format(result)
        assert isinstance(kb, InlineKeyboardMarkup)


class TestDataFormatting:
    def test_empty_data(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        result = bot._fmt_data({})
        assert "لا توجد بيانات" in result

    def test_simple_data(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        result = bot._fmt_data({"name": "test", "value": 42})
        assert "name" in result or "Name" in result
        assert "42" in result

    def test_long_string_truncated(self):
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()
        long_text = "x" * 1000
        result = bot._fmt_data({"data": long_text})
        assert len(result) < 600
        assert "..." in result


class TestCompleteThought:
    def test_complete_thought_import(self):
        import asyncio
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()

        async def run():
            return await bot._complete_thought("test task", "user1")

        result = asyncio.run(run())
        assert isinstance(result, str)
        assert len(result) > 0

    def test_complete_thought_empty(self):
        import asyncio
        from interfaces.telegram.bot import OSSWorkTelegramBot
        bot = OSSWorkTelegramBot()

        async def run():
            return await bot._complete_thought("", "user1")

        result = asyncio.run(run())
        assert result == ""
