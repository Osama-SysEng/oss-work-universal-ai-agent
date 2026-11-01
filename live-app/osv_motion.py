"""OS_V1 Motion — Higgsfield-style cinematic camera presets (clean-room).

RESEARCH VERDICT (Nov 2026): Higgsfield's professional look is largely
PROGRAMMATIC camera motion (zoom/pan/orbit/crash-zoom/handheld...) applied to
generated stills, plus a storyboard composer with transitions. That lane is
reproducible locally with OpenCV: no quota, no keys, ~2-4s per 5s clip on CPU
— 10x faster than a video model. TRUE generative motion (a character walking)
stays on the LTX-Video lane (osv_media), including image-to-video.

HONESTY POLICY (OSS law): motion output = real camera motion over a GENERATED
still — reported as such (حركة كاميرا سينمائية فوق مشهد مولّد), never claimed
to be generative character motion.
"""
from __future__ import annotations

import math
import os
import shutil
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

FPS = 30
DUR_MIN, DUR_MAX = 2.0, 10.0


def _stage_path(prefix: str, suffix: str = ".mp4") -> Path:
    """مسار كتابة ASCII فريد في %TEMP% — مرمّز cv2 (VideoWriter/imwrite) يفشل
    بصمت مع المسارات العربية في ويندوز، ودقة الثانية في strftime تسبب تصادماً
    بين مقطعين متتاليين. mkstemp يضمن الفريدة؛ الملف يُنقل لاحقاً بshutil."""
    fd, p = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    os.close(fd)
    os.remove(p)   # الملف يُعاد إنشاؤه بالمرمّز
    return Path(p)


def _publish(staged: Path) -> Path:
    """انقل الملف المكتوب في التمب إلى مجلد الوسائط (يدعم العربية)."""
    out = motion_dir() / staged.name
    shutil.move(str(staged), str(out))
    return out

# كل مسبق: دالة t∈[0,1] → (مركز x, مركز y, تكبير) في إحداثيات نسبية.
# التكبير >1 يعني اقتراباً (crop أصغر). فلسفة Higgsfield: حركة كاميرا مقنعة.
def _zoom_in(t):
    return 0.5, 0.5, 1.0 + 0.45 * t

def _zoom_out(t):
    return 0.5, 0.5, 1.45 - 0.45 * t

def _crash_zoom(t):
    return 0.5, 0.5, 1.0 + 0.6 * (t ** 2.2)   # تسارع عنيف في النهاية

def _pan_left(t):
    return 0.5 + 0.18 * t, 0.5, 1.12

def _pan_right(t):
    return 0.5 - 0.18 * t, 0.5, 1.12

def _pan_up(t):
    return 0.5, 0.5 + 0.18 * t, 1.12

def _pan_down(t):
    return 0.5, 0.5 - 0.18 * t, 1.12

def _orbit(t):
    # قوس نصف دائري: دوران بصري عبر انزياح أفقي + دوران طفيف للإطار
    return 0.5 + 0.14 * math.sin(2 * math.pi * t), 0.5, 1.15 + 0.08 * math.sin(math.pi * t)

def _dolly(t):
    return 0.5, 0.48 + 0.02 * t, 1.0 + 0.35 * t   # اقتراب بانسيابية مع هبوط بسيط

def _handheld(t):
    # ارتجاج كتف بشري: ضجيج جيبي بمzujتين غير متمايزتين
    jx = 0.006 * math.sin(2 * math.pi * 3.1 * t) + 0.004 * math.sin(2 * math.pi * 7.3 * t)
    jy = 0.006 * math.cos(2 * math.pi * 2.7 * t) + 0.003 * math.sin(2 * math.pi * 5.9 * t)
    return 0.5 + jx, 0.5 + jy, 1.10

def _ken_burns(t):
    return 0.46 + 0.06 * t, 0.5, 1.05 + 0.25 * t   # الانجراف القطري الكلاسيكي

