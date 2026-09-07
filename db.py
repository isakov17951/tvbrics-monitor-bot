# -*- coding: utf-8 -*-
"""Совместимая база архива и подтверждений доставки. Старые записи сохраняются."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config import DB_PATH


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        with conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS seen (
                url TEXT PRIMARY KEY, lang TEXT, title TEXT, partner TEXT,
                news_date TEXT, found_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS delivered (
                url TEXT NOT NULL, chat_id TEXT NOT NULL,
                PRIMARY KEY (url, chat_id))""")
            yield conn
    finally:
        conn.close()


def _read(query, args, *, table):
    if not Path(DB_PATH).exists():
        return None
    conn = sqlite3.connect(Path(DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                              (table,)).fetchone()
        return conn.execute(query, args).fetchone() if exists else None
    finally:
        conn.close()


def is_seen(url):
    return _read("SELECT 1 FROM seen WHERE url=?", (url,), table="seen") is not None


def mark_seen(url, lang, title, partner, news_date):
    with _conn() as conn:
        conn.execute("INSERT OR IGNORE INTO seen VALUES (?, ?, ?, ?, ?, ?)",
                     (url, lang, title, partner, news_date,
                      datetime.now().isoformat(timespec="seconds")))


def was_delivered(url, chat_id):
    return _read("SELECT 1 FROM delivered WHERE url=? AND chat_id=?",
                 (url, str(chat_id)), table="delivered") is not None


def mark_delivered(url, chat_id):
    with _conn() as conn:
        conn.execute("INSERT OR IGNORE INTO delivered VALUES (?, ?)", (url, str(chat_id)))


def finalize_deliveries(items, chat_ids):
    for item in items:
        if chat_ids and all(was_delivered(item["url"], chat) for chat in chat_ids):
            mark_seen(item["url"], item["lang"], item["title"], item["partner"], item["date"])
