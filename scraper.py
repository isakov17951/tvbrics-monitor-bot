# -*- coding: utf-8 -*-
"""
Обход tvbrics.com под видом обычного пользователя (Playwright + Chromium).

Логика на каждый язык:
  1. Открыть ленту новостей.
  2. Кликнуть "Страны-участницы" -> "Иран" (data-id=784184). Адрес НЕ меняется,
     лента обновляется на лету, поэтому ждём обновления контейнера.
  3. Читать карточки, жать "ЕЩЕ", пока даты не уйдут за 10 дней.
  4. Каждую ещё не виденную статью открыть и проверить: есть ли в ней
     ссылка на иранского партнёра (словарь PARTNERS в config.py).
"""

import asyncio
import random
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

import db
from config import (
    DAYS_BACK, HEADLESS, LANGS, MAX_MORE_CLICKS, PARTNERS,
    PAUSE_MAX, PAUSE_MIN, SEL_CARD, SEL_CARD_TITLE, SEL_CARD_TOP,
    SEL_COUNTRY_MENU, SEL_IRAN_ITEM, SEL_MORE_BTN,
)

DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2,4})")


async def human_pause():
    """Пауза, как у живого человека: и естественно, и вежливо к сайту."""
    await asyncio.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))


def parse_card_date(text: str):
    """Достаёт дату вида 08.06.26 (или 08.06.2026) из строки карточки."""
    m = DATE_RE.search(text or "")
    if not m:
        return None
    d, mo, y = m.groups()
    y = int(y)
    if y < 100:
        y += 2000
    elif y > 2099:  # склейка даты со временем: "07.06.2610" = 07.06.26 + 10:30
        y = 2000 + int(str(y)[:2])
    try:
        return datetime(y, int(mo), int(d))
    except ValueError:
        return None


async def extract_cards(page, base_url):
    """Собирает с текущей страницы все карточки: (заголовок, ссылка, дата)."""
    raw = await page.eval_on_selector_all(
        SEL_CARD,
        """(cards, args) => cards.map(c => {
            const name = c.querySelector(args.title);
            const a = name ? name.querySelector('a') : c.querySelector('a');
            const top = c.querySelector(args.top);
            let dateText = '';
            if (top) {
                for (const n of top.childNodes) {
                    if (n.nodeType === 3 && n.textContent.trim()) {
                        dateText = n.textContent.trim();
                        break;
                    }
                }
                if (!dateText) dateText = top.textContent.trim();
            }
            return {
                title: name ? name.textContent.trim() : '',
                href: a ? a.getAttribute('href') : '',
                top: dateText
            };
        })""",
        {"title": SEL_CARD_TITLE, "top": SEL_CARD_TOP},
    )
    cards, seen_urls = [], set()
    for item in raw:
        if not item["href"] or not item["title"]:
            continue
        url = urljoin(base_url, item["href"])
        if url in seen_urls:
            continue  # одна новость встречается и в слайдере, и в ленте
        seen_urls.add(url)
        cards.append({"title": item["title"], "url": url,
                      "date": parse_card_date(item["top"])})
    return cards


async def find_partners_in_article(page, url):
    """Открывает статью и возвращает имена партнёров по доменам ссылок."""
    await page.goto(url, wait_until="domcontentloaded")
    await human_pause()
    hrefs = await page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.href)"
    )
    found = []
    for href in hrefs:
        domain = urlparse(href).netloc.lower().removeprefix("www.")
        for partner_domain, partner_name in PARTNERS.items():
            if domain == partner_domain or domain.endswith("." + partner_domain):
                if partner_name not in found:
                    found.append(partner_name)
    return found


