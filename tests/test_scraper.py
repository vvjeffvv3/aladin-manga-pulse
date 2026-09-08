import io
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import Mock, call, patch

import requests
from bs4 import BeautifulSoup

from aladin_manga_scraper import (
    RetryablePageError,
    fetch_page,
    is_aladin_error_page,
    parse_book,
    split_title_fields,
)


class ScraperParsingTests(unittest.TestCase):
    def test_split_title_fields_extracts_volume_and_edition(self):
        """시리즈명, 권수, 판본 분리"""
        result = split_title_fields("주술회전 15 (특장판)")

        self.assertEqual(result, ("주술회전", "15", "특장판"))

    def test_parse_book_extracts_requested_fields(self):
        """HTML에서 제목, 작가, 출판사, 발매일, 가격, 평점, 판매지수 추출"""
        html = """
        <div class="ss_book_list">
          <ul>
            <li>
              <a class="bo3" href="/shop/wproduct.aspx?ItemId=12345">
                주술회전 15 (특장판)
              </a>
              <span class="ss_f_g2">
                - 초판 한정 투명 PET 카드 1종
              </span>
            </li>
            <li>
              <a href="/shop/author/authorsearch.aspx">아쿠타미 게게</a>
              (지은이), <a href="/shop/wbrowse.aspx?PublisherSearch=1">
              서울미디어코믹스</a> |
              서울미디어코믹스 | 2026년 8월
            </li>
            <li>정가 6,000원 → <span class="ss_p2"><em>5,400원</em></span></li>
            <li><span class="star_score">9.8</span></li>
            <li><span class="sales_point">1,234</span></li>
          </ul>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        book = parse_book(soup.select_one("a.bo3"))

        self.assertIsNotNone(book)
        self.assertEqual(book["title"], "주술회전 15 (특장판)")
        self.assertEqual(book["series_name"], "주술회전")
        self.assertEqual(book["vol_no"], "15")
        self.assertEqual(book["edition_type"], "특장판")
        self.assertEqual(book["special_benefits"], "- 초판 한정 투명 PET 카드 1종")
        self.assertEqual(book["author"], "아쿠타미 게게")
        self.assertEqual(book["publisher"], "서울미디어코믹스")
        self.assertEqual(book["release_date"], "2026-08")
        self.assertEqual(book["price"], 5400)
        self.assertEqual(book["rating"], 9.8)
        self.assertEqual(book["sales_point"], 1234)

    def test_is_aladin_error_page_detects_known_error_markup(self):
        """알라딘 오류 페이지 감지"""
        soup = BeautifulSoup(
            '<div id="lbErrorInfo">요청하신 페이지에 오류가 존재합니다</div>',
            "html.parser",
        )

        self.assertTrue(is_aladin_error_page(soup))


class FetchPageRetryTests(unittest.TestCase):
    @staticmethod
    def _response(content: bytes) -> Mock:
        response = Mock()
        response.content = content
        response.raise_for_status.return_value = None
        return response

    def test_fetch_page_retries_transient_network_errors_then_succeeds(self):
        """네트워크 오류 3회 재시도 후 성공"""
        success_html = b'<a class="bo3" href="?ItemId=123">book</a>'
        session = Mock()
        session.get.side_effect = [
            requests.RequestException("timeout"),
            requests.RequestException("connection reset"),
            requests.RequestException("temporary failure"),
            self._response(success_html),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "page_001.html"
            with patch("aladin_manga_scraper.time.sleep") as sleep:
                with redirect_stdout(io.StringIO()):
                    soup = fetch_page(session, "https://example.com", 1, raw_path)

        self.assertIsNotNone(soup.select_one("a.bo3"))
        self.assertEqual(session.get.call_count, 4)
        sleep.assert_has_calls([call(3), call(6), call(12)])
        self.assertEqual(sleep.call_count, 3)

    def test_fetch_page_retries_aladin_error_html(self):
        """알라딘 오류 HTML 반환 후 재시도"""
        error_html = (
            '<div id="lbErrorInfo">요청하신 페이지에 오류가 존재합니다</div>'
        ).encode()
        success_html = b'<a class="bo3" href="?ItemId=123">book</a>'
        session = Mock()
        session.get.side_effect = [
            self._response(error_html),
            self._response(success_html),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "page_001.html"
            with patch("aladin_manga_scraper.time.sleep") as sleep:
                with redirect_stdout(io.StringIO()):
                    soup = fetch_page(session, "https://example.com", 1, raw_path)

            self.assertEqual(raw_path.read_bytes(), success_html)

        self.assertIsNotNone(soup.select_one("a.bo3"))
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(3)

    def test_fetch_page_raises_after_initial_request_and_three_retries(self):
        """최대 3회 재시도 후 실패 처리"""
        session = Mock()
        session.get.side_effect = requests.RequestException("unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "page_001.html"
            with patch("aladin_manga_scraper.time.sleep") as sleep:
                with redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, "최대 재시도 횟수"):
                        fetch_page(session, "https://example.com", 1, raw_path)

        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(sleep.call_count, 3)


if __name__ == "__main__":
    unittest.main()
