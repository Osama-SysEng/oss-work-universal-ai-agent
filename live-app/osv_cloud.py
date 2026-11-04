"""osv_cloud.py — Supabase capability layer (the "managed backend" pillar).

Competitive analysis (4 Nov 2026): OnSpace.AI's differentiator is a managed
backend — per their own FAQ: Supabase (auth + PostgreSQL + file storage +
realtime). That is a public service, not proprietary magic — so OSS Work's
agent gets the SAME power: it can wire the apps it builds to a real Supabase
project (the user's own free account) instead of the toy SQLite path, which
is what makes agent-built apps survive 1000+ users.

Honesty rules honored here:
- secrets never live in code or the repo — env vars or data/supabase_config.json
  (data/ is outside the repo); the service key is used NOWHERE.
- the tools report real HTTP outcomes verbatim; a missing key returns the
  exact remedy instead of a fake success.
- stdlib only (urllib), strict timeouts, no new dependencies.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

_CFG_NAMES = {
    "url": ("OSV_SUPABASE_URL", "SUPABASE_URL", "url"),
    "anon": ("OSV_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY", "anon_key"),
    "service": ("OSV_SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY", "service_key"),
    "token": ("OSV_SUPABASE_TOKEN", "SUPABASE_ACCESS_TOKEN", "access_token"),
}

REMEDY = (
    "مفاتيح Supabase غير موجودة. الحصول عليها مجاناً في دقيقتين: "
    "1) supabase.com → New project (الخطة المجانية تكفي: قاعدة Postgres + "
    "مصادقة + تخزين ملفات + realtime). "
    "2) من لوحة المشروع: Project Settings → API. "
    "3) ضع القيمتين URL و anon key في متغيرات البيئة OSV_SUPABASE_URL و "
    "OSV_SUPABASE_ANON_KEY، أو في ملف data/supabase_config.json بصيغة "
    '{"url": "...", "anon_key": "..."}. '
    "مفتاح الخدمة service_key اختياري ولا يُكتب في أي ملف يُشارك."
)


def _load_cfg() -> dict:
    """Env vars win (12-factor); then data/supabase_config.json (outside the repo)."""
    cfg = {}
    for k, (env1, env2, json_key) in _CFG_NAMES.items():
        v = os.environ.get(env1) or os.environ.get(env2) or ""
        if not v:
            p = Path(__file__).parent / "data" / "supabase_config.json"
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                v = str(d.get(json_key, "") or "")
            except Exception:  # noqa: BLE001 — missing file is the normal case
                v = ""
        cfg[k] = v.strip()
    return cfg


def _http(url: str, headers: dict, timeout: int = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — network errors are observations
        return 0, f"{type(e).__name__}: {e}"


def tool_supabase_status(ctx) -> tuple[bool, str]:
    """Diagnose the Supabase connection with a REAL request — no fake success."""
    cfg = _load_cfg()
    if not cfg["url"] or not cfg["anon"]:
        return False, REMEDY
    st, body = _http(cfg["url"].rstrip("/") + "/rest/v1/",
                     {"apikey": cfg["anon"],
                      "Authorization": f"Bearer {cfg['anon']}"})
    if st == 200:
        extra = []
        if cfg["service"]:
            extra.append("مفتاح الخدمة موجود (لا يُكتب في أي ملف مشترك)")
        if cfg["token"]:
            extra.append("توكن الإدارة موجود (يمكن تنفيذ schema.sql برمجياً)")
        return True, ("المشروع يستجيب على REST ✓ " + cfg["url"]
                      + ("\n" + " | ".join(extra) if extra else ""))
    if st == 401:
        return False, (f"الرابط يستجيب لكن المفتاح مرفوض ({st}) — anon key "
                       "غير صحيح. انسخه من Project Settings → API. " + REMEDY)
    return False, (f"المشروع لا يستجيب (HTTP {st}): {body[:200]} — تحقق من أن "
                   "المشروع فعّال (مشروع Supabase المتوقف يُستأنف من اللوحة). "
                   + REMEDY)


_SCHEMA_TMPL = """-- {title} — PostgreSQL schema (Supabase)
-- انسخ كله والصقه في: Supabase Dashboard → SQL Editor → Run
-- RLS مفعّل على كل جدول: الأنفونيم يقرأ العلني فقط، والمستخدم يكتب ما يملكه فقط.

