# -*- coding: utf-8 -*-
"""Новости Ирана через браузер и действующие элементы интерфейса TV BRICS.

Фильтр, карточки и параметры пагинации читаются из актуального HTML.
Ответы AJAX проверяются до разбора, проверка доступа останавливает поиск.
"""

import asyncio
import json
import logging
import os
import random
import re
import unicodedata
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import db
from config import (
    DAYS_BACK, HEADLESS, IRAN_DATA_ID, IRAN_NAMES, LANGS, MAX_MORE_CLICKS, PARTNERS,
    PAUSE_MAX, PAUSE_MIN, REQUEST_TIMEOUT, SITE_TIMEZONE,
)


class ScrapeError(RuntimeError):
    """Сайт не удалось прочитать; это не означает отсутствие новостей."""


class AccessBlocked(ScrapeError):
    """Доступ ограничен: не повторяем запрос и не меняем способ доступа."""


@dataclass
class Card:
    title: str
    url: str
    date: datetime | None
    raw_date: str = ""


@dataclass
class Pagination:
    url: str
    filters: dict
    page: int
    showby: int

    def form(self):
        result = {f"filter[{key}]": str(value) for key, value in self.filters.items()}
        result.update(page=str(self.page), showby=str(self.showby))
        return result


@dataclass
class SearchReport:
    date_from: date
    date_to: date
    items: list[dict] = field(default_factory=list)
    errors: dict[str, list[str]] = field(default_factory=dict)
    completed_languages: list[str] = field(default_factory=list)
    checked_articles: int = 0

    def add_error(self, lang, message):
        self.errors.setdefault(lang, []).append(str(message))


def parse_card_date(text: str):
    """ДД.ММ.ГГ, ДД.ММ.ГГГГ, ISO и китайская дата; без догадок о годе."""
    text = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c
                   for c in (text or ""))
    patterns = (
        (r"(?<!\d)(\d{2,4})年\s*(\d{1,2})月\s*(\d{1,2})日", True),
        (r"(?<!\d)(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?!\d)", True),
        (r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)", False),
    )
    for pattern, year_first in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        a, b, c = map(int, match.groups())
        year, month, day = (a, b, c) if year_first else (c, b, a)
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day)
        except ValueError:
            return None
    return None


def search_window(days_back=DAYS_BACK, now=None):
    if days_back < 1:
        raise ValueError("Число дней должно быть не меньше 1")
    zone = ZoneInfo(SITE_TIMEZONE)
    now = now or datetime.now(zone)
    if now.tzinfo is not None:
        now = now.astimezone(zone)
    today = now.date()
    return today - timedelta(days=days_back - 1), today


def site_url(base, href):
    value = urlsplit(urljoin(base, href))
    if (value.scheme not in {"http", "https"}
            or value.hostname not in {"tvbrics.com", "www.tvbrics.com"}
            or value.username or value.password):
        raise ScrapeError("В разметке найден неожиданный адрес вместо TV BRICS")
    return urlunsplit((value.scheme, value.netloc, value.path, value.query, ""))


def parse_country_filter(content, base_url):
    soup = BeautifulSoup(content, "html.parser")
    for block in soup.select(".filter-items[data-url]"):
        for item in block.select(".js_filter_country[data-id]"):
            name = item.get_text(" ", strip=True).casefold()
            if name in IRAN_NAMES or item.get("data-id") == IRAN_DATA_ID:
                return (site_url(base_url, block["data-url"]),
                        {"id": item["data-id"], "section": item.get("data-section", "")})
    raise ScrapeError("Не найден фильтр Ирана в новой разметке сайта")


