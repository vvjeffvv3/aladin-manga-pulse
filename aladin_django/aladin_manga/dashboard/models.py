from django.db import models
from django.utils import timezone


class Series(models.Model):
    series_id = models.BigAutoField(
        primary_key=True,
        db_column="series_id",
    )
    series_name = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "series"


class OwnedSeries(models.Model):
    owned_series_id = models.BigAutoField(
        primary_key=True,
        db_column="owned_series_id",
    )
    series = models.OneToOneField(
        Series,
        db_column="series_id",
        on_delete=models.DO_NOTHING,
        related_name="owned_series_record",
    )
    owned_volume_no = models.PositiveIntegerField(default=0)
    latest_volume_no = models.PositiveIntegerField(null=True, blank=True)
    latest_checked_at = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "owned_series"


class OwnedSeriesVolume(models.Model):
    owned_series = models.ForeignKey(
        OwnedSeries,
        db_column="owned_series_id",
        on_delete=models.CASCADE,
        related_name="owned_volumes",
    )
    volume_no = models.PositiveIntegerField()

    pk = models.CompositePrimaryKey("owned_series", "volume_no")

    class Meta:
        managed = False
        db_table = "owned_series_volumes"


class OwnedFolder(models.Model):
    folder_id = models.BigAutoField(
        primary_key=True,
        db_column="folder_id",
    )
    folder_name = models.CharField(max_length=100, unique=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "owned_folders"


class OwnedSeriesFolder(models.Model):
    owned_series = models.OneToOneField(
        OwnedSeries,
        primary_key=True,
        db_column="owned_series_id",
        on_delete=models.CASCADE,
        related_name="folder_link",
    )
    folder = models.ForeignKey(
        OwnedFolder,
        db_column="folder_id",
        on_delete=models.CASCADE,
        related_name="series_links",
    )

    class Meta:
        managed = False
        db_table = "owned_series_folders"


class OwnedSeriesPosition(models.Model):
    owned_series = models.OneToOneField(
        OwnedSeries,
        primary_key=True,
        db_column="owned_series_id",
        on_delete=models.CASCADE,
        related_name="position_record",
    )
    sort_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "owned_series_positions"


class Book(models.Model):
    item_id = models.CharField(
        max_length=32,
        primary_key=True,
    )
    series = models.ForeignKey(
        Series,
        db_column="series_id",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="books",
    )
    title = models.CharField(max_length=500)
    vol_no = models.CharField(max_length=50, null=True, blank=True)
    edition_type = models.CharField(max_length=255, null=True, blank=True)
    special_benefits = models.TextField(null=True, blank=True)
    author = models.CharField(max_length=500, null=True, blank=True)
    publisher = models.CharField(max_length=255, null=True, blank=True)
    release_date = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "books"


class BookSnapshot(models.Model):
    book = models.ForeignKey(
        Book,
        db_column="item_id",
        on_delete=models.DO_NOTHING,
        related_name="snapshots",
    )
    collected_at = models.DateTimeField()
    collected_date = models.DateField(editable=False)
    rank_no = models.IntegerField(null=True, blank=True)
    price = models.IntegerField(null=True, blank=True)
    rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
    )
    sales_point = models.BigIntegerField(null=True, blank=True)
    previous_rank = models.IntegerField(null=True, blank=True)
    rank_change = models.IntegerField(null=True, blank=True)
    previous_sales_point = models.BigIntegerField(null=True, blank=True)
    sales_point_change = models.BigIntegerField(null=True, blank=True)
    is_new = models.BooleanField()
    is_out = models.BooleanField()

    pk = models.CompositePrimaryKey("book", "collected_date")

    class Meta:
        managed = False
        db_table = "book_snapshots"


class SeriesDailyStat(models.Model):
    series = models.ForeignKey(
        Series,
        db_column="series_id",
        on_delete=models.DO_NOTHING,
        related_name="daily_stats",
    )
    collected_at = models.DateTimeField()
    collected_date = models.DateField(editable=False)
    series_rank = models.IntegerField()
    volume_count = models.IntegerField()
    best_rank = models.IntegerField(null=True, blank=True)
    avg_rank = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    total_sales_point = models.BigIntegerField(null=True, blank=True)
    avg_sales_point = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    pk = models.CompositePrimaryKey("series", "collected_date")

    class Meta:
        managed = False
        db_table = "series_daily_stats"
