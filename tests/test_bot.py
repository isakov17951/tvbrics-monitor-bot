"""Регрессии редизайна, неполного поиска и потери сообщений при сбоях."""
import asyncio
import base64
import zlib
import json
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import db
import delivery
import scraper
from scraper import ScrapeError, SearchReport

# Сохранённые HTML-примеры для всех 23 проверок. Это данные, не код.
FIXTURES = json.loads(zlib.decompress(base64.b64decode(
    "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"
    "hhxJhnp7gMnP/w85xTVN"
)).decode("utf-8"))
BASE = "https://tvbrics.com/news/"


def fixture(name):
    return FIXTURES[name]


def card(slug, day):
    return (f'<a class="news-card" href="/news/{slug}/">'
            f'<div class="head-news-card__date">{day}</div>'
            '<div class="news-card__title">Обрезанный заголовок...</div></a>')


def page(contents, more=False):
    button = ('<button class="js_news_list_show_more" '
              'data-url="/ajax/filter_news_list.php" data-page="2" data-showby="36" '
              'data-filter=\'{"IBLOCK_ID":60,"PROPERTY_COUNTRY_ITEMS":784184}\'></button>')
    return '<div id="filter_news_list">' + contents + (button if more else '') + '</div>'


class ParsingTests(unittest.TestCase):
    def test_all_six_live_layouts_and_language_specific_filters(self):
        blocks = {"ru": 60, "en": 44, "cn": 63, "pt": 73, "es": 129, "ar": 148}
        for lang, block in blocks.items():
            with self.subTest(lang=lang):
                base = BASE if lang == "ru" else f"https://tvbrics.com/{lang}/news/"
                endpoint, form = scraper.parse_country_filter(fixture(f"home-{lang}.html"), base)
                self.assertEqual(form["id"], "784184")
                prefix = "" if lang == "ru" else lang + "/"
                self.assertEqual(endpoint, f"https://tvbrics.com/{prefix}ajax/filter_news_list.php")
                cards, more = scraper.parse_feed(fixture(f"feed-{lang}.html"), base)
                self.assertEqual(len(cards), 3)
                self.assertTrue(all(c.date is not None for c in cards))
                self.assertEqual(more.filters["IBLOCK_ID"], block)
                self.assertEqual(more.form()["filter[PROPERTY_COUNTRY_ITEMS]"], "784184")

    def test_country_id_is_read_from_current_html(self):
        html = fixture("home-en.html").replace('data-id="784184"', 'data-id="99999"')
        _, form = scraper.parse_country_filter(html, BASE)
        self.assertEqual(form["id"], "99999")

    def test_date_formats_and_invalid_dates(self):
        for text in ["02.09.26", "02.09.2026", "2026.09.02", "2026-09-02T10:30:00",
                     "26年09月02日 | 13:00", "2026年9月2日", "٠٢.٠٩.٢٦", "۰۲.۰۹.۲۶"]:
            with self.subTest(text=text):
                self.assertEqual(scraper.parse_card_date(text), datetime(2026, 9, 2))
        for text in ["31.02.26", "02.13.26", "", "новый формат"]:
            self.assertIsNone(scraper.parse_card_date(text))

    def test_calendar_window_uses_moscow_and_includes_whole_first_day(self):
        start, end = scraper.search_window(10, datetime(2026, 9, 6, 22, tzinfo=timezone.utc))
        self.assertEqual((start, end), (date(2026, 8, 29), date(2026, 9, 7)))
        self.assertEqual(scraper.search_window(1, datetime(2026, 9, 2)), (date(2026, 9, 2),) * 2)
        with self.assertRaises(ValueError):
            scraper.search_window(0)

    def test_dedup_and_sidebar_isolation(self):
        content = page(card("same", "02.09.26") * 2) + '<aside>' + card("sidebar", "01.01.20") + '</aside>'
        cards, _ = scraper.parse_feed(content, BASE)
        self.assertEqual([c.url for c in cards], ["https://tvbrics.com/news/same/"])

    def test_only_article_body_counts_and_title_is_full(self):
        title, names = scraper.parse_article(fixture("article.html"), BASE + "test/")
        self.assertEqual(title, "Полный заголовок статьи")
        self.assertEqual(names, ["Tehran Times"])

    def test_partner_domain_boundaries_and_subdomains(self):
        self.assertEqual(scraper.partner_names([
            "https://fake-irna.ir/test", "https://irna.ir.example.org/test",
            "https://example.org/?source=irna.ir", "mailto:news@irna.ir",
            "https://www.IRNA.ir:443/a", "https://en.irna.ir/b",
        ]), ["IRNA"])

    def test_missing_layout_is_an_error(self):
        with self.assertRaises(ScrapeError):
            scraper.parse_country_filter("<h1>Other page</h1>", BASE)
        with self.assertRaises(ScrapeError):
            scraper.parse_article("<h1>Temporary error</h1>", BASE)
        with self.assertRaises(ScrapeError):
            scraper.parse_feed("<h1>Other page</h1>", BASE)

    def test_external_feed_endpoint_is_rejected(self):
        with self.assertRaises(ScrapeError):
            scraper.parse_country_filter(fixture("home-ru.html").replace(
                '/ajax/filter_news_list.php', 'https://example.org/filter'), BASE)

    def test_failed_search_is_not_reported_as_no_news(self):
        report = SearchReport(date(2026, 8, 29), date(2026, 9, 7))
        report.add_error("RU", "failed")
        self.assertNotIn("новостей иранских партнёров нет", delivery.format_summary(report))
        self.assertIn("не полностью", delivery.format_summary(report))

    def test_access_check_is_distinguished_from_normal_html(self):
        challenge = '<script src="/.well-known/ddos-guard/js-challenge/index.js"></script>'
        for status, body in [(403, "Denied"), (429, "Too many requests"), (200, challenge)]:
            with self.subTest(status=status, body=body):
                with self.assertRaises(scraper.AccessBlocked):
                    scraper.check_response(status, body, BASE)
        scraper.check_response(200, fixture("home-ru.html"), BASE)
        with self.assertRaises(ScrapeError):
            scraper.check_response(500, "Temporary failure", BASE)


class CollectorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "seen.db"
        self.db_patch = patch.object(db, "DB_PATH", str(self.path))
        self.db_patch.start()
        self.pause = patch("scraper.asyncio.sleep", new=AsyncMock())
        self.pause.start()
        self.log = AsyncMock()

    def tearDown(self):
        self.pause.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    async def test_pagination_keeps_fresh_after_old_featured_card(self):
        responses = [fixture("home-ru.html"),
                     page(card("first", "02.09.26") + card("pinned", "01.01.20"), more=True),
                     card("second", "01.09.26") + card("first", "02.09.26"),
                     card("old", "01.08.26"), fixture("article.html"), fixture("article.html")]
        report = SearchReport(date(2026, 8, 29), date(2026, 9, 7))
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=responses)) as fetch:
            await scraper.collect_language(None, "RU", BASE, report, self.log, dry_run=True)
        self.assertEqual(len(report.items), 2)
        self.assertEqual(report.errors, {})
        self.assertEqual(fetch.await_args_list[2].kwargs["data"]["page"], "2")
        self.assertEqual(fetch.await_args_list[3].kwargs["data"]["page"], "3")
        self.assertFalse(self.path.exists())

    async def test_future_and_before_window_are_excluded(self):
        responses = [fixture("home-ru.html"),
                     page(card("start", "29.08.26") + card("yesterday", "28.08.26") + card("future", "08.09.26")),
                     fixture("article.html")]
        report = SearchReport(date(2026, 8, 29), date(2026, 9, 7))
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=responses)):
            await scraper.collect_language(None, "RU", BASE, report, self.log, dry_run=True)
        self.assertEqual([x["date"] for x in report.items], ["29.08.2026"])

    async def test_article_failure_does_not_drop_other_articles_or_mark_failed_seen(self):
        responses = [fixture("home-ru.html"), page(card("bad", "02.09.26") + card("good", "02.09.26")),
                     ScrapeError("temporary failure"), fixture("article.html")]
        report = SearchReport(date(2026, 8, 29), date(2026, 9, 7))
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=responses)):
            await scraper.collect_language(None, "RU", BASE, report, self.log)
        self.assertEqual(len(report.items), 1)
        self.assertIn("RU", report.errors)
        self.assertFalse(db.is_seen("https://tvbrics.com/news/bad/"))
        self.assertFalse(db.is_seen("https://tvbrics.com/news/good/"))

    async def test_pagination_failure_preserves_already_collected_articles(self):
        responses = [fixture("home-ru.html"), page(card("good", "02.09.26"), more=True),
                     ScrapeError("page failed"), fixture("article.html")]
        report = SearchReport(date(2026, 8, 29), date(2026, 9, 7))
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=responses)):
            await scraper.collect_language(None, "RU", BASE, report, self.log, dry_run=True)
        self.assertEqual(len(report.items), 1)
        self.assertIn("RU", report.errors)

    async def test_invalid_date_is_visible_as_partial_search(self):
        responses = [fixture("home-ru.html"), page(card("unknown", "changed format") + card("good", "02.09.26")),
                     fixture("article.html")]
        report = SearchReport(date(2026, 8, 29), date(2026, 9, 7))
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=responses)):
            await scraper.collect_language(None, "RU", BASE, report, self.log, dry_run=True)
        self.assertEqual(len(report.items), 1)
        self.assertIn("RU", report.errors)
        self.assertEqual(report.completed_languages, [])

    async def test_wrong_country_on_next_page_is_rejected(self):
        html = page(card("one", "02.09.26"), more=True).replace('"PROPERTY_COUNTRY_ITEMS":784184', '"PROPERTY_COUNTRY_ITEMS":784168')
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=[fixture("home-ru.html"), html])):
            with self.assertRaises(ScrapeError):
                await scraper.collect_language(None, "RU", BASE,
                    SearchReport(date(2026, 8, 29), date(2026, 9, 7)), self.log)

    async def test_empty_response_and_failures_are_reported_for_each_language(self):
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=ScrapeError("HTTP 500"))):
            report = await scraper.run_search(self.log, dry_run=True, languages=["RU", "CN"], source=object())
        self.assertEqual(set(report.errors), {"RU", "CN"})
        self.assertEqual(report.completed_languages, [])
        self.assertEqual(report.items, [])

    async def test_access_block_stops_all_further_site_requests(self):
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=scraper.AccessBlocked("Access check"))) as fetch:
            report = await scraper.run_search(self.log, dry_run=True, source=object())
        self.assertEqual(fetch.await_count, 1)
        self.assertEqual(set(report.errors), {lang for lang, _ in scraper.LANGS})
        self.assertEqual(report.completed_languages, [])

    async def test_access_block_keeps_previously_found_articles_unmarked(self):
        responses = [fixture("home-ru.html"), page(card("good", "02.09.26") + card("blocked", "02.09.26")),
                     fixture("article.html"), scraper.AccessBlocked("Access check")]
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=responses)) as fetch:
            report = await scraper.run_search(self.log, source=object(), now=datetime(2026, 9, 7))
        self.assertEqual(fetch.await_count, 4)
        self.assertEqual(len(report.items), 1)
        self.assertEqual(set(report.errors), {lang for lang, _ in scraper.LANGS})
        self.assertFalse(db.is_seen("https://tvbrics.com/news/good/"))

    async def test_browser_stops_on_denial_before_clicking_anything(self):
        response = MagicMock(status=403, url=BASE)
        response.text = AsyncMock(return_value="Access check")
        page_mock = MagicMock()
        page_mock.goto = AsyncMock(return_value=response)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page_mock)
        with self.assertRaises(scraper.AccessBlocked):
            await scraper.fetch_html(scraper.BrowserSource(context), BASE)
        page_mock.locator.assert_not_called()

    async def test_dry_run_does_not_change_legacy_database(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE seen (url TEXT PRIMARY KEY, lang TEXT, title TEXT, partner TEXT, news_date TEXT, found_at TEXT)")
            conn.execute("INSERT INTO seen VALUES ('old','RU','Old','IRNA','01.01.2026','old')")
        before = self.path.read_bytes()
        html = '<h1>News</h1><div class="news-detail-content">Article without partner</div>'
        responses = [fixture("home-ru.html"), page(card("new", "02.09.26")), html]
        with patch("scraper.fetch_html", new=AsyncMock(side_effect=responses)):
            await scraper.collect_language(None, "RU", BASE,
                SearchReport(date(2026, 8, 29), date(2026, 9, 7)), self.log, dry_run=True)
        self.assertEqual(self.path.read_bytes(), before)

    async def test_delivery_retries_only_unconfirmed_messages(self):
        report = SearchReport(date(2026, 8, 29), date(2026, 9, 7), items=[
            dict(partner="IRNA", date="02.09.2026", title="One", lang="RU", url="one"),
            dict(partner="IRNA", date="02.09.2026", title="Two", lang="RU", url="two"),
        ])
        sent = []

        async def send(chat, text):
            if chat == "B" and text.startswith("Партнер:"):
                raise RuntimeError("delivery failed")
            sent.append((chat, text))

        failed = await delivery.deliver_report(send, ["A", "B"], report, self.log)
        self.assertEqual(failed, ["B"])
        self.assertTrue(db.was_delivered("one", "A"))
        self.assertFalse(db.is_seen("one"))
        next_send = AsyncMock()
        self.assertEqual(await delivery.deliver_report(next_send, ["A", "B"], report, self.log), [])
        a_news = [call for call in next_send.await_args_list if call.args[0] == "A" and call.args[1].startswith("Партнер:")]
        self.assertEqual(a_news, [])
        self.assertTrue(db.is_seen("one"))
        self.assertTrue(db.is_seen("two"))


if __name__ == "__main__":
    unittest.main()