def parse_feed(content, base_url, *, fragment=False):
    """Читаем ответ фильтра/пагинации либо его блок в полной странице."""
    soup = BeautifulSoup(content, "html.parser")
    root = soup.select_one("#filter_news_list")
    if root is None:
        if not fragment:
            raise ScrapeError("Не найден контейнер отфильтрованных новостей")
        root = soup
    cards, seen = [], set()
    for node in root.select("a.news-card[href]"):
        title_node = node.select_one(".news-card__title")
        date_node = node.select_one(".head-news-card__date")
        if title_node is None:
            raise ScrapeError("Карточка новости не содержит заголовок")
        url = site_url(base_url, node["href"])
        parts = urlsplit(url)
        if not re.fullmatch(r"/(?:en/|cn/|pt/|es/|ar/)?news/[^/]+/?", parts.path):
            raise ScrapeError("В ленте обнаружена карточка с неожиданным адресом")
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        if url in seen:
            continue
        seen.add(url)
        raw = date_node.get_text(" ", strip=True) if date_node else ""
        cards.append(Card(title_node.get_text(" ", strip=True), url,
                          parse_card_date(raw), raw))
    more = root.select_one(".js_news_list_show_more")
    pagination = None
    if more:
        try:
            filters = json.loads(more["data-filter"])
            if not isinstance(filters, dict):
                raise ValueError("filter должен быть объектом")
            pagination = Pagination(site_url(base_url, more["data-url"]), filters,
                                    int(more["data-page"]), int(more["data-showby"]))
            if pagination.page < 1 or pagination.showby < 1:
                raise ValueError("Неверный номер страницы или размер страницы")
        except (KeyError, ValueError, TypeError) as exc:
            raise ScrapeError("Не удалось прочитать параметры следующей страницы") from exc
    return cards, pagination


def partner_names(hrefs):
    found = []
    for href in hrefs:
        try:
            parts = urlsplit(href)
            if parts.scheme not in {"http", "https"}:
                continue
            host = (parts.hostname or "").lower().rstrip(".")
        except ValueError:
            continue
        for domain, name in PARTNERS.items():
            if host == domain or host.endswith("." + domain):
                if name not in found:
                    found.append(name)
    return found


def parse_article(content, url):
    soup = BeautifulSoup(content, "html.parser")
    body = soup.select_one(".news-detail-content, [itemprop='articleBody']")
    title = soup.select_one("h1")
    if body is None or title is None or not body.get_text(strip=True):
        raise ScrapeError("Не найден текст или заголовок статьи: " + url)
    names = partner_names(urljoin(url, a["href"]) for a in body.select("a[href]"))
    return title.get_text(" ", strip=True), names


def check_response(status, content, url):
    if (status in {401, 403, 429}
            or "/.well-known/ddos-guard/js-challenge/" in content
            or "Checking your browser before accessing" in content):
        raise AccessBlocked(f"Сайт ограничил доступ или запросил проверку браузера "
                            f"(HTTP {status}): {url}. Поиск остановлен.")
    if status != 200:
        raise ScrapeError(f"HTTP {status}: {url}")


