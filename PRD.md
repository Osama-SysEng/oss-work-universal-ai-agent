# PRD — OSS Work / OS_V1

**المصدر الوحيد للحقيقة:** كل نقطة نهاية مذكورة هنا مستخرجة من `osv1/interface/api.py`.
لا يوجد في هذه الوثيقة أي نقطة وهمية.

**المنتج:** وكيل ذكاء اصطناعي محلي موحّد يخطّط ويقرر ويتحقق وينفّذ على جهاز المستخدم.
**الاستقلالية:** بلا مزوّد، بلا مفاتيح، وبلا إنترنت في المسار الأساسي.
**الوضع الافتراضي:** `Plan` (لا تنفيذ) — التنفيذ يتطلب `Build`.

---

## 1. تشغيل المنتج

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q          # الاختبارات تعمل بلا إنترنت وبلا محرك
python -m osv1.interface.cli status
python -m osv1.interface.api        # الواجهة الحية على http://127.0.0.1:8080
```

المحرك المحلي (اختياري، يضيف قدرات لغوية حقيقية):
`C:\tools\llama\start-engine.cmd` ثم `OSS_LOCAL_URL=http://127.0.0.1:11400`.

## 2. نقاط النهاية (Local API)

| الطريقة | المسار | الوظيفة | رمز الحالة |
|---|---|---|---|
| GET | `/` | لوحة التحكم الحية (HTML + SSE) | 200 |
| GET | `/health` | `{status, product, model}` | 200 |
| GET | `/status` | حالة النظام الحقيقية: المحرك، الأدوات، الأذونات،Memory، Audit | 200 |
| POST | `/plan` | `{task, agent_id}` → خطة **بدون** تنفيذ | 200 / 422 |
| POST | `/build` | `{task, agent_id}` → تنفيذ + تحقق + سجل | 200 / 422 |
| GET | `/agents?limit&offset&domain&specialization` | قائمة الوكلاء (300) مع ترقيم | 200 |
| GET | `/agents/{agent_id}` | وكيل واحد | 200 / 404 |
| GET | `/catalog` | أعداد حقيقية: 30 مجال × 10 تخصصات = 300 | 200 |
| GET | `/events` | تدفّق SSE للأحداث الحقيقية أثناء العمل | 200 |
| GET | `/memory?kind&limit` | الذاكرة (4 أنواع) | 200 |
| POST | `/memory/export` | تصدير الذاكرة (تحكّم المستخدم) | 200 |
| DELETE | `/memory/{entry_id}` | حذف عنصر ذاكرة | 200 / 404 |
| GET | `/audit?limit` | سجل الأفعال (سلسلة تجزئة) | 200 |
| GET | `/audit/verify` | التحقق من سلامة السجل | 200 |
| GET | `/permissions` | الأذونات الممنوحة | 200 |
| POST | `/permissions/grant` | `{scope, target, readonly}` | 200 |
| POST | `/permissions/revoke` | `{scope, target}` | 200 |
| GET | `/approvals` | الموافقات المعلّقة | 200 |
| POST | `/approvals/{approval_id}/decide` | `{approve, by}` | 200 / 404 |
| POST | `/killswitch/engage` | إيقاف فوري لكل النشاط | 200 |
| POST | `/killswitch/release` | استئناف | 200 |
| GET | `/metrics` | المقاييس الخمسة + حالة System One | 200 |
| GET | `/provenance` | سجل المصدر والترخيص لكل ما يستخدمه النظام | 200 |
| POST | `/provenance` | `{kind, name, origin, license, version, notes}` | 200 |
| GET | `/context` | نافذة السياق حسب فئة الجهاز | 200 |
| GET | `/qualities` | الصفات الثلاث عشرة: القانون والقاعدة والاختبار | 200 |
| GET | `/qualities/report` | ما هو مقيس اليوم وما يبقى هدفاً | 200 |

**قواعد التحقق:** `task` بين حرفين و10.000 حرف · `agent_id` اختياري · `limit` بين 1 و500 · `scope` من: `files`, `network`, `programs`, `irreversible` · `kind` من: `model`, `dataset`, `tool`, `dependency`, `skill`.

## 3. واجهة سطر الأوامر

`oss-v1 <command>`:

`plan` · `build` · `agents` · `agent` · `status` · `memory` · `audit` · `grant` · `revoke` · `approvals` · `kill` · `metrics` · `provenance` · `evaluate` · `qualities` · `context` · `practice` · `weekly` · `serve` · `version`

## 4. الوكلاء الـ300

- 30 مجالاً (`osv1/agents/domains.py`) × 10 تخصصات (`osv1/agents/specializations.py`) = **300 وكيل**.
- لكل وكيل: أدوات مسموحة، مستوى خطورة، قواعد تحقق، قالب خطة، وموجّه لغوي.
- التوجيه: System One أولاً (تصنيف على 30 خياراً)، ثم احتياطي تعيين الكلمات المفتاحية.

## 5. خارج النطاق (بالصراحة)

- لا مصادقة على API المحلي (يربط بـ loopback فقط) — تُضاف مع النشر على الشبكة.
- لا تحميل من الشبكة ولا استدعاء مزوّد خارجي في المسار الأساسي.
- لا أوزان نموذج مضمّنة: المحرك المحلي يقدّمها.
- تدريب LoRA حقيقي غير مضمّن: الأثر الحالي هو ملف تفضيلات مشفّر على الجهاز.

## 6. معايير القبول

1. `pytest` أخضر بلا إنترنت وبلا مفاتيح.
2. `Plan` لا ينفّذ شيئاً؛ `Build` ينفّذ ما وافق عليه المستخدم فقط.
3. كل فعل غير قابل للتراجع يطلب موافقة بشرية صريحة.
4. مفتاح الإيقاف يوقف كل شيء فوراً.
5. سلسلة سجل التدقيق قابلة للتحقق، والأسرار لا تظهر فيه.
6. المقاييس تُبلّغ مع عدد العينات؛ ما بلا عينات لا يُبلّغ كنتيجة.
