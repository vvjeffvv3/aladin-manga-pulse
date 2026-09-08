from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from dashboard.service import owned_series_service


class OwnedSeriesServiceTests(SimpleTestCase):
    def test_parse_volume_no_handles_single_volume_and_ranges(self):
        """권수 문자열과 권수 범위에서 마지막 권수를 추출"""
        cases = (
            (None, None),
            ("", None),
            ("15권", 15),
            ("1~3 세트", 3),
            ("3-1", 3),
            ("특장판 7", 7),
        )

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    owned_series_service.parse_volume_no(value),
                    expected,
                )

    @patch.object(owned_series_service, "get_series_volume_values")
    def test_get_local_latest_volume_uses_largest_numeric_volume(
        self,
        get_series_volume_values,
    ):
        """DB에 있는 시리즈 권수 중 가장 큰 숫자를 최신 권수로 선택"""
        get_series_volume_values.return_value = [
            "1",
            "10",
            "특장판 8",
            "미정",
        ]

        result = owned_series_service.get_local_latest_volume(101)

        self.assertEqual(result, 10)
        get_series_volume_values.assert_called_once_with(101)

    @patch.object(owned_series_service, "get_series_volume_values_map")
    def test_get_latest_volume_map_skips_unparseable_values(
        self,
        get_series_volume_values_map,
    ):
        """시리즈별 최신 권수 계산에서 숫자가 아닌 값을 제외"""
        get_series_volume_values_map.return_value = {
            101: ["1", "3"],
            102: ["미정"],
            103: ["2~4"],
        }

        result = owned_series_service.get_latest_volume_map({101, 102, 103})

        self.assertEqual(result, {101: 3, 103: 4})
        get_series_volume_values_map.assert_called_once_with({101, 102, 103})

    @patch.object(owned_series_service, "get_local_latest_volume", return_value=5)
    def test_decorate_owned_record_calculates_missing_volumes_and_progress(
        self,
        get_local_latest_volume,
    ):
        """보유 권수·전체 권수·미보유 권수·수집률을 계산"""
        record = SimpleNamespace(
            series_id=101,
            owned_series_id=1,
            latest_volume_no=5,
            owned_volume_no=0,
            source_url=None,
        )

        result = owned_series_service._decorate_owned_record(
            record,
            stored_owned_volumes=[1, 3, 3, 0],
        )

        self.assertIs(result, record)
        self.assertEqual(record.owned_volume_numbers, [1, 3])
        self.assertEqual(record.available_volume_numbers, [1, 2, 3, 4, 5])
        self.assertEqual(record.missing_volume_numbers, [2, 4, 5])
        self.assertEqual(record.owned_volume_count, 2)
        self.assertEqual(record.total_volume_no, 5)
        self.assertEqual(record.owned_volume_no, 2)
        self.assertEqual(record.progress_percent, 40)
        self.assertEqual(record.remaining_volume_no, 3)
        self.assertFalse(record.is_complete)
        get_local_latest_volume.assert_called_once_with(101)

    @patch.object(owned_series_service, "update_latest_volume")
    @patch.object(owned_series_service, "get_local_latest_volume", return_value=8)
    def test_decorate_owned_record_refreshes_when_local_latest_is_newer(
        self,
        get_local_latest_volume,
        update_latest_volume,
    ):
        """로컬 최신 권수가 더 많으면 시리즈 최신 권수를 갱신"""
        record = SimpleNamespace(
            series_id=101,
            owned_series_id=1,
            latest_volume_no=5,
            owned_volume_no=2,
            source_url="https://www.aladin.co.kr/item/1",
        )

        owned_series_service._decorate_owned_record(record)

        self.assertEqual(record.latest_volume_no, 8)
        self.assertEqual(record.owned_volume_numbers, [1, 2])
        self.assertEqual(record.missing_volume_numbers, [3, 4, 5, 6, 7, 8])
        update_latest_volume.assert_called_once_with(
            1,
            latest_volume_no=8,
            source_url="https://www.aladin.co.kr/item/1",
        )
        get_local_latest_volume.assert_called_once_with(101)

    def test_build_owned_folder_group_summarizes_child_series(self):
        """폴더 안 시리즈의 권수·미보유 권수·수집률을 합산"""
        records = [
            SimpleNamespace(
                total_volume_no=3,
                owned_volume_count=2,
                missing_volume_numbers=[2],
            ),
            SimpleNamespace(
                total_volume_no=5,
                owned_volume_count=4,
                missing_volume_numbers=[5],
            ),
        ]

        result = owned_series_service._build_owned_folder_group(
            7,
            "주술회전",
            records,
        )

        self.assertEqual(result["folder_id"], 7)
        self.assertEqual(result["folder_name"], "주술회전")
        self.assertEqual(result["items"], records)
        self.assertEqual(result["series_count"], 2)
        self.assertEqual(result["owned_volume_count"], 6)
        self.assertEqual(result["total_volume_no"], 8)
        self.assertEqual(result["missing_volume_count"], 2)
        self.assertEqual(result["progress_percent"], 75)

    def test_clean_folder_name_normalizes_and_validates_name(self):
        """폴더 이름의 공백을 정리하고 빈 이름·긴 이름을 거부"""
        self.assertEqual(
            owned_series_service._clean_folder_name("  주술회전   본편  "),
            "주술회전 본편",
        )

        with self.assertRaisesRegex(ValueError, "폴더 이름을 입력"):
            owned_series_service._clean_folder_name("   ")

        with self.assertRaisesRegex(ValueError, "100자 이내"):
            owned_series_service._clean_folder_name("가" * 101)

    @patch.object(owned_series_service, "search_series")
    @patch.object(owned_series_service, "get_owned_series_position_map")
    @patch.object(owned_series_service, "get_owned_series_folder_map")
    @patch.object(owned_series_service, "get_owned_folders")
    @patch.object(owned_series_service, "get_owned_volume_map")
    @patch.object(owned_series_service, "get_owned_series_records")
    @patch.object(owned_series_service, "get_local_latest_volume")
    def test_get_owned_series_dashboard_separates_owned_interest_and_folders(
        self,
        get_local_latest_volume,
        get_owned_series_records,
        get_owned_volume_map,
        get_owned_folders,
        get_owned_series_folder_map,
        get_owned_series_position_map,
        search_series,
    ):
        """보유목록·관심상품을 분리하고 폴더별 요약을 구성"""
        owned_record = SimpleNamespace(
            owned_series_id=1,
            series_id=101,
            series=SimpleNamespace(series_name="주술회전"),
            latest_volume_no=3,
            owned_volume_no=0,
            source_url=None,
        )
        interest_record = SimpleNamespace(
            owned_series_id=2,
            series_id=102,
            series=SimpleNamespace(series_name="주술회전 모듈로"),
            latest_volume_no=5,
            owned_volume_no=0,
            source_url=None,
        )
        folder = SimpleNamespace(folder_id=7, folder_name="주술회전")
        search_result = SimpleNamespace(series_id=102)

        get_owned_series_records.return_value = [owned_record, interest_record]
        get_owned_volume_map.return_value = {1: [1, 3], 2: []}
        get_local_latest_volume.side_effect = {101: 3, 102: 5}.get
        get_owned_folders.return_value = [folder]
        get_owned_series_folder_map.return_value = {1: 7}
        get_owned_series_position_map.return_value = {1: 0}
        search_series.return_value = [search_result]

        result = owned_series_service.get_owned_series_dashboard("주술")

        self.assertEqual(result["owned_series"], [owned_record])
        self.assertEqual(result["interest_series"], [interest_record])
        self.assertEqual(result["owned_folders"], [folder])
        self.assertEqual(result["series_results"], [search_result])
        self.assertEqual(owned_record.folder_id, 7)
        self.assertEqual(owned_record.position_order, 0)
        self.assertEqual(owned_record.missing_volume_numbers, [2])
        self.assertTrue(search_result.is_interested)
        self.assertFalse(search_result.is_owned)
        self.assertEqual(search_result.latest_volume_no, 5)

        groups = result["owned_folder_groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["folder_name"], "주술회전")
        self.assertEqual(groups[0]["series_count"], 1)
        self.assertEqual(groups[0]["owned_volume_count"], 2)
        self.assertEqual(groups[0]["total_volume_no"], 3)
        self.assertEqual(groups[0]["missing_volume_count"], 1)
        self.assertEqual(groups[0]["progress_percent"], 67)
        search_series.assert_called_once_with("주술")

    @patch.object(owned_series_service, "replace_owned_volumes", return_value=True)
    def test_save_owned_volumes_normalizes_selected_values(self, replace_owned_volumes):
        """보유 권수 선택값을 중복 제거·정렬한 뒤 저장"""
        save_owned_volumes = owned_series_service.save_owned_volumes.__wrapped__

        result = save_owned_volumes(1, ["3", "1", "3"])

        self.assertEqual(result, 2)
        replace_owned_volumes.assert_called_once_with(1, [1, 3])

    @patch.object(owned_series_service, "replace_owned_volumes")
    def test_save_owned_volumes_rejects_zero_or_invalid_values(
        self,
        replace_owned_volumes,
    ):
        """잘못된 보유 권수 선택값을 저장하지 않고 오류 처리"""
        save_owned_volumes = owned_series_service.save_owned_volumes.__wrapped__

        with self.assertRaisesRegex(ValueError, "1권 이상"):
            save_owned_volumes(1, ["0"])

        with self.assertRaisesRegex(ValueError, "올바르지 않습니다"):
            save_owned_volumes(1, ["잘못된값"])

        replace_owned_volumes.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()
