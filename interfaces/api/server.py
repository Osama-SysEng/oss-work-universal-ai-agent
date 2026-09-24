"""
OSS Work — Desktop Local API.

تشغيل الوكيل كـ API محلي على桌面 — 사용할 수 있습니다 مثل أي نموذج ذكاء اصطناعي.
تطبيقات桌面 الأخرى ترسل HTTP requests وتستقبل ردود.

Usage:
    python -m interfaces.api.server
    # أو
    uvicorn interfaces.api.server:app --host 127.0.0.1 --port 8080

مثال من أي تطبيق桌面:
    curl -X POST http://127.0.0.1:8080/task \\
      -H "Content-Type: application/json" \\
      -d '{"task": "صمم نظام إشعارات", "user_id": "تطبيقي"}'

أو من Python:
    import requests
    response = requests.post("http://127.0.0.1:8080/task", json={
        "task": "صمم نظام إشعارات",
        "user_id": "تطبيقي"
    })
    print(response.json())
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

# إضافة المسار للمفاتيح الداخلية
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.config import load_config
from core.processor import TaskProcessor, get_processor


# ═══════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════

class TaskRequest(BaseModel):
    """طلب مهمة — يعمل مثل أي API لنموذج ذكاء اصطناعي."""
    task: str = Field(..., min_length=2, max_length=10000,
                      description="المهمة المراد معالجتها. مثل 프롬프트 لـ ChatGPT.")
    user_id: str = Field(default="local", min_length=1, max_length=128,
                          description="معرف المستخدم لتتبع السجل")
    context: dict = Field(default_factory=dict,
                          description="سياق اختياري")


class TaskResponse(BaseModel):
    """ردود المهمة."""
    status: str = Field(..., description="completed | failed | busy")
    data: dict = Field(default_factory=dict, description="بيانات النتيجة")
    errors: list = Field(default_factory=list, description="رسائل الخطأ")
    task_id: str = Field(default="", description="معرف فريد للمهمة")
    latency_ms: float = Field(default=0, description="زمن المعالجة")


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "oss-work-desktop-api"
    version: str = "0.3.0"


class StatusResponse(BaseModel):
    version: str
    mode: str
    simulation_only: bool
    uptime_seconds: float
    total_tasks: int
    active_tasks: int
    users: list


# ═══════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="OSS Work — Desktop Local API",
    description="""\
# API محلي لـ OSS Work على桌面

استخدم هذا API للتفاعل مع وكيل OSS Work من أي تطبيق桌面.
أرسل مهمة، استعمل ردود — مثل استخدام ChatGPT أو Claude أو أي نموذج ذكاء اصطناعي آخر.

## الاستخدام السريع

```bash
# تشغيل خادم API
python -m interfaces.api.server
# أو
uvicorn interfaces.api.server:app --host 127.0.0.1 --port 8080
```

## أمثلة الاستخدام

### cURL
```bash
curl -X POST http://127.0.0.1:8080/task \\
  -H "Content-Type: application/json" \\
  -d '{"task": "صمم نظام إشعارات لـ 10 مليون مستخدم"}'
```

### Python
```python
import requests

response = requests.post("http://127.0.0.1:8080/task", json={
    "task": "صمم نظام إشعارات لـ 10 مليون مستخدم",
    "user_id": "تطبيقي",
})
result = response.json()
print(result["data"]["solution"])
```

## النهايات (Endpoints)

