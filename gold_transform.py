"""Silver 이력 CSV를 Gold 추이 데이터로 변환한다.

실행:
    python gold_transform.py
    python gold_transform.py --input history/aladin_manga_history.csv

Gold 데이터에는 각 도서의 직전 수집 시점과 비교한 순위·판매지수 변화가
추가된다. 첫 번째 수집분은 기준선이므로 is_new=0으로 기록한다.
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from daily_snapshot import deduplicate_daily_rows, parse_collected_at


DERIVED_FIELDS = [
    "previous_rank",
    "rank_change",
    "previous_sales_point",
    "sales_point_change",
    "is_new",
    "is_out",
]

SERIES_FIELDS = [
    "collected_at",
    "series_rank",
    "series_name",
    "volume_count",
    "volume_numbers",
    "best_rank",
    "avg_rank",
    "total_sales_point",
    "avg_sales_point",
]

REQUIRED_FIELDS = {
    "item_id",
    "title",
    "rank",
    "sales_point",
    "collected_at",
}


def parse_timestamp(value: str) -> datetime:
    """ISO 형식 수집 시각을 datetime으로 변환한다."""
    try:
        return parse_collected_at(value)
    except ValueError as exc:
        raise ValueError(f"collected_at 형식을 해석할 수 없습니다: {value}") from exc


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None or not value.strip():
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def volume_sort_key(value: str) -> tuple[int, int, str]:
    match = re.search(r"\d+", value)
    if match is None:
        return 1, 10**9, value
    return 0, int(match.group()), value


def format_volume_numbers(items: list[dict[str, str]]) -> str:
    values = {
        row.get("vol_no", "").strip()
        for row in items
        if row.get("vol_no", "").strip()
    }
    return ", ".join(sorted(values, key=volume_sort_key))


def item_key(row: dict[str, str]) -> str:
    """item_id를 우선 사용하고, 없으면 제목을 식별자로 사용한다."""
    item_id = row.get("item_id", "").strip()
    if item_id:
        return f"item_id:{item_id}"
    return f"title:{row.get('title', '').strip()}"


def load_history(input_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Silver 이력 CSV를 찾을 수 없습니다: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        input_fields = reader.fieldnames or []
        missing_fields = REQUIRED_FIELDS - set(input_fields)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"필수 컬럼이 없습니다: {missing}")

        rows = [
            {key: (value or "") for key, value in row.items()}
            for row in reader
        ]

    return (
        deduplicate_daily_rows(
            rows,
            identity_fields=("item_id", "title"),
        ),
        input_fields,
    )


def transform_to_gold(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """수집 시점별 비교 결과와 이탈 이벤트를 생성한다."""
    rows = deduplicate_daily_rows(
        rows,
        identity_fields=("item_id", "title"),
    )
    snapshots: dict[str, dict[str, dict[str, str]]] = {}

    for row in rows:
        collected_at = row.get("collected_at", "").strip()
        if not collected_at:
            raise ValueError("collected_at이 비어 있는 행이 있습니다.")

        # 같은 시점에 같은 도서가 중복되면 마지막 행을 사용한다.
        snapshots.setdefault(collected_at, {})[item_key(row)] = row

    sorted_timestamps = sorted(snapshots, key=parse_timestamp)
    gold_rows: list[dict[str, str]] = []

    for index, collected_at in enumerate(sorted_timestamps):
        current_items = snapshots[collected_at]
        previous_items = (
            snapshots[sorted_timestamps[index - 1]] if index > 0 else {}
        )

        for key, current in current_items.items():
            previous = previous_items.get(key)
            current_rank = parse_int(current.get("rank"))
            previous_rank = parse_int(previous.get("rank")) if previous else None
            current_sales_point = parse_int(current.get("sales_point"))
            previous_sales_point = (
                parse_int(previous.get("sales_point")) if previous else None
            )

            result = dict(current)
            result["previous_rank"] = (
                str(previous_rank) if previous_rank is not None else ""
            )
            result["rank_change"] = (
                str(previous_rank - current_rank)
                if previous_rank is not None and current_rank is not None
                else ""
            )
            result["previous_sales_point"] = (
                str(previous_sales_point)
                if previous_sales_point is not None
                else ""
            )
            result["sales_point_change"] = (
                str(current_sales_point - previous_sales_point)
                if current_sales_point is not None
                and previous_sales_point is not None
                else ""
            )
            # 첫 수집분은 신규 진입이 아니라 비교를 위한 기준선이다.
            result["is_new"] = "1" if index > 0 and previous is None else "0"
            result["is_out"] = "0"
            gold_rows.append(result)

        # 직전 수집분에는 있었지만 현재 수집분에 없는 도서를 이탈로 기록한다.
        for key, previous in previous_items.items():
            if key in current_items:
                continue

            result = dict(previous)
            previous_rank = parse_int(previous.get("rank"))
            previous_sales_point = parse_int(previous.get("sales_point"))
            result["collected_at"] = collected_at
            result["rank"] = ""
            result["sales_point"] = ""
            result["previous_rank"] = (
                str(previous_rank) if previous_rank is not None else ""
            )
            result["rank_change"] = ""
            result["previous_sales_point"] = (
                str(previous_sales_point)
                if previous_sales_point is not None
                else ""
            )
            result["sales_point_change"] = ""
            result["is_new"] = "0"
            result["is_out"] = "1"
            gold_rows.append(result)

    return sorted(
        gold_rows,
        key=lambda row: (
            parse_timestamp(row["collected_at"]),
            parse_int(row.get("rank")) or 10**9,
            row.get("title", ""),
        ),
    )


def aggregate_series(gold_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Gold 도서 데이터를 수집 시점·시리즈별 집계 데이터로 변환한다."""
    grouped: dict[tuple[str, str], dict[str, dict[str, str]]] = {}

    for row in gold_rows:
        # 이탈 이벤트는 현재 순위표에 없는 도서이므로 시리즈 집계에서 제외한다.
        if row.get("is_out") == "1":
            continue

        collected_at = row.get("collected_at", "").strip()
        series_name = row.get("series_name", "").strip()
        if not collected_at or not series_name:
            continue

        group_key = (collected_at, series_name)
        grouped.setdefault(group_key, {})[item_key(row)] = row

    snapshot_groups: dict[str, list[dict[str, str]]] = {}

    for (collected_at, series_name), items in grouped.items():
        ranks = [
            rank
            for row in items.values()
            if (rank := parse_int(row.get("rank"))) is not None
        ]
        sales_points = [
            sales_point
            for row in items.values()
            if (sales_point := parse_int(row.get("sales_point"))) is not None
        ]

        total_sales_point = sum(sales_points) if sales_points else None
        series_row = {
            "collected_at": collected_at,
            "series_rank": "",
            "series_name": series_name,
            "volume_count": str(len(items)),
            "volume_numbers": format_volume_numbers(list(items.values())),
            "best_rank": str(min(ranks)) if ranks else "",
            "avg_rank": str(round(sum(ranks) / len(ranks), 2)) if ranks else "",
            "total_sales_point": (
                str(total_sales_point) if total_sales_point is not None else ""
            ),
            "avg_sales_point": (
                str(round(sum(sales_points) / len(sales_points), 2))
                if sales_points
                else ""
            ),
        }
        snapshot_groups.setdefault(collected_at, []).append(series_row)

    series_rows: list[dict[str, str]] = []
    for collected_at in sorted(snapshot_groups, key=parse_timestamp):
        snapshot_series = sorted(
            snapshot_groups[collected_at],
            key=lambda row: (
                -(parse_int(row.get("volume_count")) or 0),
                -(parse_int(row.get("total_sales_point")) or 0),
                parse_int(row.get("best_rank")) or 10**9,
                row["series_name"],
            ),
        )

        for series_rank, row in enumerate(snapshot_series, start=1):
            row["series_rank"] = str(series_rank)
            series_rows.append(row)

    return series_rows


