from django.core.paginator import Paginator

from dashboard.repository.book_repository import search_books
from dashboard.service.formatting import format_release_date
from dashboard.service.owned_series_service import (
    decorate_book_collection_status,
    get_latest_volume_map,
)


def get_search_result(
    snapshot_time,
    keyword: str = "",
    search_field: str = "all",
    sort_by: str = "rank",
    direction: str = "asc",
    page_number: int = 1,
    page_size: int = 50,
):
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 50

    page_size = max(1, min(page_size, 100))

    books = search_books(
        snapshot_time=snapshot_time,
        keyword=keyword,
        search_field=search_field,
        sort_by=sort_by,
        descending=direction == "desc",
    )

    paginator = Paginator(books, page_size)
    page_obj = paginator.get_page(page_number)

    series_ids = {
        snapshot.book.series_id
        for snapshot in page_obj
        if snapshot.book.series_id is not None
    }
    latest_volume_by_series = get_latest_volume_map(series_ids)
    for snapshot in page_obj:
        snapshot.release_date_display = format_release_date(snapshot.book.release_date)
        snapshot.latest_series_volume_no = latest_volume_by_series.get(
            snapshot.book.series_id
        )
    decorate_book_collection_status(page_obj)

    return {
        "page_obj": page_obj,
        "keyword": keyword,
        "search_field": search_field,
        "sort_by": sort_by,
        "direction": direction,
    }
