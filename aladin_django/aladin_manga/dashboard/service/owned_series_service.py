import re

from django.db import transaction
from django.utils import timezone

from dashboard.repository.aladin_repository import lookup_aladin_series
from dashboard.repository.owned_series_repository import (
    add_owned_series_record,
    create_owned_folder as create_owned_folder_record,
    get_book,
    get_collection_status_map,
    get_or_create_series,
    get_owned_folders,
    get_owned_series_record,
    get_owned_series_folder_map,
    get_owned_series_position_map,
    get_owned_series_records,
    get_owned_volume_map,
    get_series_volume_values,
    get_series_volume_values_map,
    remove_owned_folder,
    remove_owned_series,
    reorder_owned_folders as reorder_owned_folder_records,
    reorder_owned_series as reorder_owned_series_records,
    replace_owned_volumes,
    search_series,
    set_owned_series_folder,
    update_latest_volume,
    update_owned_folder_name,
)


def parse_volume_no(value) -> int | None:
    if value is None:
        return None

    text = str(value).strip()
    range_match = re.search(r"(\d+)\s*[~～-]\s*(\d+)", text)
    if range_match:
        return max(int(range_match.group(1)), int(range_match.group(2)))

    match = re.search(r"(?<!\d)(\d+)", text)
    return int(match.group(1)) if match else None


def get_local_latest_volume(series_id: int) -> int | None:
    volumes = [
        parsed
        for value in get_series_volume_values(series_id)
        if (parsed := parse_volume_no(value)) is not None
    ]
    return max(volumes) if volumes else None


def get_latest_volume_map(series_ids: set[int]) -> dict[int, int]:
    values_map = get_series_volume_values_map(series_ids)
    latest_by_series: dict[int, int] = {}
    for series_id, values in values_map.items():
        parsed_values = [
            parsed
            for value in values
            if (parsed := parse_volume_no(value)) is not None
        ]
        if parsed_values:
            latest_by_series[series_id] = max(parsed_values)
    return latest_by_series


def decorate_book_collection_status(items):
    """도서 목록에 보유 목록·관심 항목 버튼 상태를 붙인다."""
    series_ids = {
        item.book.series_id
        for item in items
        if item.book.series_id is not None
    }
    status_map = get_collection_status_map(series_ids)

    for item in items:
        status = status_map.get(item.book.series_id)
        item.is_owned = status == "owned"
        item.is_interested = status == "interest"

    return items


def _decorate_owned_record(record, stored_owned_volumes: list[int] | None = None):
    local_latest = get_local_latest_volume(record.series_id)
    stored_latest = record.latest_volume_no
    if local_latest is not None and (
        stored_latest is None or local_latest > stored_latest
    ):
        update_latest_volume(
            record.owned_series_id,
            latest_volume_no=local_latest,
            source_url=record.source_url,
        )
        record.latest_volume_no = local_latest
        record.latest_checked_at = timezone.now()

    owned = record.owned_volume_no or 0
    owned_volumes = sorted(
        {
            int(volume_no)
            for volume_no in (stored_owned_volumes or [])
            if int(volume_no) > 0
        }
    )
    if not owned_volumes and owned > 0:
        # 체크 테이블 도입 전 데이터는 기존 보유 권수를 1권부터 보유한 것으로 해석한다.
        owned_volumes = list(range(1, owned + 1))

    latest = record.latest_volume_no
    if owned_volumes and (latest is None or max(owned_volumes) > latest):
        latest = max(owned_volumes)

    owned_set = set(owned_volumes)
    available_volumes = list(range(1, latest + 1)) if latest else []
    owned = len(owned_volumes)
    record.owned_volume_numbers = owned_volumes
    record.available_volume_numbers = available_volumes
    record.missing_volume_numbers = [
        volume_no
        for volume_no in available_volumes
        if volume_no not in owned_set
    ]
    record.owned_volume_count = owned
    record.total_volume_no = latest
    record.owned_volume_no = owned
    record.progress_percent = (
        min(100, round(owned / latest * 100)) if latest else 0
    )
    record.remaining_volume_no = max(latest - owned, 0) if latest else None
    record.is_complete = bool(latest and owned >= latest)
    return record


