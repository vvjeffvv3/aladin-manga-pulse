from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from dashboard.service import dashboard_service


class DashboardServiceTests(SimpleTestCase):
    def test_set_rank_status_assigns_expected_status(self):
        """신규·기준선·상승·하락·동일 순위 상태를 판정"""
        cases = (
            (True, None, "new"),
            (False, None, "baseline"),
            (False, 3, "up"),
            (False, -2, "down"),
            (False, 0, "same"),
        )

        for is_new, rank_change, expected in cases:
            with self.subTest(expected=expected):
                book = SimpleNamespace(
                    is_new=is_new,
                    rank_change=rank_change,
                )

                result = dashboard_service.set_rank_status(book)

                self.assertIs(result, book)
                self.assertEqual(book.rank_status, expected)

    @patch.object(dashboard_service, "decorate_book_collection_status")
    @patch.object(dashboard_service, "get_top_series")
    @patch.object(dashboard_service, "search_books")
    @patch.object(dashboard_service, "get_previous_snapshot_time")
    @patch.object(dashboard_service, "get_latest_snapshot_time")
    def test_get_home_dashboard_builds_today_dashboard(
        self,
        get_latest_snapshot_time,
        get_previous_snapshot_time,
        search_books,
        get_top_series,
        decorate_book_collection_status,
    ):
        """오늘의 도서·전일 비교·인기 시리즈를 대시보드 데이터로 구성"""
        latest = datetime(2026, 9, 8, 9, 0)
        previous = datetime(2026, 9, 7, 9, 0)
        rising_book = SimpleNamespace(
            is_new=False,
            rank_change=3,
            book=SimpleNamespace(release_date="2026-08-12"),
        )
        new_book = SimpleNamespace(
            is_new=True,
            rank_change=None,
            book=SimpleNamespace(release_date="2026-09"),
        )
        popular_series = SimpleNamespace(series_name="주술회전")

        get_latest_snapshot_time.return_value = latest
        get_previous_snapshot_time.return_value = previous
        search_books.return_value = [rising_book, new_book]
        get_top_series.return_value = [popular_series]

        result = dashboard_service.get_home_dashboard(
            book_limit=2,
            series_limit=1,
        )

        self.assertEqual(result["latest_snapshot"], latest)
        self.assertEqual(result["previous_snapshot"], previous)
        self.assertEqual(result["books"], [rising_book, new_book])
        self.assertEqual(result["series"], [popular_series])
        self.assertEqual(rising_book.rank_status, "up")
        self.assertEqual(new_book.rank_status, "new")
        self.assertEqual(rising_book.release_date_display, "2026.08")
        self.assertEqual(new_book.release_date_display, "2026.09")

        search_books.assert_called_once_with(
            snapshot_time=latest,
            sort_by="rank",
            descending=False,
        )
        get_top_series.assert_called_once_with(
            snapshot_time=latest,
            limit=1,
        )
        decorate_book_collection_status.assert_called_once_with(
            [rising_book, new_book]
        )

    @patch.object(dashboard_service, "get_top_series")
    @patch.object(dashboard_service, "search_books")
    @patch.object(dashboard_service, "get_previous_snapshot_time")
    @patch.object(dashboard_service, "get_latest_snapshot_time")
    def test_get_home_dashboard_returns_empty_data_without_snapshot(
        self,
        get_latest_snapshot_time,
        get_previous_snapshot_time,
        search_books,
        get_top_series,
    ):
        """수집 데이터가 없으면 빈 대시보드 데이터를 반환"""
        get_latest_snapshot_time.return_value = None

        result = dashboard_service.get_home_dashboard()

        self.assertEqual(
            result,
            {
                "latest_snapshot": None,
                "previous_snapshot": None,
                "books": [],
                "series": [],
            },
        )
        get_previous_snapshot_time.assert_not_called()
        search_books.assert_not_called()
        get_top_series.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()
