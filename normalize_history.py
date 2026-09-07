"""Silver 이력 CSV에서 같은 도서·같은 날짜의 오래된 행을 제거한다."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from daily_snapshot import deduplicate_daily_rows


def normalize_history(path: Path) -> tuple[int, int]:
    if not path.exists():
        raise FileNotFoundError(f"이력 CSV를 찾을 수 없습니다: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames or []
        if not fieldnames:
            raise ValueError(f"이력 CSV 헤더를 찾을 수 없습니다: {path}")
        rows = [
            {key: (value or "") for key, value in row.items()}
            for row in reader
        ]

    normalized_rows = deduplicate_daily_rows(
        rows,
        identity_fields=("item_id", "title"),
    )
    temporary_path = path.with_name(f".{path.name}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized_rows)
    temporary_path.replace(path)
    return len(rows), len(normalized_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="일별 Silver 이력 중복 정리")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).with_name("history") / "aladin_manga_history.csv",
    )
    args = parser.parse_args()

    before, after = normalize_history(args.input)
    print(f"이력 행 정리 완료: {before}개 -> {after}개")


if __name__ == "__main__":
    main()
