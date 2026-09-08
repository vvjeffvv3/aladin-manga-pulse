from datetime import datetime

from django.db.models import CharField, Q, QuerySet
from django.db.models.functions import Cast

from dashboard.models import BookSnapshot


TEXT_SEARCH_FIELDS = {
    "item_id": "book__item_id",
    "title": "book__title",
    "series_name": "book__series__series_name",
    "vol_no": "book__vol_no",
    "edition_type": "book__edition_type",
    "special_benefits": "book__special_benefits",
    "author": "book__author",
    "publisher": "book__publisher",
    "release_date": "book__release_date",
}

NUMERIC_SEARCH_FIELDS = {
    "price": "price_text",
    "rating": "rating_text",
    "sales_point": "sales_point_text",
    "rank": "rank_text",
}

SORT_FIELDS = {
    "rank": "rank_no",
    "price": "price",
    "rating": "rating",
    "sales_point": "sales_point",
}


def get_snapshot_times():
    return (
        BookSnapshot.objects
        .filter(is_out=False)
        .values_list("collected_at", flat=True)
        .distinct()
        .order_by("-collected_at")
    )


def get_latest_snapshot_time() -> datetime | None:
    return get_snapshot_times().first()


def get_previous_snapshot_time() -> datetime | None:
    snapshot_times = list(get_snapshot_times()[:2])
    return snapshot_times[1] if len(snapshot_times) == 2 else None


def search_books(
    snapshot_time: datetime,
    keyword: str = "",
    search_field: str = "all",
    sort_by: str = "rank",
    descending: bool = False,
    include_out: bool = False,
) -> QuerySet[BookSnapshot]:
    queryset = BookSnapshot.objects.select_related(
        "book",
        "book__series",
    ).filter(collected_at=snapshot_time)

    if not include_out:
        queryset = queryset.filter(is_out=False)

    keyword = keyword.strip()

    if keyword:
        queryset = queryset.annotate(
            price_text=Cast("price", output_field=CharField()),
            rating_text=Cast("rating", output_field=CharField()),
            sales_point_text=Cast("sales_point", output_field=CharField()),
            rank_text=Cast("rank_no", output_field=CharField()),
        )

        if search_field == "all":
            search_query = Q()

            for field_name in TEXT_SEARCH_FIELDS.values():
                search_query |= Q(**{f"{field_name}__icontains": keyword})

            for field_name in NUMERIC_SEARCH_FIELDS.values():
                search_query |= Q(**{f"{field_name}__icontains": keyword})

            queryset = queryset.filter(search_query)

        elif search_field in TEXT_SEARCH_FIELDS:
            field_name = TEXT_SEARCH_FIELDS[search_field]
            queryset = queryset.filter(
                **{f"{field_name}__icontains": keyword}
            )

        elif search_field in NUMERIC_SEARCH_FIELDS:
            field_name = NUMERIC_SEARCH_FIELDS[search_field]
            queryset = queryset.filter(
                **{f"{field_name}__icontains": keyword}
            )

    sort_field = SORT_FIELDS.get(sort_by, "rank_no")
    order_field = f"-{sort_field}" if descending else sort_field

    return queryset.order_by(order_field, "book_id")
