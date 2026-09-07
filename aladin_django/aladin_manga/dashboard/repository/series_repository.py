from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from dashboard.models import BookSnapshot, Series, SeriesDailyStat


@dataclass
class PopularSeries:
    series_rank: int
    series: Series
    volume_count: int
    best_rank: int | None
    total_sales_point: int | None
    volume_numbers: str


def get_series_snapshot_times():
    return (
        SeriesDailyStat.objects
        .values_list("collected_at", flat=True)
        .distinct()
        .order_by("-collected_at")
    )


def _volume_sort_key(value: str) -> tuple[int, int, str]:
    match = re.search(r"\d+", value)
    if match is None:
        return 1, 10**9, value
    return 0, int(match.group()), value


def _aggregate_popular_series(
    snapshot_time: datetime,
) -> list[PopularSeries]:
    """해당 스냅샷의 전체 도서 행을 시리즈명별로 다시 집계한다."""
    grouped: dict[int, dict] = {}
    snapshots = (
        BookSnapshot.objects
        .select_related("book", "book__series")
        .filter(
            collected_at=snapshot_time,
            is_out=False,
            book__series__isnull=False,
        )
    )

    for snapshot in snapshots:
        series = snapshot.book.series
        bucket = grouped.setdefault(
            series.series_id,
            {
                "series": series,
                "volume_count": 0,
                "ranks": [],
                "sales_points": [],
                "volume_numbers": set(),
            },
        )
        bucket["volume_count"] += 1

        if snapshot.rank_no is not None:
            bucket["ranks"].append(snapshot.rank_no)
        if snapshot.sales_point is not None:
            bucket["sales_points"].append(snapshot.sales_point)

        volume_no = (snapshot.book.vol_no or "").strip()
        if volume_no:
            bucket["volume_numbers"].add(volume_no)

    ordered = sorted(
        grouped.values(),
        key=lambda bucket: (
            -bucket["volume_count"],
            -(sum(bucket["sales_points"]) if bucket["sales_points"] else 0),
            min(bucket["ranks"]) if bucket["ranks"] else 10**9,
            bucket["series"].series_name,
        ),
    )

    popular_series: list[PopularSeries] = []
    for series_rank, bucket in enumerate(ordered, start=1):
        volume_numbers = sorted(
            bucket["volume_numbers"],
            key=_volume_sort_key,
        )
        popular_series.append(
            PopularSeries(
                series_rank=series_rank,
                series=bucket["series"],
                volume_count=bucket["volume_count"],
                best_rank=(
                    min(bucket["ranks"]) if bucket["ranks"] else None
                ),
                total_sales_point=(
                    sum(bucket["sales_points"])
                    if bucket["sales_points"]
                    else None
                ),
                volume_numbers=", ".join(volume_numbers),
            )
        )

    return popular_series


def get_top_series(
    snapshot_time: datetime,
    limit: int = 10,
) -> list[PopularSeries]:
    return _aggregate_popular_series(snapshot_time)[:limit]


def get_all_series(
    snapshot_time: datetime,
) -> list[PopularSeries]:
    return _aggregate_popular_series(snapshot_time)
