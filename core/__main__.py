"""
OSS Work — Main Package Entry Point.

أستخدام:
    python -m core                  — تشغيل الوكيل بالوضع المضبوط في .env
    python -m core --mode desktop   — تشغيل وضع桌面
    python -m core --mode telegram  — تشغيل وضع التلجرام
    python -m core --mode hybrid    — تشغيل كلا الوضعين
    python -m core --task "مهمة"    — معالجة مهمة فورية والخروج

أو من CLI:
    oss-work run                     — نفس الشيء
    oss-work telegram                — تشغيل وضع التلجرام فقط
    oss-work desktop                 — تشغيل وضع桌面 فقط
    oss-work chat "مهمة"            — معالجة مهمة عبر CLI
"""

from __future__ import annotations

import argparse
import sys

from core.config import load_config
from core.runtime import main as runtime_main


def main() -> None:
    """ال entrypoint الرئيسي للمشروع."""
    parser = argparse.ArgumentParser(
        prog="oss-work",
        description="OSS Work - Universal AI Agent",
    )
    parser.add_argument(
        "--mode",
        choices=["telegram", "desktop", "hybrid"],
        default=None,
        help="الوضع المطلوب (telegram, desktop, hybrid)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="مهمة معالجة فورية (uno فقط)",
    )
    parser.add_argument(
        "--user",
        type=str,
        default="local",
        help="معرف المستخدم",
    )

    args = parser.parse_args()

    # إذا كان هناك مهمة فورية، عالجها وخرج
    if args.task:
        from core.processor import TaskProcessor
        config = load_config()
        processor = TaskProcessor(config)
        import asyncio
        result = asyncio.run(processor.process(args.task, args.user))
        print(result.get("data", {}).get("solution", "No solution"))
        return

    # تعيين الوضع من الـ CLI إذا لم يكن مضبوطًا في .env
    config = load_config()
    if args.mode:
        config.mode = args.mode

    # تشغيل الوضع المحدد
    runtime_main()


if __name__ == "__main__":
    main()
