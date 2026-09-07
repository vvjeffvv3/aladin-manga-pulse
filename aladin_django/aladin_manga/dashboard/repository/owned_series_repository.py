from datetime import datetime

from django.db.models import Count, Max, QuerySet
from django.utils import timezone

from dashboard.models import (
    Book,
    OwnedFolder,
    OwnedSeries,
    OwnedSeriesFolder,
    OwnedSeriesPosition,
    OwnedSeriesVolume,
    Series,
)


def get_book(item_id: str) -> Book:
    return Book.objects.select_related("series").get(item_id=item_id)


def search_series(keyword: str, limit: int = 30) -> QuerySet[Series]:
    """현재 DB에 등록된 시리즈를 이름으로 검색한다."""
    queryset = Series.objects.annotate(
        known_volume_count=Count("books", distinct=True),
    )

    keyword = keyword.strip()
    if keyword:
        queryset = queryset.filter(series_name__icontains=keyword)

    return queryset.order_by("series_name")[:limit]


def get_owned_series_records() -> QuerySet[OwnedSeries]:
    return (
        OwnedSeries.objects
        .select_related("series")
        .order_by("series__series_name")
    )


def get_series_volume_values(series_id: int) -> list[str]:
    return list(
        Book.objects
        .filter(series_id=series_id)
        .values_list("vol_no", flat=True)
    )


def get_series_volume_values_map(series_ids: set[int]) -> dict[int, list[str]]:
    if not series_ids:
        return {}

    values_map: dict[int, list[str]] = {}
    rows = (
        Book.objects
        .filter(series_id__in=series_ids)
        .values_list("series_id", "vol_no")
    )
    for series_id, volume_no in rows:
        values_map.setdefault(series_id, []).append(volume_no)
    return values_map


def get_collection_status_map(series_ids: set[int]) -> dict[int, str]:
    """시리즈별 현재 위치를 owned/interest로 반환한다."""
    if not series_ids:
        return {}

    return {
        series_id: "owned" if owned_volume_no > 0 else "interest"
        for series_id, owned_volume_no in (
            OwnedSeries.objects
            .filter(series_id__in=series_ids)
            .values_list("series_id", "owned_volume_no")
        )
    }


def get_owned_volume_map(owned_series_ids: set[int]) -> dict[int, list[int]]:
    """보유 시리즈별로 실제 체크된 권수 목록을 가져온다."""
    if not owned_series_ids:
        return {}

    volume_map: dict[int, list[int]] = {}
    rows = (
        OwnedSeriesVolume.objects
        .filter(owned_series_id__in=owned_series_ids)
        .values_list("owned_series_id", "volume_no")
        .order_by("owned_series_id", "volume_no")
    )
    for owned_series_id, volume_no in rows:
        volume_map.setdefault(owned_series_id, []).append(volume_no)
    return volume_map


def get_owned_folders() -> QuerySet[OwnedFolder]:
    return OwnedFolder.objects.order_by("sort_order", "folder_name")


def get_owned_series_folder_map(
    owned_series_ids: set[int],
) -> dict[int, int]:
    if not owned_series_ids:
        return {}

    return {
        owned_series_id: folder_id
        for owned_series_id, folder_id in (
            OwnedSeriesFolder.objects
            .filter(owned_series_id__in=owned_series_ids)
            .values_list("owned_series_id", "folder_id")
        )
    }


def create_owned_folder(folder_name: str) -> OwnedFolder:
    max_sort_order = (
        OwnedFolder.objects.aggregate(max_sort_order=Max("sort_order"))[
            "max_sort_order"
        ]
        or 0
    )
    now = timezone.now()
    return OwnedFolder.objects.create(
        folder_name=folder_name,
        sort_order=max_sort_order + 1,
        created_at=now,
        updated_at=now,
    )


def update_owned_folder_name(folder_id: int, folder_name: str) -> bool:
    updated = OwnedFolder.objects.filter(folder_id=folder_id).update(
        folder_name=folder_name,
        updated_at=timezone.now(),
    )
    return bool(updated)


def remove_owned_folder(folder_id: int) -> bool:
    deleted, _ = OwnedFolder.objects.filter(folder_id=folder_id).delete()
    return bool(deleted)


def set_owned_series_folder(
    owned_series_id: int,
    folder_id: int | None,
) -> bool:
    if folder_id is None:
        OwnedSeriesFolder.objects.filter(
            owned_series_id=owned_series_id,
        ).delete()
        return True

    if not OwnedFolder.objects.filter(folder_id=folder_id).exists():
        return False

    OwnedSeriesFolder.objects.update_or_create(
        owned_series_id=owned_series_id,
        defaults={"folder_id": folder_id},
    )
    return True


def get_owned_series_position_map(
    owned_series_ids: set[int],
) -> dict[int, int]:
    if not owned_series_ids:
        return {}

    return {
        owned_series_id: sort_order
        for owned_series_id, sort_order in (
            OwnedSeriesPosition.objects
            .filter(owned_series_id__in=owned_series_ids)
            .values_list("owned_series_id", "sort_order")
        )
    }