class BrowserSource:
    """Открывает ленту и статьи в Chromium, ожидает ответы после кликов."""

    def __init__(self, context):
        self.context = context
        self.feed_page = None
        self.article_page = None
        self.stage = "подготовка браузера"

    async def _navigate(self, page, url):
        for attempt in (1, 2):
            self.stage = f"открытие страницы, попытка {attempt}/2"
            try:
                return await page.goto(url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError:
                if attempt == 2:
                    raise
                # Не повторяем запрос, если уже появилась проверка доступа.
                try:
                    content = await page.content()
                except PlaywrightError:
                    content = ""
                check_response(200, content, url)
                logging.getLogger(__name__).warning(
                    "Тайм-аут открытия %s; повтор через 3 секунды", url)
                await asyncio.sleep(3)

    async def _response_text(self, response):
        if response is None:
            raise ScrapeError("Браузер не получил ответ сайта")
        site_url(response.url, response.url)
        self.stage = "чтение ответа сайта"
        content = await response.text()
        check_response(response.status, content, response.url)
        return content

    async def fetch(self, url, *, data=None):
        if data is None:
            is_feed = url in {address for _, address in LANGS}
            attr = "feed_page" if is_feed else "article_page"
            page = getattr(self, attr)
            if page is None:
                self.stage = "создание вкладки"
                page = await self.context.new_page()
                setattr(self, attr, page)
            response = await self._navigate(page, url)
            await self._response_text(response)
            self.stage = "чтение HTML страницы"
            content = await page.content()
            check_response(200, content, url)
            if is_feed:
                self.stage = "закрытие уведомления о cookie"
                consent = page.locator(".js-cookie_confirm").first
                if await consent.is_visible():
                    await consent.click()
                    await page.locator(".confirm_cookie").wait_for(state="hidden")
            return content

        page = self.feed_page
        if page is None:
            raise ScrapeError("Лента ещё не открыта")
        matches = lambda r: r.request.method == "POST" and r.url == url
        if "id" in data:
            self.stage = "открытие списка стран"
            if not str(data["id"]).isdigit():
                raise ScrapeError("Некорректный ID страны")
            selector = f'.js_filter_country[data-id="{data["id"]}"]'
            iran = page.locator(".filter-items " + selector).first
            if not await iran.is_visible():
                menu = page.locator("li.js-toggle-active-click").filter(
                    has=page.locator(selector)).first
                await menu.locator(":scope > span").click()
            self.stage = "выбор Ирана и ожидание ответа фильтра"
            async with page.expect_response(matches) as response_info:
                await iran.click()
            content = await self._response_text(await response_info.value)
            self.stage = "ожидание активного фильтра Ирана"
            await page.locator(".filter-items " + selector + ".active").wait_for(state="attached")
        else:
            self.stage = "проверка кнопки следующей страницы"
            more = page.locator("#filter_news_list .js_news_list_show_more").first
            if await more.get_attribute("data-page") != str(data["page"]):
                raise ScrapeError("Номер следующей страницы в браузере не совпал с ожидаемым")
            self.stage = "загрузка следующей страницы новостей"
            async with page.expect_response(matches) as response_info:
                await more.click()
            content = await self._response_text(await response_info.value)
            next_page = int(data["page"]) + 1
            self.stage = "ожидание обновления номера страницы"
            await page.locator(f'.js_news_list_show_more[data-page="{next_page}"]').wait_for(state="attached")
        return content


@asynccontextmanager
async def browser_source():
    async with async_playwright() as pw:
        # PROXY (например, http://user:pass@host:port) нужен, если сайт
        # блокирует IP-адрес сервера напрямую, как адреса GitHub Actions.
        proxy = os.getenv("PROXY")
        launch_kwargs = {"headless": HEADLESS}
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}
            logging.getLogger(__name__).info("Браузер сборщика использует прокси")
        browser = await pw.chromium.launch(**launch_kwargs)
        try:
            context = await browser.new_context(locale="ru-RU", viewport={"width": 1366, "height": 850})
            context.set_default_timeout(REQUEST_TIMEOUT * 1000)
            yield BrowserSource(context)
        finally:
            await browser.close()


async def fetch_html(source, url, *, data=None):
    try:
        return await source.fetch(url, data=data)
    except PlaywrightError as exc:
        stage = getattr(source, "stage", "чтение сайта")
        details = str(exc).strip()[:1500]
        raise ScrapeError(
            f"Не удалось прочитать {url}; этап: {stage}; "
            f"{type(exc).__name__}: {details}"
        ) from exc


