import unittest

from gold_transform import aggregate_series, transform_to_gold


def make_row(
    item_id: str,
    title: str,
    series_name: str,
    vol_no: str,
    collected_at: str,
    rank: int,
    sales_point: int,
) -> dict[str, str]:
    return {
        "item_id": item_id,
        "title": title,
        "series_name": series_name,
        "vol_no": vol_no,
        "rank": str(rank),
        "sales_point": str(sales_point),
        "collected_at": collected_at,
    }


class GoldTransformTests(unittest.TestCase):
    def test_transform_calculates_changes_new_items_and_out_items(self):
        """순위·판매지수 변화, 신규 진입, 이탈 계산"""
        rows = [
            make_row(
                "a",
                "주술회전 15",
                "주술회전",
                "15",
                "2026-09-07T09:00:00+09:00",
                10,
                100,
            ),
            make_row(
                "b",
                "원피스 1",
                "원피스",
                "1",
                "2026-09-07T09:00:00+09:00",
                20,
                50,
            ),
            make_row(
                "a",
                "주술회전 15",
                "주술회전",
                "15",
                "2026-09-08T09:00:00+09:00",
                7,
                130,
            ),
            make_row(
                "c",
                "슬램덩크 1",
                "슬램덩크",
                "1",
                "2026-09-08T09:00:00+09:00",
                5,
                200,
            ),
        ]

        result = transform_to_gold(rows)

        current_a = next(
            row
            for row in result
            if row["item_id"] == "a" and row["collected_at"].startswith("2026-09-08")
        )
        new_c = next(row for row in result if row["item_id"] == "c")
        out_b = next(
            row
            for row in result
            if row["item_id"] == "b" and row["is_out"] == "1"
        )

        self.assertEqual(current_a["previous_rank"], "10")
        self.assertEqual(current_a["rank_change"], "3")
        self.assertEqual(current_a["previous_sales_point"], "100")
        self.assertEqual(current_a["sales_point_change"], "30")
        self.assertEqual(current_a["is_new"], "0")
        self.assertEqual(current_a["is_out"], "0")

        self.assertEqual(new_c["is_new"], "1")
        self.assertEqual(new_c["is_out"], "0")

        self.assertEqual(out_b["collected_at"], "2026-09-08T09:00:00+09:00")
        self.assertEqual(out_b["rank"], "")
        self.assertEqual(out_b["sales_point"], "")
        self.assertEqual(out_b["previous_rank"], "20")
        self.assertEqual(out_b["is_out"], "1")

    def test_aggregate_series_counts_volumes_and_sorts_volume_numbers(self):
        """시리즈별 권수와 권수 목록 집계"""
        rows = [
            make_row(
                "a",
                "주술회전 10",
                "주술회전",
                "10",
                "2026-09-08T09:00:00+09:00",
                10,
                100,
            ),
            make_row(
                "b",
                "주술회전 2",
                "주술회전",
                "2",
                "2026-09-08T09:00:00+09:00",
                20,
                200,
            ),
            make_row(
                "c",
                "원피스 1",
                "원피스",
                "1",
                "2026-09-08T09:00:00+09:00",
                1,
                500,
            ),
        ]
        for row in rows:
            row["is_out"] = "0"

        result = aggregate_series(rows)
        jujutsu = next(
            row for row in result if row["series_name"] == "주술회전"
        )

        self.assertEqual(jujutsu["series_rank"], "1")
        self.assertEqual(jujutsu["volume_count"], "2")
        self.assertEqual(jujutsu["volume_numbers"], "2, 10")
        self.assertEqual(jujutsu["best_rank"], "10")
        self.assertEqual(jujutsu["avg_rank"], "15.0")
        self.assertEqual(jujutsu["total_sales_point"], "300")


if __name__ == "__main__":
    unittest.main()
