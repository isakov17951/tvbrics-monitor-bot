# -*- coding: utf-8 -*-
"""База уже найденных новостей: бот не показывает одно и то же дважды."""

import sqlite3
from datetime import datetime

from config import DB_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS seen (
               url      TEXT PRIMARY KEY,
               lang     TEXT,
               title    TEXT,
               partner  TEXT,
               news_date TEXT,
               found_at TEXT
           )"""
    )
    return conn


def is_seen(url: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM seen WHERE url = ?", (url,)).fetchone()
        return row is not None


def mark_seen(url: str, lang: str, title: str, partner: str, news_date: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen VALUES (?, ?, ?, ?, ?, ?)",
            (url, lang, title, partner, news_date, datetime.now().isoformat(timespec="seconds")),
        )
