"""알라딘 상품/시리즈 페이지에서 순위 밖 시리즈 정보를 보완한다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin, urlparse


ALADIN_HOST = "www.aladin.co.kr"
ALADIN_SEARCH_URL = (
    "https://www.aladin.co.kr/search/wsearchresult.aspx?"
    "SearchTarget=All&SearchWord={keyword}"
)
ALADIN_DETAIL_URL = "https://www.aladin.co.kr/shop/wproduct.aspx?ItemId={item_id}"


class AladinLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class AladinSeriesLookup:
    series_name: str
    latest_volume_no: int | None
    source_url: str


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def extract_item_id(value: str) -> str | None:
    match = re.search(r"[?&]itemid=(\d+)", value, re.IGNORECASE)
    if match:
        return match.group(1)

    cleaned = value.strip()
    if re.fullmatch(r"97[89]\d{10}", cleaned):
        # ISBN-13은 상품번호가 아니므로 알라딘 통합검색으로 보낸다.
        return None
    if re.fullmatch(r"\d{6,12}", cleaned):
        return cleaned

    return None


def validate_aladin_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise AladinLookupError("알라딘 상품 URL은 http 또는 https로 입력해 주세요.")
    if parsed.hostname not in {ALADIN_HOST, "aladin.co.kr"}:
        raise AladinLookupError("알라딘 도메인의 URL만 사용할 수 있습니다.")
    return value


def build_detail_url(query: str) -> str:
    item_id = extract_item_id(query)
    if item_id:
        return ALADIN_DETAIL_URL.format(item_id=item_id)

    parsed = urlparse(query)
    if parsed.scheme and parsed.netloc:
        return validate_aladin_url(query)

    return ALADIN_SEARCH_URL.format(keyword=quote_plus(query))


def _session():
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise AladinLookupError(
            "순위 밖 시리즈 검색에는 requests가 필요합니다. "
            "requirements.txt를 설치해 주세요."
        ) from exc

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


def _soup(response):
    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:
        raise AladinLookupError(
            "순위 밖 시리즈 검색에는 beautifulsoup4가 필요합니다. "
            "requirements.txt를 설치해 주세요."
        ) from exc

    return BeautifulSoup(response.content, "html.parser")


def _get_page(session, url: str):
    validate_aladin_url(url)
    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        raise AladinLookupError(
            "알라딘 페이지를 읽지 못했습니다. URL이나 네트워크 상태를 확인해 주세요."
        ) from exc
    return _soup(response)


def _first_product_url(soup) -> str | None:
    for link in soup.select("a.bo3[href]"):
        href = link.get("href", "")
        if "wproduct.aspx" in href.lower() and re.search(
            r"itemid=\d+", href, re.IGNORECASE
        ):
            return urljoin("https://www.aladin.co.kr", href)
    return None


def _series_link(soup):
    links = soup.select(
        'a[href*="mseriesitem.aspx"], '
        'a[href*="wseriesitem.aspx"]'
    )
    for link in links:
        href = link.get("href", "")
        if re.search(r"[?&]srid=\d+", href, re.IGNORECASE):
            return link
    return None


def _series_name(link) -> str:
    text = clean_space(link.get_text(" ", strip=True))
    text = re.sub(r"\s*\(\s*총\s*\d+\s*권.*?\)", "", text)
    return text.strip()


def _volume_from_text(value: str) -> int | None:
    value = clean_space(value)
    values = [
        int(number)
        for number in re.findall(r"(?<!전)(?<!\d)(\d+)\s*권", value)
    ]
    range_values = re.findall(r"(\d+)\s*[~～-]\s*(\d+)", value)
    for start, end in range_values:
        values.extend([int(start), int(end)])

    if values:
        return max(values)

    # 제목 끝의 단일 숫자도 보조적으로 인식한다. 전5권 같은 세트 표기는 제외한다.
    match = re.search(r"(?:^|\s)(\d+)(?:\s|$|-)", value)
    return int(match.group(1)) if match else None


def _total_volume_from_link(link) -> int | None:
    match = re.search(r"총\s*(\d+)\s*권", link.get_text(" ", strip=True))
    return int(match.group(1)) if match else None


def lookup_aladin_series(query: str) -> AladinSeriesLookup:
    """상품 URL·상품번호·ISBN·검색어로 시리즈와 최신 권수를 찾는다."""
    query = query.strip()
    if not query:
        raise AladinLookupError(
            "알라딘 상품 URL, ISBN, 상품번호 또는 검색어를 입력해 주세요."
        )

    session = _session()
    initial_url = build_detail_url(query)
    initial_soup = _get_page(session, initial_url)

    detail_url = initial_url
    if "wsearchresult.aspx" in initial_url.lower():
        detail_url = _first_product_url(initial_soup)
        if detail_url is None:
            raise AladinLookupError("알라딘 검색 결과에서 상품을 찾지 못했습니다.")
        detail_soup = _get_page(session, detail_url)
    else:
        detail_soup = initial_soup

    series_link = _series_link(detail_soup)
    product_title_node = detail_soup.select_one("a.bo3")
    product_title = (
        clean_space(product_title_node.get_text(" ", strip=True))
        if product_title_node is not None
        else ""
    )

    if series_link is None:
        fallback_name = re.sub(
            r"\s+\d+(?:\s*권)?(?:\s|$).*",
            "",
            product_title,
        )
        fallback_name = clean_space(fallback_name) or clean_space(query)
        return AladinSeriesLookup(
            series_name=fallback_name,
            latest_volume_no=_volume_from_text(product_title),
            source_url=detail_url,
        )

    series_name = _series_name(series_link)
    series_url = urljoin("https://www.aladin.co.kr", series_link.get("href", ""))
    latest_volume_no = _total_volume_from_link(series_link)

    try:
        series_soup = _get_page(session, series_url)
    except AladinLookupError:
        series_soup = None

    if series_soup is not None:
        volume_values: list[int] = []
        for link in series_soup.select("a.bo3, a[href*='wproduct.aspx']"):
            volume = _volume_from_text(link.get_text(" ", strip=True))
            if volume is not None:
                volume_values.append(volume)
        if volume_values:
            page_latest = max(volume_values)
            latest_volume_no = max(latest_volume_no or 0, page_latest)

    return AladinSeriesLookup(
        series_name=series_name,
        latest_volume_no=latest_volume_no,
        source_url=detail_url,
    )
