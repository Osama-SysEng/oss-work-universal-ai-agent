"""OS_V1 Media — image & video generation for the agent (clean-room).

Research verdict (Oct 2026, sources in the report):
  IMAGE  open-weights best: FLUX.2-klein / Z-Image (Apache-2.0), Qwen-Image,
         SD3.5 (community).  VIDEO best: Wan2.2-TI2V-5B (Apache-2.0, 720p on
         RTX4090), LTX-2.5 (community), HunyuanVideo 1.5 (Tencent).
  HARDWARE REALITY of this machine: CPU-only (torch 2.14.1+cpu) — local
  diffusion is not practical (Wan2.2 needs a consumer GPU; FLUX on CPU =
  minutes/image). So the working lanes are KEYLESS free public services —
  the same zero-setup philosophy as the FreeLLMAPI lane: no subscriptions,
  no keys, no randomness:
    - images: Pollinations (serving the FLUX family) — measured 0.3-5s.
    - TRUE VIDEO: the public LTX-Video-distilled Space (ZeroGPU, Lightricks)
      — measured 19s for a 5s 704x512 30fps MP4 with real motion. The local
      GPU lane (diffusers + Wan2.2/LTX) stays a documented upgrade path.
  The stitched-keyframes lane survives ONLY as the honest fallback when the
  true-video lane fails — and says so in its output.

CONTENT SAFETY: the image engine ignores non-English prompts (they fall to
unconditional generation — measured NSFW once), so every prompt is
auto-translated to English via text.pollinations.ai (free, keyless, cached)
and every request carries safe=true.

HONESTY POLICY (OSS law):
  - the TRUE lane reports itself as a real video (MP4, real motion, LTX).
  - the FALLBACK reports itself as "بديل مركّب من إطارات — ليس فيديو حقيقياً"
    with the failure reason inline.
  - every file is verified: magic bytes + PIL re-open (+ MP4 ftyp check) —
    a broken file never "succeeds".
"""
from __future__ import annotations

import io
import os
import random
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

IMAGE_BASE = "https://image.pollinations.ai/prompt/"
LTX_SPACE = "Lightricks/ltx-video-distilled"   # TRUE text-to-video, ZeroGPU
DEFAULT_MODEL = "turbo"   # FREE + fastest (0.3-0.9s measured); flux = 1 img/45s/IP
PREMIUM_MODEL = "flux"
ATTEMPTS = 4
REQ_TIMEOUT_S = 180
MIN_IMAGE_BYTES = 2048
DUR_MIN, DUR_MAX = 2, 8
SCENES_MIN, SCENES_MAX = 2, 8
# Client-side pacing (the service says: "1 image every 45 seconds per IP"
# for premium models; turbo tolerated back-to-back in probing) — we pace
# to never trip the limit instead of hammering and hiding failures.
_PACE_S = {"turbo": 6.0, "flux": 50.0}

_MAGICS = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG", ".png"), (b"RIFF", ".webp"))

# محرك الصور (turbo/flux) يفهم الإنجليزية فقط — الوصف العربي يضيع كلياً فيولّد
# عشوائياً (قد ينتج محتوى غير لائق). الترجمة عبر text.pollinations.ai مجاناً بلا
# مفتاح، وتُخزَّن حتى لا تتكرر. عند فشل الترجمة يُمرَّر الأصل بصدق (ويبقى safe=true).
_TRANSLATIONS: dict[str, str] = {}


def to_english(prompt: str) -> tuple[str, bool]:
    """وصف عربي/أي لغة → إنجليزي. يعيد (النص، هل تُرجم)."""
    if prompt.isascii():
        return prompt, False
    if prompt in _TRANSLATIONS:
        return _TRANSLATIONS[prompt], True
    url = ("https://text.pollinations.ai/"
           + urllib.parse.quote("Translate to English, answer with the "
                                "translation only: " + prompt))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (OSS-Work agent)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            tr = r.read().decode("utf-8", "replace").strip()
        tr = tr.strip('"').splitlines()[0][:900] if tr else ""
        ascii_ratio = sum(c.isascii() for c in tr) / max(len(tr), 1)
        if tr and ascii_ratio > 0.9:
            _TRANSLATIONS[prompt] = tr
            return tr, True
    except Exception:  # noqa: BLE001, S110 — فشل الترجمة لا يوقف التوليد (يعاد الأصل)
        pass
    return prompt, False


