"""
JEV API Routes — TypeSafe AI System One endpoints.
يضاف إلى FastAPI تطبيق OSS Work.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/jev", tags=["jev"])

# ═══════════════════════════════════════════════════════════════════
# /jev/config
# ═══════════════════════════════════════════════════════════════════

@router.get("/config")
async def jev_config():
    """إعدادات JEV الحالية."""
    from core.config import load_config
    cfg = load_config()
    return {
        "enabled": cfg.use_jev,
        "api_key_set": bool(cfg.jev_api_key),
        "base_url": cfg.jev_base_url,
        "model": cfg.jev_model,
        "timeout": cfg.jev_timeout
    }

# ═══════════════════════════════════════════════════════════════════
# /jev/route
# ═══════════════════════════════════════════════════════════════════

@router.post("/route")
async def jev_route(request: Request):
    """توجيه مهمة عبر JEV."""
    from core.jev_client import JEVClient, TASK_ROUTER_CRITERIA
    from core.config import load_config
    
    cfg = load_config()
    if not cfg.use_jev or not cfg.jev_api_key:
        return JSONResponse(
            {"error": "JEV not configured. Set TYPESAFE_API_KEY and OSS_USE_JEV=true"},
            status_code=400
        )
    
    body = await request.json()
    task = body.get("task", "")
    criteria = body.get("criteria", TASK_ROUTER_CRITERIA)
    
    client = JEVClient(api_key=cfg.jev_api_key, base_url=cfg.jev_base_url)
    
    # توجيه سريع
    route_result = client.route_task(
        task_type="task",
        task_description=task,
        criteria=criteria
    )
    
    # جلب الاحتمالات الكاملة
    full = client.decide_sync(
        state=task,
        questions={
            "route": {
                "type": "choice",
                "instructions": "أي فئة تناسب هذا الطلب؟",
                "criteria": criteria
            }
        }
    )
    
    probs = {}
    conf = 0.0
    for d in full.decisions:
        if d.question_name == "route" and d.probabilities:
            probs = d.probabilities
            conf = max(probs.values())
    
    return {
        "jev_routed_to": route_result,
        "jev_confidence": conf,
        "jev_probabilities": probs,
        "model": cfg.jev_model
    }

# ═══════════════════════════════════════════════════════════════════
# /jev/decide
# ═══════════════════════════════════════════════════════════════════

@router.post("/decide")
async def jev_decide(request: Request):
    """طلب قرار كامل من JEV."""
    from core.jev_client import JEVClient
    from core.config import load_config
    
    cfg = load_config()
    if not cfg.use_jev or not cfg.jev_api_key:
        return JSONResponse(
            {"error": "JEV not configured"},
            status_code=400
        )
    
    body = await request.json()
    client = JEVClient(api_key=cfg.jev_api_key, base_url=cfg.jev_base_url)
    
    state = body.get("state", "")
    questions = body.get("questions", {})
    
    result = client.decide_sync(state=state, questions=questions)
    
    answers = {}
    for d in result.decisions:
        answers[d.question_name] = {
            "type": d.decision_type,
            "value": d.value,
            "probabilities": d.probabilities,
            "confidence": d.confidence
        }
    
    return {
        "model": result.model,
        "answers": answers,
        "usage": result.usage
    }
