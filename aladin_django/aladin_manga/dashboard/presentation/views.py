import json
from datetime import datetime

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from dashboard.repository.aladin_repository import AladinLookupError
from dashboard.repository.book_repository import get_snapshot_times
from dashboard.service.dashboard_service import get_home_dashboard
from dashboard.service.owned_series_service import (
    add_book_to_interest,
    add_book_to_owned,
    add_owned_series_by_id,
    add_owned_series_from_aladin,
    add_interest_series_by_id,
    add_interest_series_from_aladin,
    create_owned_folder,
    delete_owned_folder,
    delete_owned_series,
    get_owned_series_dashboard,
    move_interest_to_owned,
    reorder_owned_folders,
    reorder_owned_series,
    rename_owned_folder,
    refresh_owned_series,
    save_owned_volume,
    save_owned_series_selection,
)
from dashboard.service.search_service import get_search_result


def home(request):
    context = get_home_dashboard()
    return render(request, "dashboard/home.html", context)


def _collection_redirect(request, fallback="dashboard:home"):
    next_url = request.POST.get("next", "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback)


def _optional_folder_id(value: str | None) -> int | None:
    if value is None:
        return None

    value = str(value).strip()
    if not value:
        return None

    folder_id = int(value)
    if folder_id < 1:
        raise ValueError("폴더를 다시 선택해 주세요.")
    return folder_id


def search_dashboard(request):
    snapshot_times = list(get_snapshot_times())

    selected_snapshot = None
    snapshot_value = request.GET.get("snapshot", "")

    if snapshot_value:
        try:
            selected_snapshot = datetime.fromisoformat(snapshot_value)
        except ValueError:
            selected_snapshot = None

    if selected_snapshot not in snapshot_times:
        selected_snapshot = snapshot_times[0] if snapshot_times else None

    context = {
        "snapshot_times": snapshot_times,
        "selected_snapshot": selected_snapshot,
        "page_obj": None,
        "keyword": request.GET.get("keyword", ""),
        "search_field": request.GET.get("field", "all"),
        "sort_by": request.GET.get("sort", "rank"),
        "direction": request.GET.get("direction", "asc"),
    }

    if selected_snapshot is not None:
        context.update(
            get_search_result(
                snapshot_time=selected_snapshot,
                keyword=context["keyword"],
                search_field=context["search_field"],
                sort_by=context["sort_by"],
                direction=context["direction"],
                page_number=request.GET.get("page", 1),
            )
        )

    return render(request, "dashboard/search.html", context)


@require_POST
def add_book_to_owned_view(request, item_id: str):
    try:
        add_book_to_owned(item_id)
        messages.success(
            request,
            "보유 목록에 추가했습니다. 보유 권수는 마이페이지에서 수정할 수 있어요.",
        )
    except (ObjectDoesNotExist, ValueError, IntegrityError) as exc:
        messages.error(request, str(exc) or "보유 목록에 추가하지 못했습니다.")
    return _collection_redirect(request)


@require_POST
def add_book_to_interest_view(request, item_id: str):
    try:
        add_book_to_interest(item_id)
        messages.success(request, "관심상품에 추가했습니다.")
    except (ObjectDoesNotExist, ValueError, IntegrityError) as exc:
        messages.error(request, str(exc) or "관심상품에 추가하지 못했습니다.")
    return _collection_redirect(request)


def owned_series_dashboard(request):
    keyword = request.GET.get("keyword", "").strip()
    context = get_owned_series_dashboard(keyword=keyword)
    return render(request, "dashboard/owned_series.html", context)


def interest_series_dashboard(request):
    keyword = request.GET.get("keyword", "").strip()
    context = get_owned_series_dashboard(keyword=keyword)
    return render(request, "dashboard/interest_series.html", context)


@require_POST
def add_interest_series(request):
    series_id = request.POST.get("series_id", "")
    try:
        add_interest_series_by_id(int(series_id))
        messages.success(request, "관심상품에 추가했습니다.")
    except (TypeError, ValueError, IntegrityError):
        messages.error(request, "추가할 시리즈를 다시 선택해 주세요.")
    return _collection_redirect(request, "dashboard:interest_series")


@require_POST
def add_interest_series_external(request):
    query = request.POST.get("aladin_query", "").strip()
    try:
        add_interest_series_from_aladin(query)
        messages.success(request, "알라딘에서 시리즈를 찾아 관심상품에 추가했습니다.")
    except (AladinLookupError, ValueError) as exc:
        messages.error(request, str(exc))
    return _collection_redirect(request, "dashboard:interest_series")


@require_POST
def add_owned_series(request):
    series_id = request.POST.get("series_id", "")
    try:
        owned_volume_no = int(request.POST.get("owned_volume_no", "1"))
        folder_id = _optional_folder_id(request.POST.get("folder_id"))
        add_owned_series_by_id(int(series_id), owned_volume_no, folder_id)
        messages.success(request, "보유 목록에 추가했습니다.")
    except (TypeError, ValueError, IntegrityError) as exc:
        messages.error(request, str(exc) or "추가할 시리즈를 다시 선택해 주세요.")
    return _collection_redirect(request, "dashboard:owned_series")


@require_POST
def add_owned_series_external(request):
    query = request.POST.get("aladin_query", "").strip()
    try:
        owned_volume_no = int(request.POST.get("owned_volume_no", "1"))
        folder_id = _optional_folder_id(request.POST.get("folder_id"))
        add_owned_series_from_aladin(query, owned_volume_no, folder_id)
        messages.success(request, "알라딘에서 시리즈를 찾아 보유 목록에 추가했습니다.")
    except (AladinLookupError, TypeError, ValueError, IntegrityError) as exc:
        messages.error(request, str(exc) or "시리즈를 보유 목록에 추가하지 못했습니다.")
    return _collection_redirect(request, "dashboard:owned_series")


@require_POST
def update_owned_series_volume(request, owned_series_id: int):
    try:
        if "owned_selection" in request.POST:
            folder_id = _optional_folder_id(request.POST.get("folder_id"))
            owned_count = save_owned_series_selection(
                owned_series_id,
                request.POST.getlist("owned_volumes"),
                folder_id,
                update_folder=True,
            )
            if owned_count:
                messages.success(request, f"{owned_count}권의 보유 상태를 저장했습니다.")
            else:
                messages.info(
                    request,
                    "선택한 권수가 없어 관심상품으로 이동했습니다.",
                )
        else:
            save_owned_volume(
                owned_series_id,
                request.POST.get("owned_volume_no", ""),
            )
            messages.success(request, "보유 권수를 저장했습니다.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return _collection_redirect(request, "dashboard:owned_series")


@require_POST
def create_owned_folder_view(request):
    try:
        create_owned_folder(request.POST.get("folder_name", ""))
        messages.success(request, "폴더를 만들었습니다.")
    except (IntegrityError, ValueError) as exc:
        messages.error(request, str(exc) or "같은 이름의 폴더가 이미 있습니다.")
    return _collection_redirect(request, "dashboard:owned_series")


@require_POST
def rename_owned_folder_view(request, folder_id: int):
    try:
        rename_owned_folder(folder_id, request.POST.get("folder_name", ""))
        messages.success(request, "폴더 이름을 변경했습니다.")
    except (IntegrityError, ValueError) as exc:
        messages.error(request, str(exc) or "폴더 이름을 변경하지 못했습니다.")
    return _collection_redirect(request, "dashboard:owned_series")


@require_POST
def delete_owned_folder_view(request, folder_id: int):
    try:
        delete_owned_folder(folder_id)
        messages.success(request, "폴더를 삭제했습니다. 시리즈는 미분류로 남아 있습니다.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return _collection_redirect(request, "dashboard:owned_series")


def _json_request_payload(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("정렬 요청 형식이 올바르지 않습니다.") from exc

    if not isinstance(payload, dict):
        raise ValueError("정렬 요청 형식이 올바르지 않습니다.")
    return payload


@require_POST
def reorder_owned_folders_view(request):
    try:
        payload = _json_request_payload(request)
        reorder_owned_folders(payload.get("folder_ids", []))
    except (AttributeError, TypeError, ValueError) as exc:
        return JsonResponse(
            {"ok": False, "message": str(exc)},
            status=400,
        )
    return JsonResponse({"ok": True})


@require_POST
def reorder_owned_series_view(request):
    try:
        payload = _json_request_payload(request)
        folder_id = _optional_folder_id(payload.get("folder_id"))
        reorder_owned_series(
            folder_id,
            payload.get("owned_series_ids", []),
            payload.get("moved_owned_series_id"),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return JsonResponse(
            {"ok": False, "message": str(exc)},
            status=400,
        )
    return JsonResponse({"ok": True})


@require_POST
def move_interest_to_owned_view(request, owned_series_id: int):
    try:
        move_interest_to_owned(owned_series_id)
        messages.success(
            request,
            "보유 목록으로 옮겼습니다. 마이페이지에서 실제 보유 권수를 체크해 주세요.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    return _collection_redirect(request, "dashboard:interest_series")


@require_POST
def refresh_owned_series_view(request, owned_series_id: int):
    try:
        latest = refresh_owned_series(owned_series_id)
        if latest is None:
            messages.info(request, "최신 권수를 확인하지 못했습니다.")
        else:
            messages.success(request, f"최신 관측 권수를 {latest}권으로 갱신했습니다.")
    except (AladinLookupError, ValueError) as exc:
        messages.error(request, str(exc))
    return _collection_redirect(request, "dashboard:owned_series")


@require_POST
def remove_owned_series_view(request, owned_series_id: int):
    delete_owned_series(owned_series_id)
    messages.success(request, "목록에서 삭제했습니다.")
    return _collection_redirect(request, "dashboard:owned_series")