async def collect_language(context, lang, url, cutoff, log):
    """Полный проход по одной языковой версии. Возвращает список находок."""
    page = await context.new_page()
    results = []
    try:
        await log(f"[{lang}] Открываю {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await human_pause()

        # --- фильтр "Страны-участницы" -> "Иран" -----------------------
        menu = page.locator(SEL_COUNTRY_MENU).first
        if await menu.count() == 0:
            await log(f"[{lang}] Не нашёл кнопку 'Страны-участницы' — пропускаю язык. "
                      f"Нужно проверить селекторы этой версии через DevTools.")
            return results
        await menu.click()
        await human_pause()

        iran = page.locator(SEL_IRAN_ITEM).first
        if await iran.count() == 0:
            await log(f"[{lang}] Не нашёл пункт 'Иран' (data-id) — пропускаю язык.")
            return results
        prev_html_len = len(await page.content())
        await iran.click()
        # адрес не меняется: просто даём AJAX время перерисовать ленту
        await page.wait_for_timeout(2500)
        await human_pause()

        # --- листаем ленту кнопкой "ЕЩЕ" до глубины DAYS_BACK ----------
        prev_count = None
        for click_n in range(MAX_MORE_CLICKS + 1):
            cards = await extract_cards(page, url)
            dated = [c for c in cards if c["date"]]
            oldest = min((c["date"] for c in dated), default=None)
            await log(f"[{lang}] Вижу карточек: {len(cards)}; "
                      f"самая старая: {oldest:%d.%m.%Y}" if oldest else
                      f"[{lang}] Вижу карточек: {len(cards)}; дат не распознал")

            if oldest and oldest < cutoff:
                break  # дошли до новостей старше 10 дней

            if prev_count is not None and len(cards) <= prev_count:
                await log(f"[{lang}] После 'ЕЩЕ' новых карточек не появилось — "
                          "останавливаюсь. Похоже, бот не видит подгружаемую "
                          "часть ленты, нужна сверка селекторов.")
                break
            prev_count = len(cards)

            more = page.locator(SEL_MORE_BTN).first
            if await more.count() == 0 or not await more.is_visible():
                break  # кнопки "ЕЩЕ" больше нет — лента кончилась
            await more.scroll_into_view_if_needed()
            await more.click()
            await page.wait_for_timeout(2000)
            await human_pause()

        # --- отбор: свежие, не виденные, с партнёрской ссылкой ---------
        fresh = [c for c in cards if c["date"] and c["date"] >= cutoff]
        new_cards = [c for c in fresh if not db.is_seen(c["url"])]
        await log(f"[{lang}] За {DAYS_BACK} дн.: {len(fresh)} новостей, "
                  f"из них новых: {len(new_cards)}. Проверяю партнёров...")

        article_page = await context.new_page()
        for c in new_cards:
            partners = await find_partners_in_article(article_page, c["url"])
            if partners:
                partner_str = ", ".join(partners)
                results.append({
                    "partner": partner_str,
                    "date": c["date"].strftime("%d.%m.%Y"),
                    "title": c["title"],
                    "url": c["url"],
                    "lang": lang,
                })
                db.mark_seen(c["url"], lang, c["title"], partner_str,
                             c["date"].strftime("%d.%m.%Y"))
            else:
                # статья без партнёрской ссылки: тоже запоминаем,
                # чтобы в следующий раз не открывать её заново
                db.mark_seen(c["url"], lang, c["title"], "", 
                             c["date"].strftime("%d.%m.%Y"))
        await article_page.close()
    finally:
        await page.close()
    return results


async def run_search(log):
    """Главная точка входа. log — async-функция для сообщений о ходе работы."""
    if len(PARTNERS) <= 1:
        await log("⚠️ В config.py заполнен только пример партнёра. "
                  "Не забудь добавить остальные домены в словарь PARTNERS.")
    cutoff = datetime.now() - timedelta(days=DAYS_BACK)
    all_results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            locale="ru-RU",
            viewport={"width": 1366, "height": 850},
        )
        for lang, url in LANGS:
            try:
                found = await collect_language(context, lang, url, cutoff, log)
                all_results.extend(found)
            except Exception as e:  # один сломавшийся язык не валит весь поиск
                await log(f"[{lang}] Ошибка: {e}")
        await browser.close()
    return all_results
