# -*- coding: utf-8 -*-
"""
Telegram-бот TV BRICS / Иран.
Кнопка "Запустить поиск" -> обход всех языковых версий -> вывод в формате:

Партнер: ...
Дата: ...
Заголовок: ...
Ссылка: ...
Язык: ...
"""

import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from dotenv import load_dotenv

from scraper import run_search

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PROXY = os.getenv("PROXY")  # например http://127.0.0.1:10809; пусто = без прокси
if not TOKEN:
    raise SystemExit("Нет токена! Создай файл .env со строкой BOT_TOKEN=твой_токен")

BTN_SEARCH = "🔍 Запустить поиск"
keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_SEARCH)]],
    resize_keyboard=True,
)

dp = Dispatcher()
search_running = False  # защита от двойного нажатия


def format_news(item: dict) -> str:
    return (
        f"Партнер: {item['partner']}\n"
        f"Дата: {item['date']}\n"
        f"Заголовок: {item['title']}\n"
        f"Ссылка: {item['url']}\n"
        f"Язык: {item['lang']}"
    )


@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я ищу на tvbrics.com новости иранских партнёров "
        "за последние 10 дней (все языковые версии). "
        "Уже найденное раньше не повторяю.\n\nЖми кнопку.",
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
        await message.answer("Начинаю обход сайта, это займёт несколько минут...")

        async def log(text: str):
            await message.answer(text)

        results = await run_search(log)
        # от старой новости к новой: читается в чате по хронологии
        results.sort(key=lambda r: tuple(reversed(r["date"].split("."))))

        if not results:
            await message.answer(
                "Новых новостей иранских партнёров за последние 10 дней не нашёл."
            )
        else:
            await message.answer(f"Готово! Новых новостей: {len(results)}")
            for item in results:
                await message.answer(format_news(item))
                await asyncio.sleep(0.5)  # не упираться в лимиты Telegram
    except Exception as e:
        await message.answer(f"Что-то пошло не так: {e}")
    finally:
        search_running = False


async def main():
    session = AiohttpSession(proxy=PROXY) if PROXY else None
    bot = Bot(token=TOKEN, session=session)
    print(f"Бот запущен{' через прокси ' + PROXY if PROXY else ''}. "
          "Нажми Ctrl+C для остановки.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
