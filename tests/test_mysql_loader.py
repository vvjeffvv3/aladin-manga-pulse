import csv
import sys
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import mysql_loader


class FakeCursor:
    """mysql-connector cursor의 적재 동작만 기록하는 테스트 더블."""

    def __init__(self, state):
        self.state = state
        self.executed = []
        self.executemany_calls = []
        self.closed = False
        self._fetchone = None
        self._fetchall = []

    def execute(self, statement, parameters=None):
        normalized = " ".join(statement.split())
        self.executed.append((statement, parameters))

        if "FROM information_schema.columns" in normalized:
            self._fetchone = (1,)
        elif "FROM information_schema.statistics" in normalized:
            table_name = parameters[1]
            identity_column = (
                "item_id" if table_name == "book_snapshots" else "series_id"
            )
            self._fetchall = [
                (identity_column,),
                ("collected_date",),
            ]
        elif normalized.startswith("SELECT series_id FROM series"):
            series_name = parameters[0]
            series_ids = self.state.setdefault("series_ids", {})
            if series_name not in series_ids:
                series_ids[series_name] = 100 + len(series_ids) + 1
            self._fetchone = (series_ids[series_name],)

    def executemany(self, statement, parameters):
        self.executemany_calls.append((statement, list(parameters)))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall

    def close(self):
        self.closed = True


class FakeConnection:
    """커밋·롤백·커서 종료 여부를 확인할 수 있는 연결 테스트 더블."""

    def __init__(self):
        self.state = {}
        self.cursors = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self):
        cursor = FakeCursor(self.state)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


