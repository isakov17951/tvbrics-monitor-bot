# -*- coding: utf-8 -*-
"""Формат сообщений и доставка; импорт не требует токена Telegram."""
import asyncio

from aiogram.exceptions import TelegramRetryAfter

import db


def format_news(item):
    return (f"Партнер: {item['partner']}\nДата: {item['date']}\n"
            f"Заголовок: {item['title']}\nСсылка: {item['url']}\nЯзык: {item['lang']}")


def format_summary(report):
    period = f"{report.date_from:%d.%m.%Y}–{report.date_to:%d.%m.%Y}"
    if report.errors:
        return (f"⚠️ Поиск выполнен не полностью ({period}).\n"
                f"Проблемы в версиях: {', '.join(report.errors)}.\n"
                f"Найдено для отправки: {len(report.items)}. "
                "Необработанные статьи будут проверены при следующем запуске.")
    if not report.items:
        return f"Поиск завершён ({period}). Новых новостей иранских партнёров нет."
    return f"Поиск завершён ({period}). Найдено новых новостей: {len(report.items)}."


async def send_with_retry(send, chat_id, text):
    for attempt in range(3):
        try:
            await send(chat_id, text)
            return
        except TelegramRetryAfter as exc:
            if attempt == 2:
                raise
            await asyncio.sleep(exc.retry_after + 1)


async def deliver_report(send, chat_ids, report, log):
    """После сбоя повторяем недоставленное, сохраняя отметки по получателям."""
    failures = []
    for chat_id in chat_ids:
        try:
            await send_with_retry(send, chat_id, format_summary(report))
            for item in report.items:
                if db.was_delivered(item["url"], chat_id):
                    continue
                await send_with_retry(send, chat_id, format_news(item))
                db.mark_delivered(item["url"], chat_id)
                await asyncio.sleep(0.5)
        except Exception as exc:
            failures.append(str(chat_id))
            await log(f"Не удалось доставить подборку получателю {chat_id}: {type(exc).__name__}")
    db.finalize_deliveries(report.items, chat_ids)
    return failures
