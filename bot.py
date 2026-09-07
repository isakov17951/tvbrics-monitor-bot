# -*- coding: utf-8 -*-
"""Telegram-бот TV BRICS / Иран с кнопкой запуска поиска."""
import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from config import DAYS_BACK  # noqa: E402
from delivery import deliver_report, format_news  # noqa: E402
from scraper import run_search  # noqa: E402

BTN_SEARCH = "🔍 Запустить поиск"
keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_SEARCH)]], resize_keyboard=True,
)
dp = Dispatcher()
search_running = False


@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(
        f"Привет! Я ищу на tvbrics.com новости иранских партнёров "
        f"за последние {DAYS_BACK} дней на шести языках. "
        "Уже отправленные новости не повторяю. Нажми кнопку.",
        reply_markup=keyboard,
    )


@dp.message(F.text == BTN_SEARCH)
async def cmd_search(message: Message):
    global search_running
    if search_running:
        await message.answer("Поиск уже идёт, подожди, пожалуйста ⏳")
        return
    search_running = True
    try:
        await message.answer("Начинаю поиск, это займёт несколько минут...")

        async def log(text):
            print(text, flush=True)

        report = await run_search(log)
        failures = await deliver_report(message.bot.send_message, [message.chat.id], report, log)
        if failures:
            await message.answer("Часть подборки не удалось отправить. Повтори поиск: "
                                 "подтверждённые сообщения повторяться не будут.")
    except Exception as exc:
        print(f"Ошибка поиска: {type(exc).__name__}: {exc}", flush=True)
        await message.answer("Поиск завершился с ошибкой. Подробности есть в журнале запуска.")
    finally:
        search_running = False


async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Нет токена: создай .env со строкой BOT_TOKEN=твой_токен")
    proxy = os.getenv("PROXY")
    session = AiohttpSession(proxy=proxy) if proxy else None
    bot = Bot(token=token, session=session)
    print("Бот запущен. Нажми Ctrl+C для остановки.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