async def collect_language(session, lang, url, report, log, *, dry_run=False,
                           include_seen=False):
    await log(f"[{lang}] Открываю ленту и выбираю Иран")
    endpoint, form = parse_country_filter(await fetch_html(session, url), url)
    content = await fetch_html(session, endpoint, data=form)
    cards, pagination = parse_feed(content, url, fragment=True)
    if not cards:
        raise ScrapeError("Фильтр вернул страницу без карточек; результат поиска не подтверждён")
    if pagination and str(pagination.filters.get("PROPERTY_COUNTRY_ITEMS")) != form["id"]:
        raise ScrapeError("Фильтр следующей страницы не соответствует Ирану")

    candidates, collected = {}, set()
    for page_index in range(MAX_MORE_CLICKS + 1):
        new_cards = [card for card in cards if card.url not in collected]
        if not new_cards:
            report.add_error(lang, "Следующая страница не добавила новостей; обход неполный")
            break
        for card in new_cards:
            collected.add(card.url)
            if card.date is None:
                report.add_error(lang, f"Не распознана дата {card.raw_date!r}: {card.url}")
            elif report.date_from <= card.date.date() <= report.date_to:
                candidates[card.url] = card
        # Одна старая закреплённая карточка не должна останавливать обход.
        if all(c.date is not None and c.date.date() < report.date_from for c in new_cards):
            break
        if pagination is None:
            break
        if page_index == MAX_MORE_CLICKS:
            report.add_error(lang, "Достигнут предел страниц; поиск может быть неполным")
            break
        await asyncio.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))
        try:
            next_content = await fetch_html(session, pagination.url, data=pagination.form())
            cards, _ = parse_feed(next_content, url, fragment=True)
        except AccessBlocked:
            raise
        except (ScrapeError, UnicodeError) as exc:
            report.add_error(lang, str(exc))
            break
        if not cards:
            report.add_error(lang, "Следующая страница не содержит карточек; конец ленты не подтверждён")
            break
        pagination.page += 1

    fresh = list(candidates.values())
    pending = [c for c in fresh if include_seen or not db.is_seen(c.url)]
    await log(f"[{lang}] За период: {len(fresh)}, ещё не обработано: {len(pending)}")
    for card in pending:
        try:
            await asyncio.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))
            title, partners = parse_article(await fetch_html(session, card.url), card.url)
            report.checked_articles += 1
            news_date = card.date.strftime("%d.%m.%Y")
            if partners:
                report.items.append({"partner": ", ".join(partners), "date": news_date,
                                     "title": title, "url": card.url, "lang": lang})
            elif not dry_run:
                db.mark_seen(card.url, lang, title, "", news_date)
        except AccessBlocked:
            raise
        except (ScrapeError, UnicodeError) as exc:
            report.add_error(lang, str(exc))
            await log(f"[{lang}] Ошибка статьи: {exc}")
    if lang not in report.errors:
        report.completed_languages.append(lang)


async def run_search(log, *, dry_run=False, include_seen=False, days_back=DAYS_BACK,
                     languages=None, now=None, source=None):
    start, end = search_window(days_back, now)
    report = SearchReport(start, end)
    requested = set(languages) if languages is not None else {lang for lang, _ in LANGS}
    unknown = requested - {lang for lang, _ in LANGS}
    if unknown or not requested:
        raise ValueError("Укажи языки из списка: " + ", ".join(lang for lang, _ in LANGS))
    await log(f"Период: {start:%d.%m.%Y}–{end:%d.%m.%Y} ({SITE_TIMEZONE})")
    async def collect_all(session):
        blocked = False
        for lang, url in LANGS:
            if lang not in requested:
                continue
            if blocked:
                report.add_error(lang, "Не проверено: сайт ограничил доступ, обход остановлен")
                continue
            try:
                await collect_language(session, lang, url, report, log,
                                       dry_run=dry_run, include_seen=include_seen)
            except AccessBlocked as exc:
                blocked = True
                report.add_error(lang, str(exc))
                await log(f"[{lang}] {exc}")
            except Exception as exc:
                report.add_error(lang, str(exc))
                await log(f"[{lang}] Ошибка сбора: {exc}")
    if source is not None:
        await collect_all(source)
    else:
        async with browser_source() as session:
            await collect_all(session)
    report.items.sort(key=lambda r: (datetime.strptime(r["date"], "%d.%m.%Y"), r["lang"], r["url"]))
    return report