create table if not exists public.profiles (
  id uuid primary key references auth.users on delete cascade,
  display_name text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "read own profile" on public.profiles
  for select using (auth.uid() = id);
create policy "upsert own profile" on public.profiles
  for insert with check (auth.uid() = id);
create policy "update own profile" on public.profiles
  for update using (auth.uid() = id);

-- جدول المحتوى الخاص بالمهمة — عدّله ليناسب {title}:
create table if not exists public.items (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users on delete cascade,
  title text not null,
  body text,
  created_at timestamptz not null default now()
);

alter table public.items enable row level security;

create policy "items are readable by everyone" on public.items
  for select using (true);
create policy "users insert own items" on public.items
  for insert with check (auth.uid() = user_id);
create policy "users manage own items" on public.items
  for update using (auth.uid() = user_id);
create policy "users delete own items" on public.items
  for delete using (auth.uid() = user_id);
"""

_CLIENT_JS = """// Supabase browser client — يعمل مباشرة من الواجهة
// <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
const SUPABASE_URL = "{url}";
const SUPABASE_ANON_KEY = "{anon}";
const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// تسجيل مستخدم (حقيقي، موجّه على auth.users):
// await sb.auth.signUp({{ email, password }});
// دخول: await sb.auth.signInWithPassword({{ email, password }});
// قراءة: await sb.from('items').select('*');
// كتابة: await sb.from('items').insert({{ title }});
// لحظي: sb.channel('items-ch').on('postgres_changes',
//         {{ event: '*', schema: 'public', table: 'items' }}, payload => {{}}).subscribe();
"""

_CLIENT_PY = '''"""Supabase server-side client (supabase-py) — pip install supabase"""
from supabase import create_client

SUPABASE_URL = "{url}"
SUPABASE_ANON_KEY = "{anon}"
sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# تسجيل: sb.auth.sign_up({{"email": e, "password": p}})
# قراءة:  sb.table("items").select("*").execute()
# كتابة:  sb.table("items").insert({{"title": t}}).execute()
'''

_STEPS = """# خطوات التهيئة (مرة واحدة، دقيقتان)

1. supabase.com → تسجيل مجاني → **New project** (اختر أقرب منطقة).
2. **Project Settings → API**: انسخ `Project URL` و `anon public key`.
3. ضعهما في `data/supabase_config.json` بجانب ملفات النظام:
   `{"url": "...", "anon_key": "..."}` أو في متغيرات البيئة
   `OSV_SUPABASE_URL` / `OSV_SUPABASE_ANON_KEY`.
4. **SQL Editor** → الصق محتوى `supabase/schema.sql` → **Run**.
5. أعد تشغيل أداة `supabase_status` ثم `supabase_smoke` للتأكد أن الجداول حية.
6. التخزين (اختياري): Storage → New bucket → اجعله public أو اربطه بـRLS
   على `storage.objects`.

> لماذا هذا يتحمل 1000+ مستخدم؟ لا يوجد خادم محلي يتسرب منه الحمل:
> Auth وPostgres والتخزين وRealtime تعمل على بنية Supabase المُدارة،
> والواجهة تتصل بها مباشرة بمفتاح anon العام تحت حماية RLS.
"""


def tool_supabase_setup(ctx, title: str = "تطبيقي") -> tuple[bool, str]:
    """Scaffold a Supabase-ready project into the workspace (4 files)."""
    cfg = _load_cfg()
    if not cfg["url"] or not cfg["anon"]:
        return False, REMEDY
    base = Path(ctx.workspace) / "supabase"
    base.mkdir(parents=True, exist_ok=True)
    written = []
    files = {
        "schema.sql": _SCHEMA_TMPL.format(title=title),
        "client.js": _CLIENT_JS.format(url=cfg["url"], anon=cfg["anon"]),
        "client.py": _CLIENT_PY.format(url=cfg["url"], anon=cfg["anon"]),
        "SETUP-STEPS.md": _STEPS,
    }
    try:
        for name, content in files.items():
            (base / name).write_text(content, encoding="utf-8")
            written.append(f"supabase/{name}")
    except OSError as e:
        return False, f"فشل كتابة ملفات التهيئة: {e}"
    return True, ("جُهّزت 4 ملفات في مساحة العمل: " + ", ".join(written)
                  + "\nالخطوة المطلوبة من المستخدم: انسخ schema.sql إلى SQL "
                  "Editor في لوحة Supabase واضغط Run (انظر SETUP-STEPS.md). "
                  "بعد ذلك اختبر بـ supabase_smoke على جدول items.")


def tool_supabase_smoke(ctx, table: str = "items") -> tuple[bool, str]:
    """Probe a REAL table through PostgREST with the anon key — the honest
    'is it live' check: 200 = table serving, 401 = bad key, 404/PGRST205 =
    schema not applied yet."""
    cfg = _load_cfg()
    if not cfg["url"] or not cfg["anon"]:
        return False, REMEDY
    tbl = (table or "items").strip().strip("/") or "items"
    st, body = _http(
        f"{cfg['url'].rstrip('/')}/rest/v1/{tbl}?select=*&limit=1",
        {"apikey": cfg["anon"],
         "Authorization": f"Bearer {cfg['anon']}"})
    if st == 200:
        n = "0 صفوف" if body.strip() in ("[]", "") else "صفوف موجودة"
        return True, (f"الجدول {tbl} حي ويخدم عبر REST ✓ ({n}) — التطبيق "
                      "المبني يمكنه القراءة والكتابة فوراً تحت RLS.")
    if st == 401 or st == 403:
        return False, (f"المفتاح مرفوض ({st}) — راجع anon key. {REMEDY}")
    if "PGRST205" in body or st == 404:
        return False, (f"الجدول {tbl} غير موجود بعد — نفّذ supabase/schema.sql "
                       "في SQL Editor (انظر supabase/SETUP-STEPS.md) ثم أعد "
                       "الفحص.")
    return False, f"HTTP {st}: {body[:200]}"
