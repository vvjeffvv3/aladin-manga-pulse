from datetime import datetime
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from dashboard.models import (
    Book,
    BookSnapshot,
    OwnedFolder,
    OwnedSeries,
    OwnedSeriesFolder,
    OwnedSeriesPosition,
    OwnedSeriesVolume,
    Series,
    SeriesDailyStat,
)
from dashboard.repository import book_repository, owned_series_repository
from dashboard.repository import series_repository


TEST_MODELS = (
    Series,
    OwnedFolder,
    Book,
    OwnedSeries,
    OwnedSeriesVolume,
    OwnedSeriesFolder,
    OwnedSeriesPosition,
    BookSnapshot,
    SeriesDailyStat,
)


class RepositoryIntegrationTests(TransactionTestCase):
    """실제 ORM 쿼리와 테스트 DB 저장·조회 동작을 검증한다."""

    databases = {"default"}
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._created_models = []
        with connection.schema_editor() as schema_editor:
            for model in TEST_MODELS:
                schema_editor.create_model(model)
                cls._created_models.append(model)

    @classmethod
    def tearDownClass(cls):
        try:
            with connection.schema_editor() as schema_editor:
                for model in reversed(cls._created_models):
                    schema_editor.delete_model(model)
        finally:
            super().tearDownClass()

    def setUp(self):
        for model in reversed(TEST_MODELS):
            model.objects.all().delete()

    @staticmethod
    def _snapshot_time(day: int, hour: int = 9):
        return timezone.make_aware(datetime(2026, 9, day, hour, 0))

    @staticmethod
    def _book(
        item_id,
        series=None,
        title="테스트 만화",
        vol_no="1",
    ):
        now = timezone.now()
        return Book.objects.create(
            item_id=item_id,
            series=series,
            title=title,
            vol_no=vol_no,
            edition_type=None,
            special_benefits=None,
            author="테스트 작가",
            publisher="테스트 출판사",
            release_date="2026-09",
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _snapshot(
        book,
        collected_at,
        rank_no=1,
        sales_point=100,
        is_out=False,
    ):
        return BookSnapshot.objects.create(
            book=book,
            collected_at=collected_at,
            collected_date=collected_at.date(),
            rank_no=rank_no,
            price=6000,
            rating=Decimal("4.50"),
            sales_point=sales_point,
            previous_rank=None,
            rank_change=None,
            previous_sales_point=None,
            sales_point_change=None,
            is_new=False,
            is_out=is_out,
        )

    def test_snapshot_time_queries_ignore_out_and_return_latest_first(self):
        """스냅샷 조회가 이탈 행을 제외하고 최신 수집 시각부터 반환"""
        series = Series.objects.create(series_name="주술회전")
        first_book = self._book("B-001", series, "주술회전 1", "1")
        second_book = self._book("B-002", series, "주술회전 2", "2")
        out_book = self._book("B-003", series, "주술회전 3", "3")
        first_time = self._snapshot_time(7)
        latest_time = self._snapshot_time(8)

        self._snapshot(first_book, first_time, rank_no=2)
        self._snapshot(first_book, latest_time, rank_no=1)
        self._snapshot(second_book, latest_time, rank_no=2)
        self._snapshot(out_book, latest_time, rank_no=None, is_out=True)

        self.assertEqual(
            list(book_repository.get_snapshot_times()),
            [latest_time, first_time],
        )
        self.assertEqual(book_repository.get_latest_snapshot_time(), latest_time)
        self.assertEqual(
            book_repository.get_previous_snapshot_time(),
            first_time,
        )

    def test_search_books_filters_text_out_rows_and_sorts_numeric_values(self):
        """도서 검색이 텍스트 조건·이탈 제외·평점 내림차순을 실제 ORM으로 처리"""
        series = Series.objects.create(series_name="테스트 시리즈")
        first_book = self._book("B-010", series, "테스트 만화 1", "1")
        second_book = self._book("B-011", series, "테스트 만화 2", "2")
        out_book = self._book("B-012", series, "숨김 만화", "3")
        snapshot_time = self._snapshot_time(8)

        first_snapshot = self._snapshot(
            first_book,
            snapshot_time,
            rank_no=2,
            sales_point=100,
        )
        first_snapshot.rating = Decimal("4.20")
        first_snapshot.save(update_fields=["rating"])
        second_snapshot = self._snapshot(
            second_book,
            snapshot_time,
            rank_no=1,
            sales_point=200,
        )
        second_snapshot.rating = Decimal("4.80")
        second_snapshot.save(update_fields=["rating"])
        self._snapshot(out_book, snapshot_time, rank_no=3, is_out=True)

        results = list(
            book_repository.search_books(
                snapshot_time=snapshot_time,
                keyword="테스트",
                search_field="title",
                sort_by="rating",
                descending=True,
            )
        )

        self.assertEqual([snapshot.book.item_id for snapshot in results], ["B-011", "B-010"])
        self.assertEqual(
            list(
                book_repository.search_books(
                    snapshot_time=snapshot_time,
                    keyword="숨김",
                    search_field="title",
                    include_out=True,
                )
            )[0].book.item_id,
            "B-012",
        )

    def test_popular_series_aggregates_counts_sales_and_sorted_volumes(self):
        """인기 시리즈 집계가 등장 수·판매지수·권수 목록을 계산"""
        popular = Series.objects.create(series_name="인기 시리즈")
        other = Series.objects.create(series_name="다른 시리즈")
        no_series_book = self._book("B-020", title="단독 도서", vol_no="1")
        popular_books = [
            self._book("B-021", popular, "인기 시리즈 10", "10"),
            self._book("B-022", popular, "인기 시리즈 2", "2"),
            self._book("B-023", popular, "인기 시리즈 1", "1"),
        ]
        other_book = self._book("B-024", other, "다른 시리즈 1", "1")
        snapshot_time = self._snapshot_time(8)

        self._snapshot(no_series_book, snapshot_time, rank_no=8, sales_point=999)
        self._snapshot(popular_books[0], snapshot_time, rank_no=4, sales_point=100)
        self._snapshot(popular_books[1], snapshot_time, rank_no=2, sales_point=200)
        self._snapshot(popular_books[2], snapshot_time, rank_no=6, sales_point=300)
        self._snapshot(other_book, snapshot_time, rank_no=1, sales_point=900)
        SeriesDailyStat.objects.create(
            series=popular,
            collected_at=snapshot_time,
            collected_date=snapshot_time.date(),
            series_rank=1,
            volume_count=3,
            best_rank=2,
            avg_rank=Decimal("4.00"),
            total_sales_point=600,
            avg_sales_point=Decimal("200.00"),
        )

        result = series_repository.get_top_series(snapshot_time, limit=2)

        self.assertEqual([stat.series.series_name for stat in result], ["인기 시리즈", "다른 시리즈"])
        self.assertEqual(result[0].volume_count, 3)
        self.assertEqual(result[0].best_rank, 2)
        self.assertEqual(result[0].total_sales_point, 600)
        self.assertEqual(result[0].volume_numbers, "1, 2, 10")
        self.assertEqual(
            list(series_repository.get_series_snapshot_times()),
            [snapshot_time],
        )

    def test_search_books_sorts_by_price_in_both_directions(self):
        """도서 검색이 가격 기준 오름차순·내림차순을 모두 지원"""
        series = Series.objects.create(series_name="가격 시리즈")
        cheaper_book = self._book("B-025", series, "가격 시리즈 저가", "1")
        expensive_book = self._book("B-026", series, "가격 시리즈 고가", "2")
        snapshot_time = self._snapshot_time(8)
        cheaper_snapshot = self._snapshot(
            cheaper_book,
            snapshot_time,
            rank_no=2,
        )
        expensive_snapshot = self._snapshot(
            expensive_book,
            snapshot_time,
            rank_no=1,
        )
        cheaper_snapshot.price = 5000
        cheaper_snapshot.save(update_fields=["price"])
        expensive_snapshot.price = 8000
        expensive_snapshot.save(update_fields=["price"])

        ascending = list(
            book_repository.search_books(
                snapshot_time=snapshot_time,
                sort_by="price",
            )
        )
        descending = list(
            book_repository.search_books(
                snapshot_time=snapshot_time,
                sort_by="price",
                descending=True,
            )
        )

        self.assertEqual(
            [snapshot.book.item_id for snapshot in ascending],
            ["B-025", "B-026"],
        )
        self.assertEqual(
            [snapshot.book.item_id for snapshot in descending],
            ["B-026", "B-025"],
        )

    def test_search_series_returns_known_volume_count(self):
        """시리즈 검색이 이름 조건과 실제 등록 권수 집계를 반환"""
        target = Series.objects.create(series_name="주술회전")
        Series.objects.create(series_name="체인소맨")
        self._book("B-030", target, "주술회전 1", "1")
        self._book("B-031", target, "주술회전 2", "2")

        results = list(owned_series_repository.search_series("  주술  "))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].series_name, "주술회전")
        self.assertEqual(results[0].known_volume_count, 2)

    def test_owned_volume_replacement_updates_summary_and_maps(self):
        """보유 권수 교체가 중복을 제거하고 요약값·권수 맵을 함께 갱신"""
        series = Series.objects.create(series_name="보유 시리즈")
        owned = OwnedSeries.objects.create(
            series=series,
            owned_volume_no=0,
            latest_volume_no=5,
            latest_checked_at=None,
            source_url=None,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

        self.assertTrue(
            owned_series_repository.replace_owned_volumes(
                owned.owned_series_id,
                [1, 4, 4],
            )
        )

        owned.refresh_from_db()
        self.assertEqual(owned.owned_volume_no, 2)
        self.assertEqual(
            owned_series_repository.get_owned_volume_map({owned.owned_series_id}),
            {owned.owned_series_id: [1, 4]},
        )
        self.assertEqual(
            owned_series_repository.get_collection_status_map({series.series_id}),
            {series.series_id: "owned"},
        )

    def test_add_owned_series_record_keeps_highest_owned_and_latest_values(self):
        """보유 시리즈 재등록 시 보유 권수·최신 권수가 감소하지 않음"""
        series = Series.objects.create(series_name="업데이트 시리즈")

        record, created = owned_series_repository.add_owned_series_record(
            series.series_id,
            latest_volume_no=10,
            source_url="https://www.aladin.co.kr/item/1",
            owned_volume_no=5,
        )
        updated_record, created_again = owned_series_repository.add_owned_series_record(
            series.series_id,
            latest_volume_no=8,
            source_url="https://www.aladin.co.kr/item/2",
            owned_volume_no=2,
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(record.owned_series_id, updated_record.owned_series_id)
        updated_record.refresh_from_db()
        self.assertEqual(updated_record.owned_volume_no, 5)
        self.assertEqual(updated_record.latest_volume_no, 10)
        self.assertEqual(updated_record.source_url, "https://www.aladin.co.kr/item/2")

    def test_folder_and_series_reorder_persist_sort_order(self):
        """폴더와 보유 시리즈 순서 변경이 정렬값으로 저장"""
        first_folder = OwnedFolder.objects.create(
            folder_name="첫 폴더",
            sort_order=0,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        second_folder = OwnedFolder.objects.create(
            folder_name="둘째 폴더",
            sort_order=1,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        first_series = Series.objects.create(series_name="첫 시리즈")
        second_series = Series.objects.create(series_name="둘째 시리즈")
        first_owned = OwnedSeries.objects.create(
            series=first_series,
            owned_volume_no=1,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        second_owned = OwnedSeries.objects.create(
            series=second_series,
            owned_volume_no=1,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

        owned_series_repository.reorder_owned_folders(
            [second_folder.folder_id, first_folder.folder_id]
        )
        owned_series_repository.reorder_owned_series(
            [second_owned.owned_series_id, first_owned.owned_series_id]
        )

        first_folder.refresh_from_db()
        second_folder.refresh_from_db()
        self.assertEqual(second_folder.sort_order, 0)
        self.assertEqual(first_folder.sort_order, 1)
        positions = {
            row.owned_series_id: row.sort_order
            for row in OwnedSeriesPosition.objects.all()
        }
        self.assertEqual(
            positions,
            {
                second_owned.owned_series_id: 0,
                first_owned.owned_series_id: 1,
            },
        )

    def test_series_folder_link_and_volume_values_are_readable(self):
        """시리즈 폴더 연결과 등록 도서 권수 조회가 실제 테이블에서 동작"""
        folder = OwnedFolder.objects.create(
            folder_name="작품 폴더",
            sort_order=0,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        series = Series.objects.create(series_name="연결 시리즈")
        owned = OwnedSeries.objects.create(
            series=series,
            owned_volume_no=1,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self._book("B-040", series, "연결 시리즈 1", "1")
        self._book("B-041", series, "연결 시리즈 2", "2")
        OwnedSeriesFolder.objects.create(owned_series=owned, folder=folder)

        self.assertEqual(
            owned_series_repository.get_series_volume_values(series.series_id),
            ["1", "2"],
        )
        self.assertEqual(
            owned_series_repository.get_owned_series_folder_map(
                {owned.owned_series_id}
            ),
            {owned.owned_series_id: folder.folder_id},
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
