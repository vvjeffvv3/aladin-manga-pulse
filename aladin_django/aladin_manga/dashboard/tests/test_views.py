import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import SimpleTestCase
from django.urls import reverse

from dashboard.presentation import views


class DashboardViewTests(SimpleTestCase):
    """Presentation 계층이 Service 결과를 화면과 응답으로 연결하는지 검증한다."""

    @staticmethod
    def _message_texts(response):
        return [str(message) for message in response.wsgi_request._messages]

    def test_home_renders_dashboard_template(self):
        """홈 화면이 대시보드 템플릿과 Service 결과를 사용"""
        latest_snapshot = datetime(2026, 9, 8, 9, 0)
        context = {
            "latest_snapshot": latest_snapshot,
            "previous_snapshot": None,
            "books": [],
            "series": [],
        }

        with patch.object(views, "get_home_dashboard", return_value=context) as get_dashboard:
            response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/home.html")
        self.assertContains(response, "오늘의 인기 만화")
        get_dashboard.assert_called_once_with()

    def test_search_view_selects_requested_snapshot_and_passes_filters(self):
        """검색 화면이 스냅샷·검색어·정렬 조건을 Service에 전달"""
        first_snapshot = datetime(2026, 9, 7, 9, 0)
        selected_snapshot = datetime(2026, 9, 8, 9, 0)
        page_obj = SimpleNamespace()
        service_result = {"page_obj": page_obj}

        with patch.object(
            views,
            "get_snapshot_times",
            return_value=[first_snapshot, selected_snapshot],
        ), patch.object(
            views,
            "get_search_result",
            return_value=service_result,
        ) as get_search_result, patch.object(
            views,
            "render",
            return_value=HttpResponse("rendered"),
        ) as render:
            response = self.client.get(
                reverse("dashboard:search"),
                {
                    "snapshot": selected_snapshot.isoformat(),
                    "keyword": "주술회전",
                    "field": "title",
                    "sort": "rating",
                    "direction": "desc",
                    "page": "2",
                },
            )

        self.assertEqual(response.status_code, 200)
        context = render.call_args.args[2]
        self.assertEqual(context["selected_snapshot"], selected_snapshot)
        self.assertEqual(context["keyword"], "주술회전")
        self.assertEqual(context["search_field"], "title")
        self.assertEqual(context["sort_by"], "rating")
        self.assertEqual(context["direction"], "desc")
        self.assertIs(context["page_obj"], page_obj)
        get_search_result.assert_called_once_with(
            snapshot_time=selected_snapshot,
            keyword="주술회전",
            search_field="title",
            sort_by="rating",
            direction="desc",
            page_number="2",
        )

    def test_search_view_falls_back_from_invalid_snapshot(self):
        """잘못된 스냅샷을 요청하면 가장 최근 목록의 첫 항목을 사용"""
        snapshot = datetime(2026, 9, 8, 9, 0)

        with patch.object(views, "get_snapshot_times", return_value=[snapshot]), patch.object(
            views,
            "get_search_result",
            return_value={"page_obj": SimpleNamespace()},
        ) as get_search_result, patch.object(
            views,
            "render",
            return_value=HttpResponse("rendered"),
        ) as render:
            response = self.client.get(
                reverse("dashboard:search"),
                {"snapshot": "not-a-datetime"},
            )

        self.assertEqual(response.status_code, 200)
        context = render.call_args.args[2]
        self.assertEqual(context["selected_snapshot"], snapshot)
        get_search_result.assert_called_once()
        self.assertEqual(
            get_search_result.call_args.kwargs["snapshot_time"],
            snapshot,
        )

    def test_search_view_without_snapshots_skips_search_service(self):
        """수집 스냅샷이 없으면 빈 화면 상태로 렌더링"""
        with patch.object(views, "get_snapshot_times", return_value=[]), patch.object(
            views,
            "get_search_result",
        ) as get_search_result, patch.object(
            views,
            "render",
            return_value=HttpResponse("rendered"),
        ) as render:
            response = self.client.get(reverse("dashboard:search"))

        self.assertEqual(response.status_code, 200)
        context = render.call_args.args[2]
        self.assertIsNone(context["selected_snapshot"])
        self.assertIsNone(context["page_obj"])
        get_search_result.assert_not_called()

    def test_search_template_exposes_price_sort_option(self):
        """검색 화면에 가격 정렬 선택지를 표시"""
        with patch.object(views, "get_snapshot_times", return_value=[]), patch.object(
            views,
            "get_search_result",
        ) as get_search_result:
            response = self.client.get(reverse("dashboard:search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="price"')
        get_search_result.assert_not_called()

    def test_collection_dashboards_pass_keyword_to_service(self):
        """보유목록·관심상품 화면이 입력 키워드를 공통 Service에 전달"""
        for route_name, template_name in (
            ("dashboard:owned_series", "dashboard/owned_series.html"),
            ("dashboard:interest_series", "dashboard/interest_series.html"),
        ):
            with self.subTest(route_name=route_name), patch.object(
                views,
                "get_owned_series_dashboard",
                return_value={"series_keyword": "주술"},
            ) as get_dashboard, patch.object(
                views,
                "render",
                return_value=HttpResponse("rendered"),
            ) as render:
                response = self.client.get(
                    reverse(route_name),
                    {"keyword": "  주술  "},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(render.call_args.args[1], template_name)
            self.assertEqual(render.call_args.args[2]["series_keyword"], "주술")
            get_dashboard.assert_called_once_with(keyword="주술")

    def test_add_book_to_owned_redirects_to_safe_next_url(self):
        """도서 보유 추가 성공 시 안전한 next 주소로 이동하고 성공 메시지를 표시"""
        with patch.object(views, "add_book_to_owned") as add_book:
            response = self.client.post(
                reverse("dashboard:add_book_to_owned", args=["A-100"]),
                {"next": "/search/"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/search/")
        add_book.assert_called_once_with("A-100")
        self.assertIn("보유 목록에 추가했습니다", self._message_texts(response)[0])

    def test_add_book_to_interest_handles_service_error(self):
        """관심상품 추가 실패 시 오류 페이지 대신 메시지와 목록 화면으로 처리"""
        with patch.object(
            views,
            "add_book_to_interest",
            side_effect=ValueError("이미 관심상품에 있습니다."),
        ) as add_book:
            response = self.client.post(
                reverse("dashboard:add_book_to_interest", args=["A-200"]),
                {"next": "/search/"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/search/")
        add_book.assert_called_once_with("A-200")
        self.assertIn("이미 관심상품에 있습니다", self._message_texts(response)[0])

    def test_collection_post_rejects_get_requests(self):
        """등록·수정용 POST 전용 주소가 GET 요청을 허용하지 않음"""
        with patch.object(views, "add_book_to_owned") as add_book:
            response = self.client.get(
                reverse("dashboard:add_book_to_owned", args=["A-100"])
            )

        self.assertEqual(response.status_code, 405)
        add_book.assert_not_called()

    def test_add_owned_series_parses_volume_and_folder(self):
        """보유 시리즈 추가 요청에서 보유 권수와 폴더 번호를 정수로 변환"""
        with patch.object(views, "add_owned_series_by_id") as add_series:
            response = self.client.post(
                reverse("dashboard:add_owned_series"),
                {
                    "series_id": "12",
                    "owned_volume_no": "3",
                    "folder_id": "7",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/owned-series/")
        add_series.assert_called_once_with(12, 3, 7)
        self.assertIn("보유 목록에 추가했습니다", self._message_texts(response)[0])

    def test_save_owned_selection_passes_multiple_volumes(self):
        """보유 권수 체크박스 저장 시 여러 권과 폴더를 Service에 전달"""
        with patch.object(
            views,
            "save_owned_series_selection",
            return_value=2,
        ) as save_selection:
            response = self.client.post(
                reverse("dashboard:update_owned_series_volume", args=[5]),
                {
                    "owned_selection": "1",
                    "owned_volumes": ["1", "3"],
                    "folder_id": "4",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/owned-series/")
        save_selection.assert_called_once_with(
            5,
            ["1", "3"],
            4,
            update_folder=True,
        )
        self.assertIn("2권의 보유 상태를 저장했습니다", self._message_texts(response)[0])

    def test_reorder_owned_folders_accepts_valid_json(self):
        """폴더 정렬 API가 정상 JSON을 Service에 전달하고 성공 응답을 반환"""
        with patch.object(views, "reorder_owned_folders") as reorder:
            response = self.client.post(
                reverse("dashboard:reorder_owned_folders"),
                data=json.dumps({"folder_ids": [3, 1, 2]}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True})
        reorder.assert_called_once_with([3, 1, 2])

    def test_reorder_owned_folders_rejects_invalid_json(self):
        """폴더 정렬 API가 잘못된 JSON을 400 응답으로 처리"""
        with patch.object(views, "reorder_owned_folders") as reorder:
            response = self.client.post(
                reverse("dashboard:reorder_owned_folders"),
                data="{",
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {"ok": False, "message": "정렬 요청 형식이 올바르지 않습니다."},
        )
        reorder.assert_not_called()

    def test_reorder_owned_series_passes_optional_folder(self):
        """시리즈 정렬 API가 미분류 폴더와 이동 대상 정보를 전달"""
        payload = {
            "folder_id": None,
            "owned_series_ids": [9, 5],
            "moved_owned_series_id": 5,
        }

        with patch.object(views, "reorder_owned_series") as reorder:
            response = self.client.post(
                reverse("dashboard:reorder_owned_series"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True})
        reorder.assert_called_once_with(None, [9, 5], 5)

    def test_external_next_url_is_rejected(self):
        """외부 next 주소는 차단하고 기본 화면으로 이동"""
        with patch.object(views, "add_book_to_owned"):
            response = self.client.post(
                reverse("dashboard:add_book_to_owned", args=["A-300"]),
                {"next": "https://malicious.example/steal"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")


if __name__ == "__main__":
    import unittest

    unittest.main()
