from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from dashboard.service import search_service


class SearchServiceTests(SimpleTestCase):
    @patch.object(search_service, "decorate_book_collection_status")
    @patch.object(search_service, "get_latest_volume_map")
    @patch.object(search_service, "search_books")
    def test_get_search_result_decorates_and_returns_filters(
        self,
        search_books,
        get_latest_volume_map,
        decorate_book_collection_status,
    ):
        """검색 결과에 최신 권수·발매일 표시와 검색 조건을 반영"""
        snapshot_time = datetime(2026, 9, 8, 9, 0)
        first_book = SimpleNamespace(
            series_id=11,
            release_date="2026-08-12",
        )
        second_book = SimpleNamespace(
            series_id=None,
            release_date="2026-09",
        )
        first_snapshot = SimpleNamespace(book=first_book)
        second_snapshot = SimpleNamespace(book=second_book)
        search_books.return_value = [first_snapshot, second_snapshot]
        get_latest_volume_map.return_value = {11: 30}

        result = search_service.get_search_result(
            snapshot_time=snapshot_time,
            keyword="주술회전",
            search_field="title",
            sort_by="rating",
            direction="desc",
            page_number=1,
            page_size=10,
        )

        self.assertEqual(result["keyword"], "주술회전")
        self.assertEqual(result["search_field"], "title")
        self.assertEqual(result["sort_by"], "rating")
        self.assertEqual(result["direction"], "desc")
        self.assertEqual(
            list(result["page_obj"]),
            [first_snapshot, second_snapshot],
        )
        self.assertEqual(first_snapshot.release_date_display, "2026.08")
        self.assertEqual(second_snapshot.release_date_display, "2026.09")
        self.assertEqual(first_snapshot.latest_series_volume_no, 30)
        self.assertIsNone(second_snapshot.latest_series_volume_no)

        search_books.assert_called_once_with(
            snapshot_time=snapshot_time,
            keyword="주술회전",
            search_field="title",
            sort_by="rating",
            descending=True,
        )
        get_latest_volume_map.assert_called_once_with({11})
        decorate_book_collection_status.assert_called_once_with(
            result["page_obj"]
        )

    @patch.object(search_service, "decorate_book_collection_status")
    @patch.object(search_service, "get_latest_volume_map")
    @patch.object(search_service, "search_books")
    def test_get_search_result_handles_no_matches(
        self,
        search_books,
        get_latest_volume_map,
        decorate_book_collection_status,
    ):
        """검색 결과가 없으면 빈 페이지를 반환하고 오류를 내지 않음"""
        search_books.return_value = []
        get_latest_volume_map.return_value = {}

        result = search_service.get_search_result(
            snapshot_time=datetime(2026, 9, 8, 9, 0),
            keyword="존재하지않는만화",
            page_size=50,
        )

        self.assertEqual(result["page_obj"].paginator.count, 0)
        self.assertEqual(list(result["page_obj"]), [])
        get_latest_volume_map.assert_called_once_with(set())
        decorate_book_collection_status.assert_called_once_with(
            result["page_obj"]
        )

    @patch.object(search_service, "decorate_book_collection_status")
    @patch.object(search_service, "get_latest_volume_map", return_value={})
    @patch.object(search_service, "search_books", return_value=[])
    def test_get_search_result_clamps_page_size(
        self,
        search_books,
        get_latest_volume_map,
        decorate_book_collection_status,
    ):
        """검색 페이지 크기를 1개 이상 100개 이하로 제한"""
        too_large = search_service.get_search_result(
            snapshot_time=datetime(2026, 9, 8, 9, 0),
            page_size=999,
        )
        invalid = search_service.get_search_result(
            snapshot_time=datetime(2026, 9, 8, 9, 0),
            page_size="잘못된값",
        )

        self.assertEqual(too_large["page_obj"].paginator.per_page, 100)
        self.assertEqual(invalid["page_obj"].paginator.per_page, 50)


if __name__ == "__main__":
    import unittest

    unittest.main()
