import unittest

from daily_snapshot import deduplicate_daily_rows


class DailySnapshotTests(unittest.TestCase):
    def test_keeps_latest_row_per_item_and_date(self):
        """같은 상품이 같은 날짜에 여러 번 들어오면 최신 행만 유지"""
        rows = [
            {
                "item_id": "123",
                "title": "주술회전 15",
                "sales_point": "100",
                "collected_at": "2026-09-08T09:00:00+09:00",
            },
            {
                "item_id": "123",
                "title": "주술회전 15",
                "sales_point": "200",
                "collected_at": "2026-09-08T10:00:00+09:00",
            },
            {
                "item_id": "123",
                "title": "주술회전 15",
                "sales_point": "300",
                "collected_at": "2026-09-09T09:00:00+09:00",
            },
        ]

        result = deduplicate_daily_rows(
            rows,
            identity_fields=("item_id", "title"),
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["sales_point"], "200")
        self.assertEqual(result[1]["sales_point"], "300")

    def test_same_timestamp_keeps_later_row(self):
        """수집 시간이 같으면 나중에 들어온 행 사용"""
        rows = [
            {
                "item_id": "123",
                "sales_point": "100",
                "collected_at": "2026-09-08T10:00:00+09:00",
            },
            {
                "item_id": "123",
                "sales_point": "250",
                "collected_at": "2026-09-08T10:00:00+09:00",
            },
        ]

        result = deduplicate_daily_rows(rows, identity_fields=("item_id",))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sales_point"], "250")

    def test_rejects_row_without_collected_at(self):
        """수집 시간 누락 행 거부"""
        with self.assertRaisesRegex(ValueError, "collected_at"):
            deduplicate_daily_rows(
                [{"item_id": "123"}],
                identity_fields=("item_id",),
            )

    def test_rejects_row_without_identity(self):
        """식별자 누락 행 거부"""
        with self.assertRaisesRegex(ValueError, "식별자"):
            deduplicate_daily_rows(
                [{"collected_at": "2026-09-08T10:00:00+09:00"}],
                identity_fields=("item_id", "title"),
            )


if __name__ == "__main__":
    unittest.main()
