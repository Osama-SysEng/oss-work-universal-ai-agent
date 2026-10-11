# PRD — OSS Work Universal AI Agent

## 1. نظرة عامة
وكيل ذكاء اصطناعي مفتوح المصدر (Apache-2.0): محرك خيال Ultra IQ يعمل محليا، توجيه نماذج، 8 وكلاء متخصصين، واجهات CLI وTelegram وDesktop API محلي. الوضع الافتراضي محاكاة فقط.

## 2. المستخدمون
- مستخدم نهائي (Telegram/CLI/Web)
- مطوّر/مشغّل (CLI، API محلي، مهارات، تحديثات)

## 3. الميزات الأساسية (قابلة للاختبار)
1. إرسال مهمة عبر API المحلي (`POST /task` بجسم `{"task": "...", "user_id": "..."}` → `status: completed|failed|busy`)
2. فحص صحة وحالة الوكيل (`GET /health`, `GET /status` → version/mode/simulation_only/uptime/total_tasks/active_tasks/users)
3. سرد النماذج المتاحة (`GET /models?limit=&offset=` → models/total/limit/offset)
4. أوامر CLI: `run|chat|status|models|imagine|skill|update|telegram|desktop|data-dir` (Typer `oss-work`)
5. تشغيل مهمة CLI (`oss-work chat "مهمة" --user local`) وتفاعلي (`oss-work desktop`)
6. محرك الخيال (`oss-work imagine "مهمة" --threads 50 --depth 20` → solution/confidence/invented/threads_explored/simulation_branches)
7. اكتساب مهارة (`oss-work skill <capability> [--install/--no-install]` → installed|already_installed|not_found|failed)
8. فحص/تطبيق تحديث (`oss-work update --check/--apply`)
9. حدّ معدل API (`OSS_RATE_LIMIT` default 60/60s → 429 عند التجاوز) وتحقق طول المهمة (2–10000 حرف → 400)

## 4. API endpoints الحقيقية (من الكود فقط)
- `GET /health`, `GET /status`, `POST /task`, `GET /models`, `GET /` (من `interfaces/api/server.py`)
- JEV: `GET /config`, `POST /route`, `POST /decide` (من `interfaces/api/jev_routes.py`)
- التشغيل: `uvicorn interfaces.api.server:app --host 127.0.0.1 --port 8080` أو `python -m interfaces.api.server` أو `oss-work run|desktop`

## 5. بيانات الدخول/الإعداد للاختبار
- `python -m venv .venv && pip install -e ".[dev]"`؛ الإعداد عبر `.env` (`TELEGRAM_BOT_TOKEN` للتلجرام فقط، `OSS_WORK_SIMULATION_ONLY=1` افتراضيا، `OSS_RATE_LIMIT`)
- الاختبارات: `python -m pytest tests/ -v`؛ لا مصادقة على API المحلي — يعمل localhost بدون مفاتيح

## 6. خارج النطاق (mocked/simulated)
- «100+ نموذج بصفر تكلفة» و«300B خيطا» ادعاءات README غير قابلة للاختبار كعقد؛ التشغيل الافتراضي محاكاة فقط (لا طلبات خارجية حقيقية، لا مفاتيح، لا تعديل ملفات خارج الجذر، بوابات موافقة)؛ تكاملات Meta/Telegram/GitHub/Google/Microsoft وPlaywright الحية تتطلب إعدادا ومفاتيح حقيقية.
