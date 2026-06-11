# -*- coding: utf-8 -*-
"""
Одноразовый прогон поиска — для GitHub Actions (по расписанию или Run workflow).
Делает то же, что кнопка в Telegram, но без ожидания нажатий:
ищет -> присылает результаты в твой чат -> завершается.

Нужны переменные окружения (на GitHub задаются в Secrets):
  BOT_TOKEN — токен бота
  CHAT_ID   — id твоего чата с ботом (узнать: напиши @userinfobot в Telegram)
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
if not TOKEN or not CHAT_ID:
    raise SystemExit("Нужны переменные BOT_TOKEN и CHAT_ID")

# На сервере GitHub нет экрана — принудительно включаем невидимый режим,
# что бы ни стояло в config.py. Делаем это ДО импорта scraper.
import config  # noqa: E402
config.HEADLESS = True

from aiogram import Bot  # noqa: E402
from scraper import run_search  # noqa: E402
from bot import format_news  # noqa: E402


async def main():
    bot = Bot(token=TOKEN)
    try:
        async def log(text: str):
            print(text, flush=True)  # ход работы виден в логе GitHub Actions

        results = await run_search(log)
        # от старой новости к новой: читается в чате по хронологии
        results.sort(key=lambda r: tuple(reversed(r["date"].split("."))))

        if not results:
            await bot.send_message(
                CHAT_ID,
                "Плановый поиск: новых новостей иранских партнёров "
                "за последние 10 дней нет.",
            )
        else:
            await bot.send_message(CHAT_ID, f"Найдено новых новостей: {len(results)}")
            for item in results:
                await bot.send_message(CHAT_ID, format_news(item))
                await asyncio.sleep(0.5)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
