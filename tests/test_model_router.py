"""
اختبارات لوحدة توجيه النماذج Model Router
"""

from core.services.model_router import (
    MODELS,
    ROUTING_TABLE,
    ModelProvider,
    ModelRouter,
)


class TestModelRouterCreation:
    def test_default_creation(self):
        router = ModelRouter()
        assert router.default_model == "gemini_flash"
        assert len(router._model_map) == len(MODELS)

    def test_custom_default(self):
        router = ModelRouter(default_model="gpt4o")
        assert router.default_model == "gpt4o"


class TestModelClassification:
    def test_code_classification(self):
        router = ModelRouter()
        task_type = router.classify_task("write python code for a web scraper")
        assert task_type == "code_generation"

    def test_arabic_classification(self):
        router = ModelRouter()
        task_type = router.classify_task("اكتب مقالة بالعربية")
        assert task_type == "arabic_content"

    def test_general_classification(self):
        router = ModelRouter()
        task_type = router.classify_task("مرحبا كيف حالك")
        assert task_type == "general_chat"

    def test_fast_classification(self):
        router = ModelRouter()
        task_type = router.classify_task("quick response please")
        assert task_type == "fast_response"

    def test_html_classification(self):
        router = ModelRouter()
        task_type = router.classify_task("generate HTML for a login page")
        assert task_type == "html_generation"


class TestModelRouting:
    def test_get_candidates(self):
        router = ModelRouter()
        candidates = router.get_candidates("code_generation")
        assert len(candidates) > 0
        assert "gpt4o" in candidates or "deepseek_coder" in candidates

    def test_get_provider(self):
        router = ModelRouter()
        model = router.get_provider("gpt4o")
        assert model is not None
        assert model.id == "gpt4o"
        assert model.name == "GPT-4o"

    def test_get_unknown_provider(self):
        router = ModelRouter()
        model = router.get_provider("nonexistent_model")
        assert model is None


class TestModelInfo:
    def test_model_fields(self):
        model = MODELS[0]
        assert hasattr(model, "id")
        assert hasattr(model, "name")
        assert hasattr(model, "provider")
        assert hasattr(model, "context_window")

    def test_provider_enum(self):
        assert ModelProvider.OPENAI.value == "openai"
        assert ModelProvider.GROQ.value == "groq"
        assert ModelProvider.OLLAMA.value == "ollama"


class TestRoutingTable:
    def test_routing_table_keys(self):
        assert "code_generation" in ROUTING_TABLE
        assert "general_chat" in ROUTING_TABLE
        assert "fast_response" in ROUTING_TABLE

    def test_routing_table_values(self):
        candidates = ROUTING_TABLE.get("general_chat", [])
        assert len(candidates) > 0
        for c in candidates:
            assert c in [m.id for m in MODELS]


class TestModelProviderValues:
    def test_all_providers(self):
        providers = {m.provider for m in MODELS}
        assert ModelProvider.OPENAI in providers
        assert ModelProvider.ANTHROPIC in providers
        assert ModelProvider.GOOGLE in providers
        assert ModelProvider.GROQ in providers
        assert ModelProvider.OLLAMA in providers


class TestModelCategories:
    def test_categories(self):
        categories = {m.category for m in MODELS}
        assert "general" in categories
        assert "code" in categories
        assert "fast" in categories


class TestOssLocalEngine:
    """oss-work independent engine wiring (llama-server, no keys)."""

    def test_oss_local_registered(self):
        router = ModelRouter()
        model = router.get_provider("oss_local")
        assert model is not None
        assert model.provider == ModelProvider.LOCAL
        assert model.api_available is True

    def test_offline_fallback_prefers_oss_local(self):
        assert ROUTING_TABLE["offline_fallback"][0] == "oss_local"

    def test_local_unavailable_when_down(self, monkeypatch):
        import asyncio

        import httpx

        class _DeadClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                raise httpx.ConnectError("down")

            async def post(self, *a, **k):
                raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "AsyncClient", _DeadClient)
        router = ModelRouter()
        assert asyncio.run(router.is_available("oss_local")) is False

    def test_local_fallback_none_when_all_down(self, monkeypatch):
        import asyncio

        monkeypatch.setenv("OSS_LOCAL_URL", "http://127.0.0.1:9")
        router = ModelRouter()
        result = asyncio.run(router._local_fallback("hi", {}))
        assert result is None