def get_owned_series_dashboard(keyword: str = "") -> dict:
    records = list(get_owned_series_records())
    volume_map = get_owned_volume_map(
        {record.owned_series_id for record in records}
    )
    tracked_records = [
        _decorate_owned_record(record, volume_map.get(record.owned_series_id))
        for record in records
    ]

    owned_records = [
        record
        for record in tracked_records
        if record.owned_volume_count > 0
    ]
    interest_records = [
        record
        for record in tracked_records
        if record.owned_volume_count == 0
    ]

    folders = list(get_owned_folders())
    folder_map = get_owned_series_folder_map(
        {record.owned_series_id for record in owned_records}
    )
    position_map = get_owned_series_position_map(
        {record.owned_series_id for record in owned_records}
    )
    for record in owned_records:
        record.folder_id = folder_map.get(record.owned_series_id)
        record.position_order = position_map.get(record.owned_series_id)

    owned_folder_groups = []
    assigned_series_ids: set[int] = set()
    for folder in folders:
        folder_records = [
            record
            for record in owned_records
            if record.folder_id == folder.folder_id
        ]
        folder_records.sort(key=_owned_series_sort_key)
        assigned_series_ids.update(
            record.owned_series_id for record in folder_records
        )
        owned_folder_groups.append(
            _build_owned_folder_group(
                folder.folder_id,
                folder.folder_name,
                folder_records,
            )
        )

    unassigned_records = [
        record
        for record in owned_records
        if record.owned_series_id not in assigned_series_ids
    ]
    unassigned_records.sort(key=_owned_series_sort_key)
    if unassigned_records or not folders:
        owned_folder_groups.append(
            _build_owned_folder_group(
                None,
                "미분류",
                unassigned_records,
            )
        )

    tracked_ids = {record.series_id for record in tracked_records}
    owned_ids = {record.series_id for record in owned_records}
    search_results = list(search_series(keyword)) if keyword else []
    for series in search_results:
        series.is_interested = series.series_id in tracked_ids
        series.is_owned = series.series_id in owned_ids
        series.latest_volume_no = get_local_latest_volume(series.series_id)

    return {
        "owned_series": owned_records,
        "interest_series": interest_records,
        "series_results": search_results,
        "series_keyword": keyword,
        "owned_folders": folders,
        "owned_folder_groups": owned_folder_groups if owned_records or folders else [],
    }


def _build_owned_folder_group(
    folder_id: int | None,
    folder_name: str,
    records: list,
) -> dict:
    total_volume_no = sum(
        record.total_volume_no or 0
        for record in records
    )
    owned_volume_count = sum(
        record.owned_volume_count
        for record in records
    )
    missing_volume_count = sum(
        len(record.missing_volume_numbers)
        for record in records
    )
    return {
        "folder_id": folder_id,
        "folder_name": folder_name,
        "items": records,
        "series_count": len(records),
        "owned_volume_count": owned_volume_count,
        "total_volume_no": total_volume_no,
        "missing_volume_count": missing_volume_count,
        "progress_percent": (
            min(100, round(owned_volume_count / total_volume_no * 100))
            if total_volume_no
            else 0
        ),
    }


def _owned_series_sort_key(record):
    return (
        record.position_order is None,
        record.position_order if record.position_order is not None else 0,
        record.series.series_name.casefold(),
    )


def _clean_folder_name(folder_name: str) -> str:
    cleaned_name = " ".join(str(folder_name or "").split())
    if not cleaned_name:
        raise ValueError("폴더 이름을 입력해 주세요.")
    if len(cleaned_name) > 100:
        raise ValueError("폴더 이름은 100자 이내로 입력해 주세요.")
    return cleaned_name


@transaction.atomic
def create_owned_folder(folder_name: str):
    return create_owned_folder_record(_clean_folder_name(folder_name))


@transaction.atomic
def rename_owned_folder(folder_id: int, folder_name: str) -> None:
    if not update_owned_folder_name(
        folder_id,
        _clean_folder_name(folder_name),
    ):
        raise ValueError("이름을 바꿀 폴더를 찾지 못했습니다.")


@transaction.atomic
def delete_owned_folder(folder_id: int) -> None:
    if not remove_owned_folder(folder_id):
        raise ValueError("삭제할 폴더를 찾지 못했습니다.")


@transaction.atomic
def reorder_owned_folders(folder_ids: list[int] | tuple[int, ...]) -> None:
    try:
        cleaned_ids = [int(folder_id) for folder_id in folder_ids]
    except (TypeError, ValueError) as exc:
        raise ValueError("폴더 순서값이 올바르지 않습니다.") from exc

    reorder_owned_folder_records(cleaned_ids)


