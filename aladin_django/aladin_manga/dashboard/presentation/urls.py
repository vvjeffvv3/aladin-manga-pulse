from django.urls import path

from . import views


app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search_dashboard, name="search"),
    path(
        "books/<str:item_id>/owned/",
        views.add_book_to_owned_view,
        name="add_book_to_owned",
    ),
    path(
        "books/<str:item_id>/interest/",
        views.add_book_to_interest_view,
        name="add_book_to_interest",
    ),
    path(
        "interest-series/",
        views.interest_series_dashboard,
        name="interest_series",
    ),
    path("owned-series/", views.owned_series_dashboard, name="owned_series"),
    path(
        "interest-series/add/",
        views.add_interest_series,
        name="add_interest_series",
    ),
    path(
        "interest-series/add-external/",
        views.add_interest_series_external,
        name="add_interest_series_external",
    ),
    path("owned-series/add/", views.add_owned_series, name="add_owned_series"),
    path(
        "owned-series/add-external/",
        views.add_owned_series_external,
        name="add_owned_series_external",
    ),
    path(
        "owned-folders/add/",
        views.create_owned_folder_view,
        name="add_owned_folder",
    ),
    path(
        "owned-folders/reorder/",
        views.reorder_owned_folders_view,
        name="reorder_owned_folders",
    ),
    path(
        "owned-folders/<int:folder_id>/rename/",
        views.rename_owned_folder_view,
        name="rename_owned_folder",
    ),
    path(
        "owned-folders/<int:folder_id>/delete/",
        views.delete_owned_folder_view,
        name="delete_owned_folder",
    ),
    path(
        "owned-series/reorder/",
        views.reorder_owned_series_view,
        name="reorder_owned_series",
    ),
    path(
        "owned-series/<int:owned_series_id>/volume/",
        views.update_owned_series_volume,
        name="update_owned_series_volume",
    ),
    path(
        "interest-series/<int:owned_series_id>/move-owned/",
        views.move_interest_to_owned_view,
        name="move_interest_to_owned",
    ),
    path(
        "owned-series/<int:owned_series_id>/refresh/",
        views.refresh_owned_series_view,
        name="refresh_owned_series",
    ),
    path(
        "owned-series/<int:owned_series_id>/remove/",
        views.remove_owned_series_view,
        name="remove_owned_series",
    ),
]