def reorder_owned_folders(folder_ids: list[int]) -> None:
    if len(folder_ids) != len(set(folder_ids)):
        raise ValueError("폴더 순서값이 중복되었습니다.")

    folders = list(
        OwnedFolder.objects.filter(folder_id__in=folder_ids)
    )
    if len(folders) != len(folder_ids):
        raise ValueError("존재하지 않는 폴더가 포함되어 있습니다.")

    folders_by_id = {folder.folder_id: folder for folder in folders}
    now = timezone.now()
    for sort_order, folder_id in enumerate(folder_ids):
        folder = folders_by_id[folder_id]
        folder.sort_order = sort_order
        folder.updated_at = now

    if folders:
        OwnedFolder.objects.bulk_update(
            folders,
            ["sort_order", "updated_at"],
        )


def reorder_owned_series(owned_series_ids: list[int]) -> None:
    if len(owned_series_ids) != len(set(owned_series_ids)):
        raise ValueError("시리즈 순서값이 중복되었습니다.")

    existing_ids = set(
        OwnedSeries.objects
        .filter(owned_series_id__in=owned_series_ids)
        .values_list("owned_series_id", flat=True)
    )
    if existing_ids != set(owned_series_ids):
        raise ValueError("존재하지 않는 시리즈가 포함되어 있습니다.")

    for sort_order, owned_series_id in enumerate(owned_series_ids):
        OwnedSeriesPosition.objects.update_or_create(
            owned_series_id=owned_series_id,
            defaults={"sort_order": sort_order},
        )


def get_owned_series_record(owned_series_id: int) -> OwnedSeries:
    return OwnedSeries.objects.select_related("series").get(
        owned_series_id=owned_series_id,
    )


def get_or_create_series(series_name: str) -> tuple[Series, bool]:
    return Series.objects.get_or_create(series_name=series_name.strip())


def add_owned_series_record(
    series_id: int,
    latest_volume_no: int | None = None,
    source_url: str | None = None,
    owned_volume_no: int | None = None,
) -> tuple[OwnedSeries, bool]:
    defaults = {
        "latest_volume_no": latest_volume_no,
        "latest_checked_at": timezone.now() if latest_volume_no else None,
        "source_url": source_url,
    }
    if owned_volume_no is not None:
        defaults["owned_volume_no"] = owned_volume_no
    record, created = OwnedSeries.objects.get_or_create(
        series_id=series_id,
        defaults=defaults,
    )

    fields_to_update: list[str] = []
    if not created:
        target_owned_volume = owned_volume_no
        if owned_volume_no is not None and owned_volume_no > 0:
            target_owned_volume = max(
                record.owned_volume_no or 0,
                owned_volume_no,
            )
        if (
            target_owned_volume is not None
            and record.owned_volume_no != target_owned_volume
        ):
            record.owned_volume_no = target_owned_volume
            fields_to_update.append("owned_volume_no")
        if latest_volume_no is not None and (
            record.latest_volume_no is None
            or latest_volume_no > record.latest_volume_no
        ):
            record.latest_volume_no = latest_volume_no
            record.latest_checked_at = timezone.now()
            fields_to_update.extend(["latest_volume_no", "latest_checked_at"])
        if source_url and record.source_url != source_url:
            record.source_url = source_url
            fields_to_update.append("source_url")
        if fields_to_update:
            record.updated_at = timezone.now()
            fields_to_update.append("updated_at")
            record.save(update_fields=fields_to_update)

    return record, created


def update_owned_volume(
    owned_series_id: int,
    owned_volume_no: int,
) -> bool:
    queryset = OwnedSeries.objects.filter(
        owned_series_id=owned_series_id,
    )
    if not queryset.exists():
        return False

    queryset.update(
        owned_volume_no=owned_volume_no,
        updated_at=timezone.now(),
    )
    return True


def replace_owned_volumes(
    owned_series_id: int,
    volume_numbers: list[int] | set[int] | tuple[int, ...],
) -> bool:
    """체크박스 선택값과 보유 권수 요약값을 함께 저장한다."""
    numbers = sorted({int(volume_no) for volume_no in volume_numbers})
    if any(volume_no < 1 for volume_no in numbers):
        raise ValueError("권수는 1권 이상이어야 합니다.")

    owned_series_queryset = OwnedSeries.objects.filter(
        owned_series_id=owned_series_id,
    )
    if not owned_series_queryset.exists():
        return False

    OwnedSeriesVolume.objects.filter(
        owned_series_id=owned_series_id,
    ).delete()
    if numbers:
        OwnedSeriesVolume.objects.bulk_create(
            [
                OwnedSeriesVolume(
                    owned_series_id=owned_series_id,
                    volume_no=volume_no,
                )
                for volume_no in numbers
            ],
            ignore_conflicts=True,
        )

    owned_series_queryset.update(
        owned_volume_no=len(numbers),
        updated_at=timezone.now(),
    )
    return True


def update_latest_volume(
    owned_series_id: int,
    latest_volume_no: int | None,
    source_url: str | None = None,
    checked_at: datetime | None = None,
) -> None:
    values = {
        "latest_volume_no": latest_volume_no,
        "latest_checked_at": checked_at or timezone.now(),
        "updated_at": timezone.now(),
    }
    if source_url:
        values["source_url"] = source_url
    OwnedSeries.objects.filter(
        owned_series_id=owned_series_id,
    ).update(**values)


def remove_owned_series(owned_series_id: int) -> None:
    OwnedSeriesVolume.objects.filter(
        owned_series_id=owned_series_id,
    ).delete()
    OwnedSeries.objects.filter(
        owned_series_id=owned_series_id,
    ).delete()
