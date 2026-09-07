"""수집 시각을 기준으로 날짜별 최신 관측을 선택하는 공통 유틸리티."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping


KST = timezone(timedelta(hours=9))


def parse_collected_at(value: str) -> datetime:
    """ISO 수집 시각을 KST 기준 timezone-aware datetime으로 변환한다."""
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def collected_date(value: str) -> str:
    """수집 시각에서 KST 기준 수집일(YYYY-MM-DD)을 반환한다."""
    return parse_collected_at(value).date().isoformat()


def row_identity(
    row: Mapping[str, object],
    identity_fields: tuple[str, ...],
) -> str:
    """행에서 날짜별 중복을 판별할 식별자 문자열을 만든다."""
    for field_name in identity_fields:
        value = str(row.get(field_name) or "").strip()
        if value:
            return f"{field_name}:{value}"
    return ""


def deduplicate_daily_rows(
    rows: Iterable[Mapping[str, object]],
    identity_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    """같은 식별자·같은 날짜의 행 중 collected_at이 가장 최신인 행만 남긴다.

    같은 시각의 행이 중복으로 들어오면 뒤에서 들어온 행을 사용한다.
    따라서 새 실행 결과를 기존 이력보다 먼저 선택할 수 있다.
    """
    latest: dict[tuple[str, str], tuple[datetime, int, dict[str, object]]] = {}

    for position, raw_row in enumerate(rows):
        row = {key: value for key, value in raw_row.items()}
        collected_at = str(row.get("collected_at") or "").strip()
        if not collected_at:
            raise ValueError("collected_at이 비어 있는 행이 있습니다.")

        identity = row_identity(row, identity_fields)
        if not identity:
            raise ValueError(
                "날짜별 중복을 판별할 식별자 컬럼이 비어 있는 행이 있습니다."
            )

        collected_at_dt = parse_collected_at(collected_at)
        key = (identity, collected_at_dt.date().isoformat())
        previous = latest.get(key)

        if previous is None or collected_at_dt >= previous[0]:
            latest[key] = (collected_at_dt, position, row)

    return [
        row
        for _, _, row in sorted(
            latest.values(),
            key=lambda value: (value[0], row_identity(value[2], identity_fields)),
        )
    ]
