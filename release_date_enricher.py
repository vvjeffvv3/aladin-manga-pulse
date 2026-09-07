"""알라딘 상품 상세 페이지에서 정확한 발매일을 보강한다.

베스트셀러 목록 페이지는 발매일을 보통 연·월까지만 제공하므로,
상품 상세 페이지를 추가로 확인해 YYYY-MM-DD 형식으로 업데이트한다.

실행:
    python release_date_enricher.py
    python release_date_enricher.py --input history/aladin_manga_history.csv
    python release_date_enricher.py --delay 1.0

보강 후에는 Gold 변환과 MySQL 적재를 다시 실행한다.
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).parent
PRODUCT_URL = "https://www.aladin.co.kr/shop/wproduct.aspx?ItemId={item_id}"
EXACT_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
KOREAN_DATE_RE = re.compile(
    r"(?P<year>\d{4})\s*년\s*"
    r"(?P<month>\d{1,2})\s*월\s*"
    r"(?P<day>\d{1,2})\s*일"
)
NUMERIC_DATE_RE = re.compile(
    r"(?P<year>\d{4})\s*[./-]\s*"
    r"(?P<month>\d{1,2})\s*[./-]\s*"
    r"(?P<day>\d{1,2})"
)
LABELLED_DATE_RE = re.compile(
    r"(?:출간일|발행일|발매일|출시일)\s*[:：]?\s*"
    r"(?P<date>\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|"
    r"\d{4}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2})"
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def normalize_exact_date(value: str) -> str | None:
    value = clean_text(value)
    match = KOREAN_DATE_RE.search(value) or NUMERIC_DATE_RE.search(value)
    if match is None:
        return None

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def is_exact_date(value: str | None) -> bool:
    return bool(value and EXACT_DATE_RE.fullmatch(value.strip()))


def extract_release_date(html: bytes) -> str | None:
    """상세 페이지에서 '출간일'로 표시된 정확한 날짜를 추출한다."""
    soup = BeautifulSoup(html, "html.parser")

    for selector in (
        'meta[itemprop="datePublished"]',
        'meta[property="book:release_date"]',
    ):
        node = soup.select_one(selector)
        if node is not None:
            date = normalize_exact_date(node.get("content", ""))
            if date:
                return date

    page_text = clean_text(soup.get_text(" ", strip=True))
    labelled_match = LABELLED_DATE_RE.search(page_text)
    if labelled_match is not None:
        return normalize_exact_date(labelled_match.group("date"))

    # JSON-LD에 datePublished만 제공되는 상세 페이지도 대비한다.
    json_date_match = re.search(
        r"datePublished\s*[\"']?\s*:\s*[\"']"
        r"(?P<date>\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        html.decode("utf-8", errors="ignore"),
        re.IGNORECASE,
    )
    if json_date_match is not None:
        return normalize_exact_date(json_date_match.group("date"))

    return None


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )
    return session


def load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        fields = reader.fieldnames or []
        if "item_id" not in fields or "release_date" not in fields:
            raise ValueError(
                f"item_id와 release_date 컬럼이 필요합니다: {path}"
            )
        rows = [
            {key: (value or "") for key, value in row.items()}
            for row in reader
        ]
    return rows, fields


def update_csv(
    path: Path,
    rows: list[dict[str, str]],
    fields: list[str],
    release_dates: dict[str, str],
) -> int:
    updated_count = 0
    for row in rows:
        item_id = row.get("item_id", "").strip()
        release_date = release_dates.get(item_id)
        if release_date and row.get("release_date", "").strip() != release_date:
            row["release_date"] = release_date
            updated_count += 1

    if updated_count == 0:
        return 0

    temporary_path = path.with_name(f"{path.name}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)
    return updated_count


def enrich_paths(
    paths: list[Path],
    delay: float,
    timeout: float,
) -> None:
    loaded: list[tuple[Path, list[dict[str, str]], list[str]]] = []
    item_ids: set[str] = set()

    for path in paths:
        rows, fields = load_csv(path)
        loaded.append((path, rows, fields))
        for row in rows:
            item_id = row.get("item_id", "").strip()
            if item_id and not is_exact_date(row.get("release_date")):
                item_ids.add(item_id)

    print(f"정확한 발매일 확인 대상: {len(item_ids)}개 상품")
    if not item_ids:
        print("이미 모든 발매일이 YYYY-MM-DD 형식입니다.")
        return

    session = create_session()
    release_dates: dict[str, str] = {}
    for index, item_id in enumerate(sorted(item_ids), start=1):
        try:
            response = session.get(
                PRODUCT_URL.format(item_id=item_id),
                timeout=timeout,
            )
            response.raise_for_status()
            release_date = extract_release_date(response.content)
        except requests.RequestException as exc:
            print(f"[{index}/{len(item_ids)}] {item_id}: 요청 실패 - {exc}")
            release_date = None

        if release_date:
            release_dates[item_id] = release_date
            print(f"[{index}/{len(item_ids)}] {item_id}: {release_date}")
        else:
            print(f"[{index}/{len(item_ids)}] {item_id}: 정확한 날짜 없음")

        if index < len(item_ids):
            time.sleep(max(0.0, delay))

    total_updated = 0
    for path, rows, fields in loaded:
        updated_count = update_csv(path, rows, fields, release_dates)
        total_updated += updated_count
        print(f"{updated_count}개 행 업데이트: {path.resolve()}")

    print(f"총 업데이트 행: {total_updated}개")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="알라딘 상세 페이지에서 정확한 발매일을 보강"
    )
    parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        type=Path,
        default=None,
        help="업데이트할 CSV 경로. 여러 번 지정할 수 있음",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.7,
        help="상품 상세 페이지 사이 대기 시간(초)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="요청 타임아웃(초)",
    )
    args = parser.parse_args()

    paths = args.inputs or [
        BASE_DIR / "history" / "aladin_manga_history.csv",
        BASE_DIR / "aladin_manga.csv",
    ]
    enrich_paths(paths, delay=args.delay, timeout=args.timeout)


if __name__ == "__main__":
    main()
