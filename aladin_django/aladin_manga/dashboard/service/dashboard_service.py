from dashboard.repository.book_repository import (
    get_latest_snapshot_time,
    get_previous_snapshot_time,
    search_books,
)
from dashboard.repository.series_repository import get_top_series
from dashboard.service.formatting import format_release_date
from dashboard.service.owned_series_service import decorate_book_collection_status


def set_rank_status(book):
    if book.is_new:
        book.rank_status = "new"
    elif book.rank_change is None:
        book.rank_status = "baseline"
    elif book.rank_change > 0:
        book.rank_status = "up"
    elif book.rank_change < 0:
        book.rank_status = "down"
    else:
        book.rank_status = "same"

    return book


def get_home_dashboard(
    book_limit: int = 50,
    series_limit: int = 10,
):
    latest_snapshot = get_latest_snapshot_time()

    if latest_snapshot is None:
        return {
            "latest_snapshot": None,
            "previous_snapshot": None,
            "books": [],
            "series": [],
        }

    previous_snapshot = get_previous_snapshot_time()

    books = list(
        search_books(
            snapshot_time=latest_snapshot,
            sort_by="rank",
            descending=False,
        )[:book_limit]
    )

    for book in books:
        set_rank_status(book)
        book.release_date_display = format_release_date(book.book.release_date)
    decorate_book_collection_status(books)

    series = list(
        get_top_series(
            snapshot_time=latest_snapshot,
            limit=series_limit,
        )
    )

    return {
        "latest_snapshot": latest_snapshot,
        "previous_snapshot": previous_snapshot,
        "books": books,
        "series": series,
    }