def save_gold(
    rows: list[dict[str, str]],
    input_fields: list[str],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_fields = input_fields + [
        field for field in DERIVED_FIELDS if field not in input_fields
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)


def save_series(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=SERIES_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def default_input_path() -> Path:
    """기존 history 폴더와 새 silver 폴더를 모두 지원한다."""
    candidates = [
        Path(__file__).with_name("history") / "aladin_manga_history.csv",
        Path(__file__).with_name("silver") / "aladin_manga_history.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="알라딘 Silver 이력 Gold 변환기")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Silver 이력 CSV 경로",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("gold") / "manga_trend.csv",
        help="Gold 추이 CSV 경로",
    )
    parser.add_argument(
        "--series-output",
        type=Path,
        default=Path(__file__).with_name("gold") / "popular_series.csv",
        help="시리즈별 Gold 집계 CSV 경로",
    )
    args = parser.parse_args()

    input_path = args.input or default_input_path()
    rows, input_fields = load_history(input_path)
    gold_rows = transform_to_gold(rows)
    series_rows = aggregate_series(gold_rows)
    save_gold(gold_rows, input_fields, args.output)
    save_series(series_rows, args.series_output)

    new_count = sum(row["is_new"] == "1" for row in gold_rows)
    out_count = sum(row["is_out"] == "1" for row in gold_rows)
    print(f"{len(gold_rows)}개 Gold 행을 저장했습니다: {args.output.resolve()}")
    print(
        f"{len(series_rows)}개 시리즈 집계 행을 저장했습니다: "
        f"{args.series_output.resolve()}"
    )
    print(f"신규 관측: {new_count}개, 이탈 감지: {out_count}개")


if __name__ == "__main__":
    main()
