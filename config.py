# -*- coding: utf-8 -*-
"""Настройки TV BRICS / Иран. Партнёры и языки сохранены из исходного бота."""
import os
from pathlib import Path

PARTNERS = {
    "irna.ir": "IRNA",
    "mehrnews.com": "Mehr News",
    "tehrantimes.com": "Tehran Times",
    "nournews.ir": "Nour News",
    "parstoday.ir": "Pars Today",
    "tabnak.ir": "Tabnak",
    "iranpress.com": "Iran Press",
    "alalam.ir": "Al Alam",
    "iribnews.ir": "IRIB News",
    "presstv.ir": "Press TV",
    "iribmediatrade.ir": "IRIB Media Trade",
    "iranradio.ir": "Iran Radio",
}

LANGS = [
    ("RU", "https://tvbrics.com/news/"),
    ("EN", "https://tvbrics.com/en/news/"),
    ("CN", "https://tvbrics.com/cn/news/"),
    ("PT", "https://tvbrics.com/pt/news/"),
    ("ES", "https://tvbrics.com/es/news/"),
    ("AR", "https://tvbrics.com/ar/news/"),
]

IRAN_DATA_ID = "784184"
IRAN_NAMES = {"иран", "iran", "irã", "irán", "伊朗", "إيران", "ايران"}
DAYS_BACK = 10                # сегодня и 9 предыдущих календарных дней
SITE_TIMEZONE = "Europe/Moscow"
PAUSE_MIN = 2.0               # умеренная частота запросов к сайту
PAUSE_MAX = 3.5
REQUEST_TIMEOUT = 45          # секунд на открытие страницы или действие браузера
HEADLESS = True               # исходный режим Chromium, подходит для GitHub Actions
MAX_MORE_CLICKS = 40          # максимум дополнительных страниц на один язык
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).with_name("seen_news.db")))
