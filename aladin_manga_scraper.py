"""알라딘 만화/라이트노벨 베스트셀러 전체 페이지 수집기.

설치:
    python -m pip install requests beautifulsoup4

실행:
    python aladin_manga_scraper.py
    python aladin_manga_scraper.py --output aladin_manga.csv
    python aladin_manga_scraper.py --raw-dir raw
    python aladin_manga_scraper.py --history-output silver/aladin_manga_history.csv

price는 할인 가격이 표시된 경우 할인 가격을 저장합니다.
special_benefits는 도서 제목 옆의 ss_f_g2 문구를 그대로 저장합니다.
원본 HTML은 실행일 기준으로 raw/YYYY-MM-DD/page_001.html 형식으로 저장합니다.
네트워크·HTTP 오류나 알라딘 오류 페이지가 반환되면 페이지별로 최대 3회 재시도합니다.
목록 페이지에서 월까지만 제공된 발매일은 release_date_enricher.py로
상품 상세 페이지를 확인한 뒤 일자까지 보강할 수 있습니다.
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from daily_snapshot import deduplicate_daily_rows


URL = (
    "https://www.aladin.co.kr/shop/common/wbest.aspx?"
    "BestType=Bestseller&BranchType=1&CID=2551"
)

FIELDS = [
    "item_id",
    "title",
    "series_name",
    "vol_no",
    "edition_type",
    "special_benefits",
    "author",
    "publisher",
    "release_date",
    "price",
    "rating",
    "sales_point",
    "rank",
    "collected_at",
]

KST = timezone(timedelta(hours=9))
MAX_RETRIES = 3
RETRY_DELAYS_SECONDS = (3, 6, 12)

EDITION_MARKERS = (
    "특장판",
    "한정판",
    "특전판",
    "특별판",
    "초판",
    "애장판",
    "완전판",
    "일반판",
    "통상판",
)


def clean_space(value: str) -> str:
    """줄바꿈·탭·nbsp를 하나의 공백으로 정리한다."""
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def parse_int(value: str) -> Optional[int]:
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def parse_date(value: str) -> Optional[str]:
    """예: '2026년 8월' -> '2026-08', '2026년 8월 12일' -> '2026-08-12'."""
    match = re.search(
        r"(?P<year>\d{4})\s*년"
        r"(?:\s*(?P<month>\d{1,2})\s*월)?"
        r"(?:\s*(?P<day>\d{1,2})\s*일)?",
        value,
    )
    if not match:
        return None

    year = match.group("year")
    month = match.group("month")
    day = match.group("day")

    if day:
        return f"{year}-{int(month):02d}-{int(day):02d}"
    if month:
        return f"{year}-{int(month):02d}"
    return year


def split_title_fields(title: str) -> tuple[str, Optional[str], str]:
    """제목에서 시리즈명, 권수, 판본 유형을 보수적으로 분리한다."""
    edition_types: list[str] = []

    def remove_known_edition(match: re.Match[str]) -> str:
        parenthetical_text = clean_space(match.group(1))
        marker = next(
            (
                candidate
                for candidate in EDITION_MARKERS
                if candidate in parenthetical_text
            ),
            None,
        )
        if marker is None:
            return match.group(0)
        if parenthetical_text not in edition_types:
            edition_types.append(parenthetical_text)
        return ""

    title_without_edition = re.sub(
        r"\s*\(([^()]*)\)",
        remove_known_edition,
        title,
    )
    title_without_edition = clean_space(title_without_edition)

    # 단권은 숫자, 세트는 '1~3'처럼 범위 문자열로 보존한다.
    volume_match = re.fullmatch(
        r"(?P<series>.+?)\s+"
        r"(?P<volume>\d+(?:\s*[~～-]\s*\d+)?)"
        r"\s*(?:권)?\s*(?:세트)?",
        title_without_edition,
    )
    if volume_match is None:
        return title_without_edition, None, ", ".join(edition_types)

    series_name = clean_space(volume_match.group("series"))
    volume_no = re.sub(r"\s+", "", volume_match.group("volume"))
    volume_no = volume_no.replace("～", "~").replace("－", "-")
    return series_name, volume_no, ", ".join(edition_types)


def find_info_li(book_block: Tag) -> Optional[Tag]:
    """작가·출판사·발매일이 들어 있는 li를 찾는다."""
    for li in book_block.select("ul > li"):
        text = clean_space(li.get_text(" ", strip=True))
        if "|" in text and re.search(r"\d{4}\s*년", text):
            return li
    return None


def extract_authors(info_li: Tag) -> str:
    """정보 줄에서 '(지은이)' 역할이 붙은 사람의 이름만 추출한다."""
    authors: list[str] = []

    for link in info_li.find_all("a"):
        href = link.get("href", "")
        if "publishersearch" in href.lower():
            continue

        role_parts: list[str] = []
        for sibling in link.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "a":
                break
            if isinstance(sibling, Tag):
                role_parts.append(sibling.get_text(" ", strip=True))
            else:
                role_parts.append(str(sibling))

        role_text = clean_space(" ".join(role_parts))
        if re.search(r"\(\s*지은이\s*\)", role_text):
            author_name = clean_space(link.get_text(" ", strip=True))
            if author_name and author_name not in authors:
                authors.append(author_name)

    return ", ".join(authors)


def extract_rank(title_link: Tag) -> Optional[int]:
    """상품 바깥쪽 순위 셀에서 실제 베스트셀러 순위를 추출한다."""
    for row in title_link.find_parents("tr"):
        direct_cells = row.find_all("td", recursive=False)
        if not direct_cells:
            continue

        rank_text = clean_space(direct_cells[0].get_text(" ", strip=True))
        match = re.fullmatch(r"(?P<rank>\d+)\.", rank_text)
        if match:
            return int(match.group("rank"))

    return None


def parse_book(title_link: Tag) -> Optional[dict[str, object]]:
    """상품 제목 링크 하나를 기준으로 요청한 필드를 추출한다."""
    book_block = title_link.find_parent("div", class_="ss_book_list")
    title_li = title_link.find_parent("li")
    if book_block is None or title_li is None:
        return None

    title = clean_space(title_link.get_text(" ", strip=True))
    series_name, vol_no, edition_type = split_title_fields(title)

    # 제목 옆에 있는 부가 문구를 그대로 가져온다.
    # 예: "- 루나 코믹스, 초판 한정 ..."
    special_benefit_nodes = title_li.select("span.ss_f_g2")
    special_benefits = " ".join(
        clean_space(node.get_text(" ", strip=True))
        for node in special_benefit_nodes
    )

    info_li = find_info_li(book_block)
    if info_li is None:
        return None

    info_text = clean_space(info_li.get_text(" ", strip=True))
    info_parts = [clean_space(part) for part in info_text.split("|")]

    # '(지은이)' 역할이 붙은 사람만 가져온다.
    author = extract_authors(info_li)

    publisher_link = info_li.select_one(
        'a[href*="PublisherSearch"], a[href*="publishersearch"]'
    )
    if publisher_link is not None:
        publisher = clean_space(publisher_link.get_text(" ", strip=True))
    elif len(info_parts) >= 2:
        publisher = info_parts[1]
    else:
        publisher = ""

    release_date = parse_date(info_text)

    price_li = next(
        (
            li
            for li in book_block.select("ul > li")
            if "원" in clean_space(li.get_text(" ", strip=True))
            and ("→" in li.get_text() or "할인" in li.get_text())
        ),
        None,
    )
    if price_li is None:
        price_li = next(
            (
                li
                for li in book_block.select("ul > li")
                if "원" in clean_space(li.get_text(" ", strip=True))
            ),
            None,
        )

    price: Optional[int] = None
    if price_li is not None:
        sale_price_node = price_li.select_one(".ss_p2 em")
        if sale_price_node is not None:
            price = parse_int(sale_price_node.get_text(" ", strip=True))
        else:
            first_price = re.search(r"\d[\d,]*", price_li.get_text(" ", strip=True))
            if first_price:
                price = parse_int(first_price.group(0))

    rating_node = book_block.select_one(".star_score")
    rating: Optional[float] = None
    if rating_node is not None:
        rating_text = clean_space(rating_node.get_text(" ", strip=True))
        try:
            rating = float(rating_text)
        except ValueError:
            rating = None

    sales_point_node = book_block.select_one(".sales_point")
    sales_point = (
        parse_int(sales_point_node.get_text(" ", strip=True))
        if sales_point_node is not None
        else None
    )

    return {
        "title": title,
        "series_name": series_name,
        "vol_no": vol_no,
        "edition_type": edition_type,
        "special_benefits": special_benefits,
        "author": author,
        "publisher": publisher,
        "release_date": release_date,
        "price": price,
        "rating": rating,
        "sales_point": sales_point,
    }


class RetryablePageError(RuntimeError):
    """일시적인 접근 오류로 다시 요청할 수 있는 페이지 오류."""


def is_aladin_error_page(soup: BeautifulSoup) -> bool:
    """상품 목록 대신 알라딘 오류 페이지가 반환됐는지 확인한다."""
    if soup.select_one("#lbErrorInfo, .error2013") is not None:
        return True

    page_text = clean_space(soup.get_text(" ", strip=True))
    return "요청하신 페이지에 오류가 존재합니다" in page_text


def fetch_page(
    session: requests.Session,
    page_url: str,
    page_number: int,
    raw_page_path: Path,
) -> BeautifulSoup:
    """페이지를 요청하고 일시 오류는 최대 3회 재시도한다."""
    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(page_url, timeout=20)
            # 실패 응답도 마지막 시도 결과를 확인할 수 있도록 보관한다.
            raw_page_path.write_bytes(response.content)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            if is_aladin_error_page(soup):
                raise RetryablePageError(
                    "알라딘 오류 페이지가 반환되었습니다."
                )

            # 첫 페이지에 상품 링크가 없으면 정상적인 종료가 아니라
            # 일시 오류 또는 접근 제한일 가능성이 높으므로 재시도한다.
            if page_number == 1 and not soup.select("a.bo3"):
                raise RetryablePageError(
                    "첫 페이지에서 상품 링크를 찾지 못했습니다."
                )

            return soup
        except (requests.RequestException, RetryablePageError) as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break

            retry_number = attempt + 1
            wait_seconds = RETRY_DELAYS_SECONDS[attempt]
            print(
                f"{page_number}페이지 일시 오류 "
                f"(재시도 {retry_number}/{MAX_RETRIES}): {exc}"
                f" - {wait_seconds}초 후 다시 요청합니다.",
                flush=True,
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        f"{page_number}페이지 요청이 최대 재시도 횟수({MAX_RETRIES}회)를 "
        f"초과했습니다: {last_error}"
    ) from last_error


def crawl_all_pages(raw_dir: Path) -> list[dict[str, object]]:
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

    books: list[dict[str, object]] = []
    seen_item_ids: set[str] = set()
    page_number = 1
    collected_at = datetime.now(KST).isoformat(timespec="seconds")
    collection_date = collected_at[:10]
    raw_date_dir = raw_dir / collection_date
    raw_date_dir.mkdir(parents=True, exist_ok=True)

    while True:
        # 1페이지는 사용자가 준 URL을 그대로 사용하고,
        # 2페이지부터는 알라딘의 페이지 이동 링크 형식에 맞춘다.
        page_url = URL
        if page_number > 1:
            page_url = (
                f"{URL}&page={page_number}&cnt=1000&SortOrder=1"
            )

        raw_page_path = raw_date_dir / f"page_{page_number:03d}.html"
        soup = fetch_page(session, page_url, page_number, raw_page_path)

        title_links = soup.select("a.bo3")
        page_books: list[dict[str, object]] = []

        for position, title_link in enumerate(title_links, start=1):
            # 상품 URL의 ItemId를 이용해 페이지 사이 중복을 제거한다.
            href = title_link.get("href", "")
            item_id_match = re.search(r"ItemId=([^&#]+)", href, re.IGNORECASE)
            item_id = item_id_match.group(1) if item_id_match else None
            item_key = (
                item_id
                if item_id is not None
                else clean_space(title_link.get_text(" ", strip=True))
            )

            if item_key in seen_item_ids:
                continue

            book = parse_book(title_link)
            if book is not None:
                seen_item_ids.add(item_key)
                book["item_id"] = item_id
                book["rank"] = extract_rank(title_link)
                if book["rank"] is None:
                    # 순위 셀을 찾지 못한 경우에만 페이지 위치를 보조값으로 사용한다.
                    book["rank"] = (page_number - 1) * 50 + position
                book["collected_at"] = collected_at
                page_books.append(book)

        if not title_links or not page_books:
            break

        books.extend(page_books)
        print(f"{page_number}페이지: {len(page_books)}개 수집")
        page_number += 1

        # 여러 페이지를 연속으로 요청하지 않도록 잠시 대기한다.
        time.sleep(1)

    if not books:
        raise RuntimeError(
            "상품을 찾지 못했습니다. 알라딘 HTML 구조나 접근 정책이 변경되었는지 확인하세요."
        )

    return books


def save_csv(books: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(books)


def append_history(
    books: list[dict[str, object]],
    history_path: Path,
) -> int:
    """도서·수집일별 최신 관측만 남기도록 이력 CSV를 갱신한다."""
    history_path.parent.mkdir(parents=True, exist_ok=True)

    existing_rows: list[dict[str, object]] = []
    history_exists = history_path.exists() and history_path.stat().st_size > 0
    history_fields = FIELDS

    if history_exists:
        with history_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is not None:
                if set(reader.fieldnames) != set(FIELDS):
                    raise ValueError(
                        f"기존 이력 CSV의 컬럼이 현재 코드와 다릅니다: {history_path}"
                    )
                history_fields = reader.fieldnames

            for row in reader:
                existing_rows.append(
                    {key: (value or "") for key, value in row.items()}
                )

    normalized_rows = deduplicate_daily_rows(
        [*existing_rows, *books],
        identity_fields=("item_id", "title"),
    )

    with history_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=history_fields)
        writer.writeheader()
        writer.writerows(normalized_rows)

    return len(books)


def main() -> None:
    parser = argparse.ArgumentParser(description="알라딘 만화 베스트셀러 전체 페이지 크롤러")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("aladin_manga.csv"),
        help="저장할 CSV 경로",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(__file__).with_name("raw"),
        help="날짜별 원본 HTML을 저장할 폴더",
    )
    parser.add_argument(
        "--history-output",
        type=Path,
        default=Path(__file__).with_name("history") / "aladin_manga_history.csv",
        help="수집 결과를 누적할 Silver CSV 경로",
    )
    args = parser.parse_args()

    books = crawl_all_pages(args.raw_dir)
    save_csv(books, args.output)
    added_count = append_history(books, args.history_output)
    print(f"{len(books)}개 상품을 수집했습니다: {args.output.resolve()}")
    print(f"원본 HTML 저장 위치: {(args.raw_dir / books[0]['collected_at'][:10]).resolve()}")
    print(
        f"최신 이력 {added_count}개 행을 반영했습니다: "
        f"{args.history_output.resolve()}"
    )


if __name__ == "__main__":
    main()