class MysqlLoaderTests(unittest.TestCase):
    @staticmethod
    def _write_csv(path: Path, fieldnames, rows):
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _all_executemany_calls(connection):
        return [
            call
            for cursor in connection.cursors
            for call in cursor.executemany_calls
        ]

    def test_upsert_books_deduplicates_and_normalizes_nullable_values(self):
        """도서 적재가 item_id 중복을 제거하고 빈 값을 NULL로 정리"""
        connection = FakeConnection()
        cursor = connection.cursor()
        rows = [
            {
                "item_id": "B-001",
                "series_name": "  주술회전  ",
                "title": "주술회전 15",
                "vol_no": "15",
                "edition_type": "",
                "special_benefits": "  ",
                "author": "아쿠타미 게게",
                "publisher": "서울미디어코믹스",
                "release_date": "2026-09",
            },
            {
                "item_id": "B-001",
                "series_name": "주술회전",
                "title": "주술회전 15 개정판",
                "vol_no": "15",
                "edition_type": "개정판",
                "special_benefits": "초판 특전",
                "author": "아쿠타미 게게",
                "publisher": "서울미디어코믹스",
                "release_date": "2026-09",
            },
        ]

        count = mysql_loader.upsert_books(cursor, rows, {})

        self.assertEqual(count, 1)
        self.assertEqual(len(cursor.executemany_calls), 1)
        parameters = cursor.executemany_calls[0][1]
        self.assertEqual(parameters[0][0], "B-001")
        self.assertEqual(parameters[0][2], "주술회전 15 개정판")
        self.assertEqual(parameters[0][4], "개정판")
        self.assertEqual(parameters[0][5], "초판 특전")

    def test_upsert_book_snapshots_converts_datetime_and_numeric_values(self):
        """스냅샷 적재가 날짜를 KST MySQL 시각으로 변환하고 숫자를 파싱"""
        connection = FakeConnection()
        cursor = connection.cursor()
        rows = [
            {
                "item_id": "B-001",
                "collected_at": "2026-09-08T00:30:00+00:00",
                "rank": "7",
                "price": "6,000",
                "rating": "4.80",
                "sales_point": "1,234",
                "previous_rank": "10",
                "rank_change": "3",
                "previous_sales_point": "900",
                "sales_point_change": "334",
                "is_new": "0",
                "is_out": "0",
            }
        ]

        count = mysql_loader.upsert_book_snapshots(cursor, rows)

        self.assertEqual(count, 1)
        parameters = cursor.executemany_calls[0][1][0]
        self.assertEqual(parameters[0], "B-001")
        self.assertEqual(parameters[1], datetime(2026, 9, 8, 9, 30))
        self.assertEqual(parameters[2:4], (7, 6000))
        self.assertEqual(parameters[4], Decimal("4.80"))
        self.assertEqual(parameters[5:10], (1234, 10, 3, 900, 334))

    def test_main_dry_run_validates_csv_without_connecting(self):
        """dry-run이 CSV를 중복 정리해 검증하고 MySQL 연결은 생략"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_path = temp_path / "books.csv"
            series_path = temp_path / "series.csv"
            self._write_csv(
                book_path,
                ["item_id", "title", "collected_at", "rank", "sales_point"],
                [
                    {
                        "item_id": "B-001",
                        "title": "주술회전 1",
                        "collected_at": "2026-09-08T09:00:00+09:00",
                        "rank": "2",
                        "sales_point": "100",
                    },
                    {
                        "item_id": "B-001",
                        "title": "주술회전 1",
                        "collected_at": "2026-09-08T10:00:00+09:00",
                        "rank": "1",
                        "sales_point": "200",
                    },
                ],
            )
            self._write_csv(
                series_path,
                ["collected_at", "series_name", "series_rank", "volume_count"],
                [
                    {
                        "collected_at": "2026-09-08T09:00:00+09:00",
                        "series_name": "주술회전",
                        "series_rank": "1",
                        "volume_count": "1",
                    },
                    {
                        "collected_at": "2026-09-08T10:00:00+09:00",
                        "series_name": "주술회전",
                        "series_rank": "1",
                        "volume_count": "1",
                    },
                ],
            )

            with patch.object(
                sys,
                "argv",
                [
                    "mysql_loader.py",
                    "--book-input",
                    str(book_path),
                    "--series-input",
                    str(series_path),
                    "--dry-run",
                ],
            ), patch.object(mysql_loader, "connect_database") as connect_database, patch(
                "builtins.print"
            ) as print_mock:
                mysql_loader.main()

        connect_database.assert_not_called()
        print_mock.assert_any_call("도서 Gold 행: 1개")
        print_mock.assert_any_call("시리즈 Gold 행: 1개")
        print_mock.assert_any_call("입력 CSV 검증을 완료했습니다.")

    def test_main_commits_loader_steps_in_order(self):
        """전체 Loader가 CSV 중복 제거 후 테이블·마이그레이션·적재 순서로 커밋"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_path = temp_path / "books.csv"
            series_path = temp_path / "series.csv"
            self._write_csv(
                book_path,
                [
                    "item_id",
                    "title",
                    "series_name",
                    "vol_no",
                    "collected_at",
                    "rank",
                    "price",
                    "rating",
                    "sales_point",
                    "is_new",
                    "is_out",
                ],
                [
                    {
                        "item_id": "B-001",
                        "title": "주술회전 1",
                        "series_name": "주술회전",
                        "vol_no": "1",
                        "collected_at": "2026-09-08T09:00:00+09:00",
                        "rank": "2",
                        "price": "6000",
                        "rating": "4.5",
                        "sales_point": "100",
                        "is_new": "0",
                        "is_out": "0",
                    },
                    {
                        "item_id": "B-001",
                        "title": "주술회전 1",
                        "series_name": "주술회전",
                        "vol_no": "1",
                        "collected_at": "2026-09-08T10:00:00+09:00",
                        "rank": "1",
                        "price": "6000",
                        "rating": "4.6",
                        "sales_point": "150",
                        "is_new": "0",
                        "is_out": "0",
                    },
                ],
            )
            self._write_csv(
                series_path,
                [
                    "collected_at",
                    "series_name",
                    "series_rank",
                    "volume_count",
                    "best_rank",
                    "avg_rank",
                    "total_sales_point",
                    "avg_sales_point",
                ],
                [
                    {
                        "collected_at": "2026-09-08T09:00:00+09:00",
                        "series_name": "주술회전",
                        "series_rank": "1",
                        "volume_count": "1",
                        "best_rank": "2",
                        "avg_rank": "2",
                        "total_sales_point": "100",
                        "avg_sales_point": "100",
                    },
                    {
                        "collected_at": "2026-09-08T10:00:00+09:00",
                        "series_name": "주술회전",
                        "series_rank": "1",
                        "volume_count": "1",
                        "best_rank": "1",
                        "avg_rank": "1",
                        "total_sales_point": "150",
                        "avg_sales_point": "150",
                    },
                ],
            )
            connection = FakeConnection()
            argv = [
                "mysql_loader.py",
                "--book-input",
                str(book_path),
                "--series-input",
                str(series_path),
                "--database",
                "test_database",
            ]

            with patch.object(sys, "argv", argv), patch.object(
                mysql_loader,
                "connect_database",
                return_value=connection,
            ), patch("builtins.print"):
                mysql_loader.main()

        self.assertEqual(connection.rollback_count, 0)
        self.assertEqual(connection.commit_count, 3)
        self.assertTrue(connection.closed)
        calls = self._all_executemany_calls(connection)
        self.assertEqual(len(calls), 3)
        books_call = next(call for call in calls if "INSERT INTO books" in call[0])
        snapshots_call = next(
            call for call in calls if "INSERT INTO book_snapshots" in call[0]
        )
        stats_call = next(
            call for call in calls if "INSERT INTO series_daily_stats" in call[0]
        )
        self.assertEqual(len(books_call[1]), 1)
        self.assertEqual(len(snapshots_call[1]), 1)
        self.assertEqual(len(stats_call[1]), 1)
        self.assertEqual(snapshots_call[1][0][2], 1)
        self.assertEqual(stats_call[1][0][2:4], (1, 1))

    def test_main_rolls_back_and_closes_connection_when_loading_fails(self):
        """적재 중 예외가 발생하면 롤백하고 커서·연결을 닫음"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            book_path = temp_path / "books.csv"
            series_path = temp_path / "series.csv"
            self._write_csv(
                book_path,
                ["item_id", "title", "collected_at", "rank", "sales_point"],
                [
                    {
                        "item_id": "B-001",
                        "title": "주술회전 1",
                        "collected_at": "2026-09-08T09:00:00+09:00",
                        "rank": "1",
                        "sales_point": "100",
                    }
                ],
            )
            self._write_csv(
                series_path,
                ["collected_at", "series_name", "series_rank", "volume_count"],
                [
                    {
                        "collected_at": "2026-09-08T09:00:00+09:00",
                        "series_name": "주술회전",
                        "series_rank": "1",
                        "volume_count": "1",
                    }
                ],
            )
            connection = FakeConnection()
            argv = [
                "mysql_loader.py",
                "--book-input",
                str(book_path),
                "--series-input",
                str(series_path),
            ]

            with patch.object(sys, "argv", argv), patch.object(
                mysql_loader,
                "connect_database",
                return_value=connection,
            ), patch.object(
                mysql_loader,
                "upsert_books",
                side_effect=RuntimeError("적재 실패"),
            ), patch("builtins.print"):
                with self.assertRaisesRegex(RuntimeError, "적재 실패"):
                    mysql_loader.main()

        self.assertEqual(connection.rollback_count, 1)
        self.assertTrue(connection.closed)
        self.assertTrue(all(cursor.closed for cursor in connection.cursors))


if __name__ == "__main__":
    unittest.main()
