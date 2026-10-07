"""
JEV Client - TypeSafe AI System One Model Integration
وحدة التكامل مع نموذج JEV من TypeSafe AI

JEV هو نموذج "System One" لا يولد نصاً بل يعيد قرارات
مع احتمالات - مثالي للـ routing والـ classification.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class JEVQuestion:
    """سؤال واحد لـ JEV"""
    name: str
    question_type: str  # 'choice', 'bool', 'float', 'text'
    instructions: str
    criteria: Optional[Dict[str, str]] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None


@dataclass
class JEVDecision:
    """قرار من JEV"""
    question_name: str
    decision_type: str
    value: Any
    probabilities: Dict[str, float]
    confidence: float


@dataclass
class JEVResponse:
    """الاستجابة الكاملة من JEV"""
    model: str
    decisions: List[JEVDecision] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'JEVResponse':
        decisions = []
        for qname, qdata in data.get('answers', {}).items():
            d = JEVDecision(
                question_name=qname,
                decision_type=qdata.get('type', 'unknown'),
                value=qdata.get('choice') or qdata.get('value'),
                probabilities=qdata.get('probabilities', {}),
                confidence=qdata.get('confidence', 0.0)
            )
            decisions.append(d)
        return cls(
            model=data.get('model', 'jev-latest'),
            decisions=decisions,
            usage=data.get('usage', {})
        )


class JEVClient:
    """
    عميل للاتصال بـ JEV API
    
    الاستخدام:
        client = JEVClient(api_key="ts_...")
        response = client.decide(
            state="المستخدم يريد إنشاء حساب",
            questions={
                "intent": JEVQuestion(
                    name="intent",
                    question_type="choice",
                    instructions="ما هي نية المستخدم؟",
                    criteria={
                        "registration": "إنشاء حساب جديد",
                        "login": "تسجيل الدخول",
                        "support": "طلب دعم فني"
                    }
                )
            }
        )
    """
    
    BASE_URL = "https://api.typesafe.ai/v1"
    DEFAULT_MODEL = "jev-latest"
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url or self.BASE_URL
        self.session_token = None
    
    def _build_payload(self, state: str, questions: Dict[str, Any]) -> Dict[str, Any]:
        """بناء Payload للطلب"""
        formatted_questions = {}
        for name, q in questions.items():
            if isinstance(q, JEVQuestion):
                formatted_questions[name] = {
                    "type": q.question_type,
                    "instructions": q.instructions,
                }
                if q.criteria:
                    formatted_questions[name]["criteria"] = q.criteria
                if q.min_val is not None:
                    formatted_questions[name]["min"] = q.min_val
                if q.max_val is not None:
                    formatted_questions[name]["max"] = q.max_val
            elif isinstance(q, dict):
                formatted_questions[name] = q
        return {
            "model": self.DEFAULT_MODEL,
            "state": state,
            "questions": formatted_questions
        }
    
    async def decide(self, state: str, questions: Dict[str, Any]) -> JEVResponse:
        """
        إرسال قرار إلى JEV وحصول على نتائج التصنيف
        
        Args:
            state: السياق/الحالة للتحليل
            questions: أسئلة قرار معرفة مسبقاً
        
        Returns:
            JEVResponse مع القرارات والاحتمالات
        """
        import httpx
        
        payload = self._build_payload(state, questions)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/systemone",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
        
        logger.info(f"JEV response: {len(data.get('answers', {}))} decisions")
        return JEVResponse.from_api_response(data)
    
    def decide_sync(self, state: str, questions: Dict[str, Any]) -> JEVResponse:
        """نسخة synchronous من decide()"""
        import httpx
        
        payload = self._build_payload(state, questions)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.base_url}/systemone",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
        
        logger.info(f"JEV sync response: {len(data.get('answers', {}))} decisions")
        return JEVResponse.from_api_response(data)
    
    def route_task(self, task_type: str, task_description: str, criteria: Dict[str, str]) -> str:
        """
        توجيه مهمة إلى الفئة المناسبة
        
        مثال:
            route = client.route_task(
                task_type="task",
                task_description="تصميم نظام إشعارات لموقع ويب",
                criteria={
                    "design": "تصميم واجهات و UX",
                    "backend": "خلفية و APIs",
                    "fullstack": "واجهة و خلفية معاً",
                    "devops": "نشر و بنية"
                }
            )
        """
        response = self.decide_sync(
            state=task_description,
            questions={
                "route": JEVQuestion(
                    name="route",
                    question_type="choice",
                    instructions=f"أي فئة تناسب هذا {task_type}؟",
                    criteria=criteria
                )
            }
        )
        if response.decisions:
            return response.decisions[0].value
        return "unknown"
    
    def classify_intent(self, user_input: str, intents: Dict[str, str]) -> Dict[str, Any]:
        """
        تصنيف نية المستخدم
        
        مثال:
            result = client.classify_intent(
                user_input="أريد إنشاء مشروع جديد",
                intents={
                    "create": "إنشاء مشروع جديد",
                    "list": "عرض المشاريع",
                    "delete": "حذف مشروع",
                    "help": "مساعدة"
                }
            )
        """
        response = self.decide_sync(
            state=user_input,
            questions={
                "intent": JEVQuestion(
                    name="intent",
                    question_type="choice",
                    instructions="ما هي نية المستخدم؟",
                    criteria=intents
                ),
                "confidence": JEVQuestion(
                    name="confidence",
                    question_type="float",
                    instructions="درجة الثقة (0-1)",
                    min_val=0.0,
                    max_val=1.0
                )
            }
        )
        result = {"intent": None, "confidence": 0.0}
        for d in response.decisions:
            if d.question_name == "intent":
                result["intent"] = d.value
            elif d.question_name == "confidence":
                result["confidence"] = float(d.value) if d.value else 0.0
        return result


# === مساعدين جاهزين ===

# مساعد التصنيف الافتراضي للمهام
TASK_ROUTER_CRITERIA = {
    "design": "تصميم واجهات و UX/UI",
    "backend": "خلفية و APIs و_server",
    "frontend": "واجهة مستخدم أمامية",
    "data": "بيانات وقواعد معلومات",
    "devops": "نشر وبنية تحتية",
    "ai_ml": "ذكاء اصطناعي وتعلم آلي",
    "security": "أمان وخصوصية",
    "fullstack": "لفافة كاملة (واجهة + خلفية)",
    "mobile": "تطبيقات جوال",
}

# مساعد التصنيف الافتراضي للنيّات
INTENT_CRITERIA = {
    "create": "إنشاء شيء جديد",
    "read": "قراءة أو عرض معلومات",
    "update": "تعديل أو تحديث",
    "delete": "حذف شيء",
    "search": "بحث عن معلومات",
    "help": "طلب مساعدة",
    "config": "إعدادات وتكوين",
}


def create_default_client(api_key: str) -> JEVClient:
    """إنشاء عميل جاهز مع المعايير الافتراضية"""
    return JEVClient(api_key=api_key)


if __name__ == "__main__":
    # اختبار سريع (يتطلب TYPESAFE_API_KEY)
    import os
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if api_key:
        client = create_default_client(api_key)
        response = client.route_task(
            "task",
            "تصميم نظام إشعارات لموقع ويب",
            TASK_ROUTER_CRITERIA
        )
        print(f"📬 التوجيه: {response}")
    else:
        print("⚠️ لم تعثر على TYPESAFE_API_KEY - ضعها في البيئة لتشغيل الاختبار")