@transaction.atomic
def reorder_owned_series(
    folder_id: int | None,
    owned_series_ids: list[int] | tuple[int, ...],
    moved_owned_series_id: int | None = None,
) -> None:
    try:
        cleaned_ids = [int(owned_series_id) for owned_series_id in owned_series_ids]
        moved_id = (
            int(moved_owned_series_id)
            if moved_owned_series_id is not None
            else None
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("시리즈 순서값이 올바르지 않습니다.") from exc

    if moved_id is not None and moved_id not in cleaned_ids:
        raise ValueError("이동한 시리즈가 새 위치에 포함되지 않았습니다.")

    if folder_id is not None and not get_owned_folders().filter(
        folder_id=folder_id,
    ).exists():
        raise ValueError("선택한 폴더를 찾지 못했습니다.")

    owned_ids = set(
        get_owned_series_records()
        .filter(
            owned_series_id__in=cleaned_ids,
            owned_volume_no__gt=0,
        )
        .values_list("owned_series_id", flat=True)
    )
    if owned_ids != set(cleaned_ids):
        raise ValueError("보유 목록에 없는 시리즈가 포함되어 있습니다.")

    folder_map = get_owned_series_folder_map(owned_ids)
    if any(
        owned_series_id != moved_id
        and folder_map.get(owned_series_id) != folder_id
        for owned_series_id in cleaned_ids
    ):
        raise ValueError("같은 폴더 안의 시리즈만 순서를 바꿀 수 있습니다.")

    if moved_id is not None and not set_owned_series_folder(moved_id, folder_id):
        raise ValueError("이동할 시리즈를 찾지 못했습니다.")

    reorder_owned_series_records(cleaned_ids)


@transaction.atomic
def add_book_to_owned(item_id: str):
    """책 목록의 별 버튼으로 해당 시리즈를 보유 목록에 넣는다."""
    book = get_book(item_id)
    if book.series_id is None:
        raise ValueError("시리즈 정보가 없는 도서는 목록에 추가할 수 없습니다.")

    selected_volume = parse_volume_no(book.vol_no) or 1
    local_latest = get_local_latest_volume(book.series_id)
    latest_volume = max(local_latest or 0, selected_volume)
    record, created = add_owned_series_record(
        series_id=book.series_id,
        latest_volume_no=latest_volume,
        owned_volume_no=selected_volume,
    )
    _merge_initial_owned_volumes(
        record.owned_series_id,
        max(selected_volume, record.owned_volume_no or 0),
    )
    return record, created


@transaction.atomic
def add_book_to_interest(item_id: str):
    """책 목록의 하트 버튼으로 해당 시리즈를 관심 항목에 넣는다."""
    book = get_book(item_id)
    if book.series_id is None:
        raise ValueError("시리즈 정보가 없는 도서는 목록에 추가할 수 없습니다.")

    record, created = add_owned_series_record(
        series_id=book.series_id,
        latest_volume_no=get_local_latest_volume(book.series_id),
        owned_volume_no=0,
    )
    replace_owned_volumes(record.owned_series_id, [])
    set_owned_series_folder(record.owned_series_id, None)
    return record, created


@transaction.atomic
def add_interest_series_by_id(series_id: int):
    latest = get_local_latest_volume(series_id)
    record, created = add_owned_series_record(
        series_id=series_id,
        latest_volume_no=latest,
        owned_volume_no=0,
    )
    replace_owned_volumes(record.owned_series_id, [])
    set_owned_series_folder(record.owned_series_id, None)
    return record, created


def add_interest_series_from_aladin(query: str):
    lookup = lookup_aladin_series(query)
    with transaction.atomic():
        series, _ = get_or_create_series(lookup.series_name)
        record, created = add_owned_series_record(
            series_id=series.series_id,
            latest_volume_no=lookup.latest_volume_no,
            source_url=lookup.source_url,
            owned_volume_no=0,
        )
        replace_owned_volumes(record.owned_series_id, [])
        set_owned_series_folder(record.owned_series_id, None)
        return record, created


@transaction.atomic
def add_owned_series_by_id(
    series_id: int,
    owned_volume_no: int = 1,
    folder_id: int | None = None,
):
    """시리즈 검색 결과를 보유 목록에 추가한다."""
    if owned_volume_no < 1:
        raise ValueError("보유 목록에 추가하려면 보유 권수를 1권 이상 입력해 주세요.")

    latest = get_local_latest_volume(series_id)
    latest = max(latest or 0, owned_volume_no)
    record, created = add_owned_series_record(
        series_id=series_id,
        latest_volume_no=latest,
        owned_volume_no=owned_volume_no,
    )
    _merge_initial_owned_volumes(
        record.owned_series_id,
        max(owned_volume_no, record.owned_volume_no or 0),
    )
    _assign_folder_if_requested(record.owned_series_id, folder_id)
    return record, created


def add_owned_series_from_aladin(
    query: str,
    owned_volume_no: int = 1,
    folder_id: int | None = None,
):
    """알라딘 상품 URL·상품번호·ISBN·검색어로 보유 시리즈를 추가한다."""
    if owned_volume_no < 1:
        raise ValueError("보유 목록에 추가하려면 보유 권수를 1권 이상 입력해 주세요.")

    lookup = lookup_aladin_series(query)
    with transaction.atomic():
        series, _ = get_or_create_series(lookup.series_name)
        latest = max(lookup.latest_volume_no or 0, owned_volume_no)
        record, created = add_owned_series_record(
            series_id=series.series_id,
            latest_volume_no=latest,
            source_url=lookup.source_url,
            owned_volume_no=owned_volume_no,
        )
        _merge_initial_owned_volumes(
            record.owned_series_id,
            max(owned_volume_no, record.owned_volume_no or 0),
        )
        _assign_folder_if_requested(record.owned_series_id, folder_id)
        return record, created


def _merge_initial_owned_volumes(
    owned_series_id: int,
    initial_volume_no: int,
) -> None:
    """기존 보유 상태를 유지하면서 초기 권수까지 체크한다."""
    current = set(get_owned_volume_map({owned_series_id}).get(owned_series_id, []))
    current.update(range(1, initial_volume_no + 1))
    if not replace_owned_volumes(owned_series_id, current):
        raise ValueError("보유 목록을 저장할 대상을 찾지 못했습니다.")


def _assign_folder_if_requested(
    owned_series_id: int,
    folder_id: int | None,
) -> None:
    if folder_id is None:
        return
    if not set_owned_series_folder(owned_series_id, folder_id):
        raise ValueError("선택한 폴더를 찾지 못했습니다.")


@transaction.atomic
def save_owned_volumes(
    owned_series_id: int,
    values: list[str] | tuple[str, ...],
) -> int:
    try:
        volume_numbers = sorted({int(value) for value in values})
    except (TypeError, ValueError) as exc:
        raise ValueError("보유 권수 선택값이 올바르지 않습니다.") from exc

    if any(volume_no < 1 for volume_no in volume_numbers):
        raise ValueError("보유 권수는 1권 이상이어야 합니다.")

    if not replace_owned_volumes(owned_series_id, volume_numbers):
        raise ValueError("저장할 보유 목록을 찾지 못했습니다.")
    return len(volume_numbers)


@transaction.atomic
def save_owned_series_selection(
    owned_series_id: int,
    values: list[str] | tuple[str, ...],
    folder_id: int | None = None,
    *,
    update_folder: bool = False,
) -> int:
    owned_count = save_owned_volumes(owned_series_id, values)
    if update_folder and owned_count:
        if not set_owned_series_folder(owned_series_id, folder_id):
            raise ValueError("선택한 폴더를 찾지 못했습니다.")
    elif not owned_count:
        set_owned_series_folder(owned_series_id, None)
    return owned_count


@transaction.atomic
def save_owned_volume(owned_series_id: int, value: str) -> int:
    try:
        owned_volume_no = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("보유 권수는 0 이상의 숫자로 입력해 주세요.") from exc

    if owned_volume_no < 0:
        raise ValueError("보유 권수는 0 이상이어야 합니다.")

    return save_owned_series_selection(
        owned_series_id,
        [str(volume_no) for volume_no in range(1, owned_volume_no + 1)],
    )


@transaction.atomic
def move_interest_to_owned(owned_series_id: int) -> int:
    """관심상품을 보유 목록으로 옮기고 마이페이지에서 권수를 조정하게 한다."""
    return save_owned_series_selection(owned_series_id, ["1"])


def refresh_owned_series(owned_series_id: int):
    record = get_owned_series_record(owned_series_id)
    if record.source_url:
        lookup = lookup_aladin_series(record.source_url)
        latest = lookup.latest_volume_no
        source_url = lookup.source_url
    else:
        latest = get_local_latest_volume(record.series_id)
        source_url = record.source_url

    update_latest_volume(
        record.owned_series_id,
        latest_volume_no=latest,
        source_url=source_url,
        checked_at=timezone.now(),
    )
    return latest


@transaction.atomic
def delete_owned_series(owned_series_id: int) -> None:
    remove_owned_series(owned_series_id)
