# PRD — OSS Work Universal AI Agent

## 1. نظرة عامة
وكيل ذكاء اصطناعي مفتوح المصدر (Apache-2.0): محرك خيال Ultra IQ يعمل محليا، توجيه محلي، 8 وكلاء متخصصين، واجهات CLI وDesktop API محلي، ونظام OS محلي مستقل (oss-os). لا مفاتيح، لا سحابة.

## 2. المستخدمون
- مستخدم نهائي (CLI/Web/OS)
- مطوّر/مشغّل (CLI، API محلي، مهارات، تحديثات)

## 3. الميزات الأساسية (قابلة للاختبار)
1. إرسال مهمة عبر API المحلي (`POST /task` بجسم `{"task": "...", "user_id": "..."}` → `status: completed|failed|busy`)
2. فحص صحة وحالة الوكيل (`GET /health`, `GET /status` → version/mode/simulation_only/uptime/total_tasks/active_tasks/users)
3. سرد النماذج المتاحة (`GET /models?limit=&offset=` → models/total/limit/offset)
4. أوامر CLI: `run|chat|status|models|imagine|skill|update|desktop|data-dir` (Typer `oss-work`) + أوامر النظام `oss-os boot|status|run|tasks|submit|jobs|drain|skill-new|serve`
5. تشغيل مهمة CLI (`oss-work chat "مهمة" --user local`) وتفاعلي (`oss-work desktop`)
6. محرك الخيال (`oss-work imagine "مهمة" --threads 50 --depth 20` → solution/confidence/invented/threads_explored/simulation_branches)
7. عرض مهارة (`oss-work skill` → self-built local skills; new ones via `oss-os skill-new <name> <purpose>`)
8. فحص/تطبيق تحديث (`oss-work update --check/--apply`)
9. حدّ معدل API (`OSS_RATE_LIMIT` default 60/60s → 429 عند التجاوز) وتحقق طول المهمة (2–10000 حرف → 400)

## 4. API endpoints الحقيقية (من الكود فقط)
- `GET /health`, `GET /status`, `POST /task`, `GET /models`, `GET /` (من `interfaces/api/server.py`)
- التشغيل: `uvicorn interfaces.api.server:app --host 127.0.0.1 --port 8080` أو `python -m interfaces.api.server` أو `oss-work run|desktop`

## 5. بيانات الدخول/الإعداد للاختبار
- `python -m venv .venv && pip install -e ".[dev]"`؛ الإعداد عبر `.env` (`OSS_WORK_SIMULATION_ONLY=1` افتراضيا، `OSS_RATE_LIMIT`)؛ المحرك المحلي عبر `OSS_LOCAL_URL` (llama-server، بلا مفاتيح)
- الاختبارات: `python -m pytest tests/ -v`؛ لا مصادقة على API المحلي — يعمل localhost بدون مفاتيح

## 6. خارج النطاق (mocked/simulated)
- النظام محلي فقط (OS v1): لا طلبات خارجية، لا مفاتيح، لا تعديل ملفات خارج الجذر، بوابات موافقة؛ تكاملات التكامل المحلية فقط (webhook/rest_api عبر loopback + سجل محلي).