def media_dir() -> Path:
    d = Path(os.environ.get("OSV_MEDIA_DIR")
             or (Path(__file__).resolve().parent / "media"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def sniff_ext(data: bytes) -> str | None:
    for magic, ext in _MAGICS:
        if data.startswith(magic):
            return ext
    return None


def _verify_mp4(p: Path) -> bool:
    """MP4 سليم: التوقيع ftyp في الإزاحة 4-8 (لا نصدق الامتداد)."""
    try:
        with open(p, "rb") as f:
            head = f.read(12)
        return len(head) >= 12 and head[4:8] == b"ftyp"
    except OSError:
        return False


def _fetch_image(prompt: str, width: int, height: int, model: str,
                 seed: int) -> bytes:
    q = (f"?width={width}&height={height}&model={urllib.parse.quote(model)}"
         f"&nologo=true&safe=true&seed={seed}")
    url = IMAGE_BASE + urllib.parse.quote(prompt[:900], safe="") + q
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (OSS-Work agent)"})
    with urllib.request.urlopen(req, timeout=REQ_TIMEOUT_S) as r:
        return r.read()


# الإعدادات المجرَّبة حياً (نابليون 18.7s) — أعظم فرصة نجاح داخل حصة ZeroGPU
SAFE_CONFIG = (704, 512, 5.0)


def _quota_reason(msg: str) -> str:
    """رسالة حصة ZeroGPU → شرح عربي قابل للفعل (توكن مجاني يرفع الحصة)."""
    m = re.search(r"ZeroGPU quota \((\d+)s requested vs\. (\d+)s left\)"
                  r".*?in (\d\d:\d\d:\d\d)", msg)
    if not m:
        return ""
    return (f"حصة ZeroGPU المجهولة انتهت (المطلوب {m.group(1)}s والمتاح "
            f"{m.group(2)}s — تعود بعد {m.group(3)}). الحل: توكن Hugging Face "
            "مجاني من huggingface.co/settings/tokens يوضع في متغير "
            "OSV_HF_TOKEN فيرفع الحصة كثيراً")


def _verify_video(p: Path) -> bool:
    """MP4/WebP سليم: MP4 بتوقيع ftyp، وWebP يُعاد فتحه بPIL ويعدّ الإطارات."""
    try:
        with open(p, "rb") as f:
            head = f.read(12)
        if head[4:8] == b"ftyp":
            return True
        if head[:4] == b"RIFF":
            img = Image.open(p)
            img.load()
            return getattr(img, "n_frames", 1) >= 1
    except Exception:  # noqa: BLE001 — ملف تالف = فشل
        return False
    return False


def _ltx_generate(prompt: str, duration_s: float, width: int, height: int,
                  seed: int | None, image_path: str | None = None
                  ) -> tuple[Path, int]:
    """TRUE text-to-video via the public LTX-Video-distilled Space (ZeroGPU).
    Returns (mp4_path, seed_used); raises on any failure — the caller falls
    back to the honest stitched lane and reports the reason. A free HF token
    (env OSV_HF_TOKEN) lifts the anonymous quota wall."""
    from gradio_client import Client  # optional dependency — honest error if absent

    tok = os.environ.get("OSV_HF_TOKEN", "").strip()
    client = Client(LTX_SPACE, verbose=False, token=tok or None)
    result = client.predict(
        prompt=prompt,
        negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted",
        input_image_filepath=image_path,   # صورة بداية = روح Genjutsu (image-to-video)
        input_video_filepath=None,
        height_ui=float(height),
        width_ui=float(width),
        mode="text-to-video",
        duration_ui=float(duration_s),
        ui_frames_to_use=9,
        seed_ui=int(seed) if seed is not None else 0,
        randomize_seed=seed is None,
        ui_guidance_scale=3,
        improve_texture_flag=True,
        api_name="/text_to_video",
    )
    video, seed_used = result
    src = video.get("video") if isinstance(video, dict) else video
    if not src:
        raise RuntimeError("استجابة بلا ملف فيديو")
    out = media_dir() / time.strftime("osv_vid_%Y%m%d_%H%M%S.mp4")
    shutil.copyfile(src, out)
    if out.stat().st_size < 10_000:
        raise RuntimeError("ملف الفيديو ضئيل — يُرفض")
    return out, int(seed_used)


class MediaKit:
    """One kit per process — stateless generation, files on disk."""

    def __init__(self):
        self._last_req = 0.0

    def _pace(self, model: str) -> None:
        gap = time.time() - self._last_req
        wait = _PACE_S.get(model, 6.0) - gap
        if wait > 0:
            time.sleep(wait)

    def generate_image(self, prompt: str, width: int = 1024, height: int = 1024,
                       model: str = DEFAULT_MODEL, seed: int | None = None,
                       attempts: int | None = None
                       ) -> tuple[bool, str]:
        prompt = (prompt or "").strip()
        if not prompt:
            return False, "الوصف فارغ — اكتب ماذا تريد أن ترى"
        prompt, translated = to_english(prompt)
        width = min(max(int(width), 256), 1920)
        height = min(max(int(height), 256), 1920)
        seed = random.randint(0, 999_999) if seed in (None, "") else int(seed)
        n_attempts = ATTEMPTS if attempts is None else max(1, int(attempts))
        last = ""
        for attempt in range(n_attempts):
            self._pace(model)
            t0 = time.time()
            try:
                data = _fetch_image(prompt, width, height, model, seed + attempt)
                self._last_req = time.time()
                ext = sniff_ext(data)
                if ext is None or len(data) < MIN_IMAGE_BYTES:
                    last = f"استجابة ليست صورة ({len(data)} بايت)"
                    continue
                img = Image.open(io.BytesIO(data))   # PIL re-opens = really decodable
                img.load()
                out = media_dir() / (time.strftime("osv_img_%Y%m%d_%H%M%S") + ext)
                out.write_bytes(data)
                tr_note = " (ترجمنا وصفك للإنجليزية — محرك الصور يفهمها فقط)" if translated else ""
                return True, (f"صورة مولّدة: {out} ({img.width}x{img.height}, "
                              f"{len(data) // 1024}KB، نموذج {model}، "
                              f"{time.time() - t0:.1f}s، seed={seed}){tr_note}")
            except urllib.error.HTTPError as exc:
                self._last_req = time.time()
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001, S110 — empty body is fine
                    pass
                if exc.code == 402:
                    m = re.search(r"[Rr]etry after (\d+)", detail or "")
                    wait = (int(m.group(1)) + 3) if m else 45
                    last = "حد المعدل المجاني للخدمة (402 — الصور المجانية متباعدة لكل IP)"
                    time.sleep(wait)
                    continue
                last = f"HTTP {exc.code}"
            except Exception as exc:  # noqa: BLE001 — network/service variance
                self._last_req = time.time()
                last = f"{type(exc).__name__}: {str(exc)[:120]}"
                time.sleep(3 * (attempt + 1))
        return False, (f"تعذّر توليد الصورة بعد {n_attempts} محاولات — {last}. "
                       + ("بديل أسرع: النموذج turbo (مجاني بلا حد عملي)"
                          if model != "turbo" else
                          "حتى turbo خاضع للتقييد اللحظي من الخدمة — أعد المحاولة بعد قليل"))

    def generate_video(self, prompt: str | list[str], duration_s: int = 5,
                       width: int = 704, height: int = 512,
                       image_path: str | None = None, **a) -> tuple[bool, str]:
        """TRUE video with real motion (LTX-Video, open source) — ONE continuous
        scene described richly. image_path = صورة بداية (image-to-video، روح
        Genjutsu). The stitched-keyframes lane survives only as the honest
        fallback and SAYS it is not a true video."""
        if isinstance(prompt, (list, tuple)):
            prompt = "، ".join(str(p).strip() for p in prompt if str(p).strip())
        prompt = (prompt or "").strip()
        if not prompt:
            return False, "الوصف فارغ — صف المشهد المتحرك الذي تريده"
        prompt, translated = to_english(prompt)
        duration_s = min(max(float(duration_s), DUR_MIN), DUR_MAX)
        width = min(max(int(width), 256), 1280)
        height = min(max(int(height), 256), 1280)
        t0 = time.time()
        tr_note = " (ترجمنا وصفك للإنجليزية)" if translated else ""
        configs = [(width, height, duration_s)]
        if (width, height, float(duration_s)) != SAFE_CONFIG:
            # الأبعاد الثقيلة تستهلك حصة أكبر — إعادة محاولة واحدة بالمجرَّب
            configs.append(SAFE_CONFIG)
        reason = ""
        for ci, (cw, ch, cd) in enumerate(configs):
            try:
                out, seed = _ltx_generate(prompt, cd, cw, ch, None, image_path)
                if not _verify_mp4(out):
                    raise RuntimeError("الملف ليس MP4 سليماً")
                retried = (" (أعدنا المحاولة بالأبعاد المجرَّبة 704x512@5s)"
                           if ci > 0 else "")
                return True, (f"فيديو حقيقي بحركة فعلية: {out} "
                              f"({cd}s، {out.stat().st_size // 1024}KB، "
                              f"seed={seed}، نموذج LTX-Video مفتوح المصدر، "
                              f"{time.time() - t0:.1f}s){tr_note}{retried}")
            except ImportError:
                reason = "gradio_client غير مثبّت (pip install gradio_client)"
                break   # إعادة المحاولة لا تصلح غياب الحزمة
            except Exception as exc:  # noqa: BLE001 — quota/queue/space variance
                reason = (_quota_reason(str(exc))
                          or f"{type(exc).__name__}: {str(exc)[:160]}")
        # ---- البديل الصادق: مشاهد مولّدة تتبدل — يُعلن أنه ليس فيديو حقيقياً ----
        scenes = [s.strip() for s in re.split(r"[،,;.]|\band\b|\bthen\b", prompt)
                  if s.strip()]
        if len(scenes) < SCENES_MIN:
            scenes = [prompt, prompt + ", different camera angle"]
        ok, obs = self._stitch_scenes(scenes[:SCENES_MAX], width, height)
        if ok:
            return True, (f"⚠️ بديل مركّب من إطارات — ليس فيديو حقيقياً: {obs} | "
                          f"سبب تعطل الممر الحقيقي: {reason}")
        return False, f"فشل الفيديو الحقيقي ({reason}) وفشل البديل أيضاً: {obs}"

    def _stitch_scenes(self, scenes: list[str], width: int, height: int
                       ) -> tuple[bool, str]:
        """Stitch N generated keyframes into an animated clip (WebP/GIF).
        Honest-by-construction: only called as the labeled fallback."""
        frames, files, t0 = [], [], time.time()
        for i, p in enumerate([p for p in scenes if p]):
            # attempts=2: البديل يجب أن يفشل بسرعة ليتحول الوكيل لممر الحركة
            # (مقدمات الكاميرا) بدل حرق دقائق في إعادة السحب على خدمة مُقيَّدة
            ok, obs = self.generate_image(p, width, height, DEFAULT_MODEL,
                                          attempts=2)
            if not ok:
                return False, f"فشل المشهد {i + 1}: {obs}"
            path = obs.split(": ", 1)[1].split(" (")[0]
            files.append(path)
            img = Image.open(path).convert("RGB").resize((width, height))
            frames.append(img)
        if len(frames) < SCENES_MIN:
            return False, "مشاهد صالحة أقل من الحد"
        out = media_dir() / time.strftime("osv_vid_%Y%m%d_%H%M%S.webp")
        try:
            frames[0].save(out, save_all=True, append_images=frames[1:],
                           duration=1600, loop=0, method=4)
        except Exception:  # noqa: BLE001 — webp encoder gaps → gif fallback
            out = out.with_suffix(".gif")
            frames[0].save(out, save_all=True, append_images=frames[1:],
                           duration=1600, loop=0)
        check = Image.open(out); check.load()
        return True, (f"{out} ({len(frames)} مشاهد مولّدة، "
                      f"{out.stat().st_size // 1024}KB، {time.time() - t0:.1f}s)")

    def list_media(self, limit: int = 20) -> tuple[bool, str]:
        files = sorted(media_dir().glob("osv_*"), key=lambda p: p.stat().st_mtime,
                       reverse=True)[:max(1, min(int(limit), 50))]
        if not files:
            return True, "(لا وسائط بعد)"
        # المسارات الكاملة — الوكيل يمررها مباشرة إلى motion_generate/genjutsu
        return True, "\n".join(f"{p} — {p.stat().st_size // 1024}KB" for p in files)


def media_tools(kit: MediaKit) -> dict:
    """Agent-facing registry (merged into the agent loop like device_tools)."""
    def _video(ctx, prompt="", prompts=None, duration_s=5, width=704, height=512,
               image_path=None, **a):
        # توافق الصيغة القديمة: prompts=[...] → يُدمج وصفاً واحداً
        if not prompt and prompts:
            prompt = prompts
        return kit.generate_video(prompt, duration_s, int(width), int(height),
                                  image_path=image_path)

    def _motion(ctx, image="", preset="zoom_in", duration_s=5, fps=30,
                width=704, height=512, **a):
        import osv_motion as mo
        return mo.motion_clip(str(image), str(preset), float(duration_s),
                              int(fps), int(width), int(height))

    def _genjutsu(ctx, image="", presets=None, duration_s=4, **a):
        import osv_motion as mo
        if isinstance(presets, str):
            presets = [p.strip() for p in presets.split(",") if p.strip()]
        return mo.genjutsu_variants(str(image), presets, float(duration_s))

    def _cinema(ctx, scenes=None, transition="crossfade", fps=30, **a):
        import osv_motion as mo
        return mo.compose_cinema(scenes or [], str(transition), int(fps))

    return {
        "image_generate": {
            "fn": lambda ctx, prompt="", width=1024, height=1024, model=DEFAULT_MODEL, **a:
                kit.generate_image(prompt, int(width), int(height), str(model)),
            "args": {"prompt": "str وصف بالعربية أو الإنجليزية",
                     "width": "int (256-1920)", "height": "int",
                     "model": "turbo (سريع مجاني)|flux (أجمل)"},
            "desc": "توليد صورة حقيقية من وصف نصي — الناتج ملف فعلي على القرص. استخدمها فوراً عند طلب أي صورة أو شعار أو رسم — لا تعتذر ولا تقل إنك نصي"},
        "video_generate": {
            "fn": _video,
            "args": {"prompt": "str وصف مشهد واحد متحرك بتفاصيله (الشخصية + الحركة + المكان + الإضاءة)",
                     "image_path": "str (اختياري) صورة بداية → تحريكها توليدياً image-to-video",
                     "duration_s": "int مدة الفيديو بالثواني (2-8)",
                     "width": "int (256-1280)", "height": "int"},
            "desc": "توليد فيديو حقيقي بحركة فعلية (MP4 من نموذج LTX-Video مفتوح المصدر) — وصف مشهد واحد غني: مثال «نابليون بقبعة بيكونت ومعطفه الرمادي يسير على سطح سفينة حربية وسط جنوده المتصطفين، أمواج وغروب ذهبي، سينمائي». يقبل image_path لتحريك صورة موجودة (image-to-video). استخدمه فوراً عند أي طلب فيديو — لا تعتذر ولا تقل إنك نصي"},
        "motion_generate": {
            "fn": _motion,
            "args": {"image": "str مسار الصورة المولّدة (من image_generate)",
                     "preset": "zoom_in|zoom_out|crash_zoom|pan_left|pan_right|pan_up|pan_down|orbit|dolly_in|handheld|ken_burns|vertigo",
                     "duration_s": "int (2-10)", "fps": "int (افتراضي 30)",
                     "width": "int", "height": "int"},
            "desc": "حركة كاميرا سينمائية احترافية فوق مشهد مولّد (MP4 في ثوانٍ، بلا حصة، غير محدود، محلية 100% بلا خدمات خارجية) — أسلوب Higgsfield: ولّد الصورة بimage_generate ثم طبق مسبقاً من zoom_in أو orbit أو crash_zoom أو ken_burns أو dolly_in أو handheld أو vertigo. مثال سير عمل: صورة نابليون → preset=crash_zoom → مقطع ملحمي فوري. إذا فشل توليد صورة جديدة (تقيي الخدمة/الحصة) فاستخدم أي صورة موجودة في مجلد media من media_list — الحركة تعمل على أي صورة موجودة. للشخصيات المتحركة توليدياً استخدم video_generate"},
        "genjutsu_variants": {
            "fn": _genjutsu,
            "args": {"image": "str مسار الصورة", "duration_s": "int مدة كل مقطع",
                     "presets": "list أو str مفصولة بفواصل (افتراضي 4 رؤيات)"},
            "desc": "صورة واحدة تدخل — عدة مقاطع سينمائية تخرج (zoom_in, orbit, ken_burns, crash_zoom افتراضياً). مثالية لصناعة تشكيلة ريلز من صورة واحدة بسرعة قياسية. إذا فشل توليد صورة جديدة فاستخدم أي صورة موجودة في media من media_list"},
        "cinema_compose": {
            "fn": _cinema,
            "args": {"scenes": "list[{image: مسار, preset: اسم المسبق, duration: ثوانٍ}] — ولّد كل صورة بimage_generate أولاً",
                     "transition": "crossfade|cut", "fps": "int"},
            "desc": "ستوري بورد سينمائي: 2-8 مشاهد (كل مشهد صورة مولّدة + مسبق حركة + مدة) → فيلم واحد MP4 بانتقالات crossfade. مثال: [{image:'a.png', preset:'zoom_in', duration:4}, {image:'b.png', preset:'pan_right', duration:4}]"},
        "media_list": {
            "fn": lambda ctx, **a: kit.list_media(),
            "args": {}, "desc": "سرد الوسائط المولّدة سابقاً"},
    }
