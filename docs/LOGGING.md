# Structured Logging — oss-work

- الوحدة: `core/obs_logging.py` (stdlib فقط، مقتبسة من `C:\pgload\logging_template.py`، `SERVICE=oss-work`).
- السكيما لكل سطر JSON: `timestamp` (UTC ISO-8601 ms) + `level` + `service` + `env` + `version` + `request_id` + `event` + `message`.
- الربط: `interfaces/api/server.py` يستخدم `get_logger("oss-work-api")` + middleware بسيط يقرأ `X-Request-ID` (أو يولّد `new_request_id()`)، يخزّنه في `request_id_ctx`، يعيده في ترويسة الرد، ويسجّل سطر وصول واحد (`http.access`: method + path + status). لا تُسجَّل أجسام الطلبات أو الترويسات الحساسة.
- المتغيرات (`.env.example`): `SERVICE_NAME=oss-work`، `LOG_LEVEL=info`، `GIT_SHA=dev`، و`ENVIRONMENT` للبيئة. مستوى السجل يُقرأ من `LOG_LEVEL` (وإلا `info` للإنتاج و`debug` للتطوير).
- الأسرار: أي حقل يحمل مفتاحًا مثل password/token/secret/authorization/cookie يُقنَّع `***` تلقائيًا عبر `_redact`. ممنوع تسجيل أسرار حقيقية.