- `GET /health` — فحص الحالة
- `GET /status` — حالة الوكيل والإحصائيات
- `POST /task` — إرسال مهمة (النهاية الرئيسية)
- `GET /models` — عرض النماذج المتاحة
""",
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ═══════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """فحص الحالة."""
    return HealthResponse(
        status="ok",
        service="oss-work-desktop-api",
        version="0.3.0",
    )


@app.get("/status", response_model=StatusResponse)
async def get_status(processor: TaskProcessor = None):
    """حالة الوكيل والإحصائيات."""
    if processor is None:
        processor = get_processor()
    status = processor.get_status()
    return StatusResponse(
        version=status["version"],
        mode=status["mode"],
        simulation_only=status["simulation_only"],
        uptime_seconds=status["uptime_seconds"],
        total_tasks=status["total_tasks"],
        active_tasks=status["active_tasks"],
        users=status["users"],
    )


@app.post("/task", response_model=TaskResponse)
async def submit_task(
    request: TaskRequest,
    processor: TaskProcessor = None,
):
    """
    إرسال مهمة للوكيل.

    هذه هي النهاية الرئيسية. أرسل مهمة (مثل 프롬프트 لـ ChatGPT)،
    واحصل على ردود مع الحل.

    يعالج الوكيل المهمة عبر:
    1. محرك Ultra IQ الخيال — يكتمل/يوسع الفكر
    2. المنسق — يوجّه عبر عوامل代理 متخصصة
    3. موجه النماذج — يستخدم 100+ نماذج ذكاء اصطناعي مجانية إذا لزم
    """
    if processor is None:
        processor = get_processor()

    if not request.task or len(request.task.strip()) < 2:
        raise HTTPException(400, "المهمة يجب أن تكون 2 حرف على الأقل")

    if len(request.task) > 10000:
        raise HTTPException(400, "المهمة يجب أن تكون 10000 حرف كحد أقصى")

    result = await processor.process(request.task, request.user_id)

    return TaskResponse(
        status=result.get("status", "unknown"),
        data=result.get("data", {}),
        errors=result.get("errors", []),
        task_id=result.get("task_id", ""),
        latency_ms=result.get("latency_ms", 0),
    )


@app.get("/models")
async def list_models():
    """عرض النماذج المتاحة للخدمה."""
    try:
        from core.services.model_router import get_router
        router = get_router()
        models = []
        for m in router._model_map.values():
            models.append({
                "id": m.id,
                "name": m.name,
                "provider": m.provider.value,
                "category": m.category,
                "context_window": m.context_window,
                "supports_vision": m.supports_vision,
                "cost_per_1k_tokens": m.cost_per_1k_tokens,
                "api_available": m.api_available,
                "browser_url": m.browser_url,
            })
        return {"models": models}
    except Exception as e:
        raise HTTPException(500, f"فشل في عرض النماذج: {e}")


@app.get("/")
async def root():
    """النهاية الجذرية — معلومات API."""
    return {
        "service": "OSS Work — Desktop Local API",
        "version": "0.3.0",
        "description": "استخدم هذا API للتفاعل مع OSS Work من أي تطبيق桌面.",
        "endpoints": {
            "POST /task": "إرسال مهمة (النهاية الرئيسية)",
            "GET /health": "فحص الحالة",
            "GET /status": "حالة الوكيل",
            "GET /models": "عرض النماذج المتاحة",
            "/docs": "توثيق API تفاعلي",
        },
    }


# ═══════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    """تشغيل خادم API المحلي."""
    config = load_config()

    print("=" * 60)
    print("  OSS Work — Desktop Local API Server")
    print("=" * 60)
    print()
    print(f"  الإصدار:    0.3.0")
    print(f"  الوضع:       {config.mode}")
    print(f"  المحاكاة:    {'ON' if config.simulation_only else 'OFF'}")
    print(f"  API URL:     http://{config.api_host}:{config.api_port}")
    print(f"  التوثيق:     http://{config.api_host}:{config.api_port}/docs")
    print()
    print("  استخدم مثل أي نموذج ذكاء اصطناعي:")
    print(f"    curl -X POST http://{config.api_host}:{config.api_port}/task \\")
    print("      -H 'Content-Type: application/json' \\")
    print('      -d \'{"task": "مهمتك هنا"}\'')
    print()
    print("=" * 60)
    print()

    uvicorn.run(
        app,
        host=config.api_host,
        port=config.api_port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