def _vertigo(t):
    # dolly zoom (هيتشكوك): اقتراب مع تباعد مجال مُحاكى بالتدوير الطفيف
    return 0.5, 0.5, 1.0 + 0.4 * t

PRESETS: dict[str, tuple] = {
    "zoom_in": ("اقتراب بطيء", _zoom_in),
    "zoom_out": ("إبعاد بطيء", _zoom_out),
    "crash_zoom": ("اقتراب صاعق", _crash_zoom),
    "pan_left": ("تمرير يسار", _pan_left),
    "pan_right": ("تمرير يمين", _pan_right),
    "pan_up": ("تمرير أعلى", _pan_up),
    "pan_down": ("تمرير أسفل", _pan_down),
    "orbit": ("دوران مقوس", _orbit),
    "dolly_in": ("دوللي سينمائي", _dolly),
    "handheld": ("كاميرا محمولة", _handheld),
    "ken_burns": ("كين بيرنز", _ken_burns),
    "vertigo": ("دوللي-زوم (فيرتيغو)", _vertigo),
}


def motion_dir() -> Path:
    d = Path(os.environ.get("OSV_MEDIA_DIR")
             or (Path(__file__).resolve().parent / "media"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_still(src: str, width: int, height: int) -> np.ndarray:
    """الصورة المصدر (مسار) → إطار أساس بحجم الهدف مع هامش تكبير للحركة."""
    img = Image.open(src).convert("RGB").resize((width, height), Image.LANCZOS)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _frame_at(base: np.ndarray, cx: float, cy: float, zoom: float,
              out_w: int, out_h: int, rot: float = 0.0) -> np.ndarray:
    """قص الإطار عند (cx,cy) بمعامل zoom ثم ملاءمة الحجم النهائي."""
    h, w = base.shape[:2]
    crop_w, crop_h = int(w / zoom), int(h / zoom)
    cxp, cyp = int(cx * w), int(cy * h)
    x0 = min(max(cxp - crop_w // 2, 0), w - crop_w)
    y0 = min(max(cyp - crop_h // 2, 0), h - crop_h)
    crop = base[y0:y0 + crop_h, x0:x0 + crop_w]
    if abs(rot) > 0.01:
        m = cv2.getRotationMatrix2D((crop_w / 2, crop_h / 2), rot, 1.0)
        crop = cv2.warpAffine(crop, m, (crop_w, crop_h),
                              borderMode=cv2.BORDER_REFLECT)
    return cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_CUBIC)


def _resolve_src(src: str) -> str:
    """الأسماء المجرّدة من media_list تُحلّ ضد مجلد الوسائط — الوكيل يمرر ما رآه."""
    p = Path(src)
    if p.is_file() or not src or Path(src).is_absolute():
        return src
    cand = motion_dir() / p.name
    return str(cand) if cand.is_file() else src


def motion_clip(src: str, preset: str = "zoom_in", duration_s: float = 5.0,
                fps: int = FPS, width: int = 704, height: int = 512
                ) -> tuple[bool, str]:
    """مقطع MP4: حركة كاميرا سينمائية مبرمَجة فوق مشهد مولّد — سريع بلا حصة."""
    if preset not in PRESETS:
        return False, (f"مسبق غير معروف: {preset}. المتاح: "
                       f"{', '.join(sorted(PRESETS))}")
    src = _resolve_src(src)
    if not src or not Path(src).is_file():
        return False, (f"الصورة المصدر غير موجودة: {src} "
                       f"(مرر مساراً كاملاً أو اسأل media_list عن المسارات)")
    duration_s = min(max(float(duration_s), DUR_MIN), DUR_MAX)
    width = min(max(int(width), 256), 1920)
    height = min(max(int(height), 256), 1920)
    t0 = time.time()
    base = _load_still(src, width, height)
    n = int(duration_s * fps)
    label, curve = PRESETS[preset]
    staged = _stage_path("osv_mot_")
    writer = cv2.VideoWriter(str(staged), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (width, height))
    if not writer.isOpened():
        return False, "تعذر فتح مرمّز MP4 (mp4v)"
    for i in range(n):
        cx, cy, zoom = curve(i / max(n - 1, 1))
        writer.write(_frame_at(base, cx, cy, zoom, width, height))
    writer.release()
    out = _publish(staged)
    check = cv2.VideoCapture(str(out))
    ok = check.isOpened() and int(check.get(cv2.CAP_PROP_FRAME_COUNT)) >= n - 1
    check.release()
    if not ok:
        return False, f"الملف الناتج غير سليم: {out}"
    return True, (f"حركة كاميرا سينمائية فوق مشهد مولّد (ليست حركة توليدية): "
                  f"{out} ({preset}/{label}، {duration_s}s @{fps}fps، "
                  f"{out.stat().st_size // 1024}KB، {time.time() - t0:.1f}s)")


def genjutsu_variants(src: str, presets: list[str] | None = None,
                      duration_s: float = 4.0) -> tuple[bool, str]:
    """روح Genjutsu: صورة واحدة تدخل — رؤيات كثيرة تخرج. N مقاطع من نفس الصورة."""
    presets = presets or ["zoom_in", "orbit", "ken_burns", "crash_zoom"]
    clips, t0 = [], time.time()
    for p in presets[:6]:
        ok, obs = motion_clip(src, p, duration_s)
        if not ok:
            return False, f"فشل المسبق {p}: {obs}"
        clips.append(str(obs.split(": ", 1)[1].split(" (")[0]))
    return True, (f"{len(clips)} رؤيات من صورة واحدة: " + " ، ".join(
        f"{Path(c).name}" for c in clips) +
        f" — {time.time() - t0:.1f}s إجمالاً")


def compose_cinema(scenes: list[dict], transition: str = "crossfade",
                   fps: int = FPS) -> tuple[bool, str]:
    """ستوري بورد سينمائي: [{image, preset, duration}] → فيلم واحد بانتقالات."""
    if not scenes or not isinstance(scenes, list):
        return False, "لا مشاهد — مرر [{image, preset, duration}]"
    segs, t0 = [], time.time()
    for i, sc in enumerate(scenes[:8]):
        img = str(sc.get("image", ""))
        preset = str(sc.get("preset", "ken_burns"))
        dur = float(sc.get("duration", 4.0))
        ok, obs = motion_clip(img, preset, dur, fps)
        if not ok:
            return False, f"المشهد {i + 1} فشل: {obs}"
        segs.append(obs.split(": ", 1)[1].split(" (")[0])
    # دمج بالانتقالات — نقرأ المقاطع ونعيد ترميزها في فيلم واحد
    caps = [cv2.VideoCapture(p) for p in segs]
    if not all(c.isOpened() for c in caps):
        for c in caps:
            c.release()
        return False, "تعذر فتح أحد المقاطع للدمج"
    w = int(caps[0].get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(caps[0].get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = _stage_path("osv_cine_")
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (w, h))
    fade = int(fps * 0.5) if transition == "crossfade" else 0
    prev_last: np.ndarray | None = None
    for si, cap in enumerate(caps):
        frames = []
        while True:
            okf, fr = cap.read()
            if not okf:
                break
            frames.append(fr)
        cap.release()
        if not frames:
            continue
        for i, fr in enumerate(frames):
            if (transition == "crossfade" and fade and si > 0
                    and i < fade and prev_last is not None):
                a = float(i) / fade          # 0→1: من المشهد السابق إلى الحالي
                writer.write(cv2.addWeighted(prev_last, 1.0 - a, fr, a, 0))
            else:
                writer.write(fr)
        prev_last = frames[-1]
    writer.release()
    out = _publish(out)
    if out.stat().st_size < 10_000:
        return False, "الملف المركّب ضئيل — يُرفض"
    return True, (f"فيلم سينمائي مركّب: {out} ({len(segs)} مشاهد، "
                  f"{transition}، {out.stat().st_size // 1024}KB، "
                  f"{time.time() - t0:.1f}s)")
