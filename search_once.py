# -*- coding: utf-8 -*-
"""Разовый поиск для Actions и локальной проверки без Telegram."""
import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from config import DAYS_BACK, LANGS  # noqa: E402
from delivery import deliver_report, format_news, format_summary  # noqa: E402
from scraper import run_search  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Не отправлять Telegram-сообщения и не менять базу")
    parser.add_argument("--include-seen", action="store_true",
                        help="Проверить и ранее найденное (только вместе с --dry-run)")
    parser.add_argument("--days", type=int, default=DAYS_BACK)
    parser.add_argument("--langs", nargs="+", type=str.upper, choices=[lang for lang, _ in LANGS])
    parser.add_argument("--json", type=Path, help="Сохранить результат и ошибки в JSON")
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days должен быть не меньше 1")
    if args.include_seen and not args.dry_run:
        parser.error("--include-seen разрешён только с --dry-run")
    return args


async def main(args=None):
    args = args or parse_args()
    token = os.getenv("BOT_TOKEN")
    chat_ids = list(dict.fromkeys(c.strip() for c in os.getenv("CHAT_ID", "").split(",") if c.strip()))
    if not args.dry_run and (not token or not chat_ids):
        raise SystemExit("Для отправки нужны BOT_TOKEN и CHAT_ID. Для проверки используй --dry-run.")

    async def log(text):
        print(text, flush=True)

    report = await run_search(log, dry_run=args.dry_run, include_seen=args.include_seen,
                              days_back=args.days, languages=args.langs)
    await log(format_summary(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2,
                                        default=str), encoding="utf-8")
    if args.dry_run:
        for item in report.items:
            await log(format_news(item))
        failures = []
    else:
        from aiogram import Bot
        bot = Bot(token=token)
        try:
            failures = await deliver_report(bot.send_message, chat_ids, report, log)
        finally:
            await bot.session.close()
    for lang, errors in report.errors.items():
        for error in errors:
            await log(f"[{lang}] {error}")
    return 1 if report.errors or failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
