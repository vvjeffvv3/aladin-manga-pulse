"""Gold CSV 데이터를 MySQL에 적재한다.

설치:
    python -m pip install mysql-connector-python

프로젝트 루트의 .env 또는 환경변수:
    ALADIN_MYSQL_HOST=127.0.0.1
    ALADIN_MYSQL_PORT=3306
    ALADIN_MYSQL_USER=root
    ALADIN_MYSQL_PASSWORD=비밀번호
    ALADIN_MYSQL_DATABASE=aladin_manga

실행:
    python mysql_loader.py --dry-run
    python mysql_loader.py

MySQL에는 Silver 기본 정보와 날짜별 스냅샷, Gold 시리즈 집계를 각각
series/books/book_snapshots/series_daily_stats 테이블에 저장하고,
보유 시리즈 정보는 owned_series 테이블에 별도로 저장한다.
수집 시각은 현재 CSV의 KST 값을 MySQL DATETIME에 KST 기준으로 저장한다.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from daily_snapshot import deduplicate_daily_rows


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
SCHEMA_PATH = BASE_DIR / "mysql_schema.sql"
DEFAULT_BOOK_INPUT = BASE_DIR / "gold" / "manga_trend.csv"
DEFAULT_SERIES_INPUT = BASE_DIR / "gold" / "popular_series.csv"
KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None or not value.strip():
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None or not value.strip():
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except InvalidOperation:
        return None


def nullable_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def parse_mysql_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        # MySQL DATETIME에는 시간대 정보가 없으므로 KST 시각만 저장한다.
        parsed = parsed.astimezone(KST).replace(tzinfo=None)
    return parsed


def load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        fields = reader.fieldnames or []
        rows = [
            {key: (value or "") for key, value in row.items()}
            for row in reader
        ]
    return rows, fields


def validate_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError(
            "MySQL 데이터베이스 이름은 영문·숫자·밑줄만 사용할 수 있습니다."
        )
    return value


def read_schema_statements() -> list[str]:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"MySQL 스키마 파일을 찾을 수 없습니다: {SCHEMA_PATH}")

    schema_lines = [
        line
        for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    ]
    schema = "\n".join(schema_lines)
    return [statement.strip() for statement in schema.split(";") if statement.strip()]


def connect_database(config: DatabaseConfig) -> Any:
    try:
        import mysql.connector
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "mysql-connector-python이 필요합니다. "
            "'python -m pip install mysql-connector-python'을 실행하세요."
        ) from exc

    database = validate_identifier(config.database)
    server_connection = mysql.connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
    )
    try:
        cursor = server_connection.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.close()
        server_connection.commit()
    finally:
        server_connection.close()

    return mysql.connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=database,
    )


def create_tables(connection: Any) -> None:
    cursor = connection.cursor()
    try:
        for statement in read_schema_statements():
            cursor.execute(statement)
        connection.commit()
    finally:
        cursor.close()


def _primary_key_columns(cursor: Any, database: str, table_name: str) -> list[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.statistics
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND INDEX_NAME = 'PRIMARY'
        ORDER BY SEQ_IN_INDEX
        """,
        (database, table_name),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _has_column(
    cursor: Any,
    database: str,
    table_name: str,
    column_name: str,
) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (database, table_name, column_name),
    )
    return bool(cursor.fetchone()[0])


def migrate_daily_snapshot_keys(connection: Any, database: str) -> None:
    """기존 시각 복합키를 식별자·수집일 복합키로 바꾸고 중복을 제거한다."""
    daily_tables = (
        ("book_snapshots", "item_id"),
        ("series_daily_stats", "series_id"),
    )
    cursor = connection.cursor()
    try:
        for table_name, identity_column in daily_tables:
            if not _has_column(
                cursor,
                database,
                table_name,
                "collected_date",
            ):
                cursor.execute(
                    f"""
                    ALTER TABLE `{table_name}`
                    ADD COLUMN `collected_date`
                        DATE GENERATED ALWAYS AS (DATE(`collected_at`)) STORED
                        AFTER `collected_at`
                    """
                )

            primary_key = _primary_key_columns(cursor, database, table_name)
            expected_key = [identity_column, "collected_date"]
            if primary_key == expected_key:
                continue

            # 같은 식별자·같은 날짜에 여러 행이 있으면 최신 시각만 남긴다.
            cursor.execute(
                f"""
                DELETE older
                FROM `{table_name}` AS older
                INNER JOIN `{table_name}` AS newer
                    ON older.`{identity_column}` = newer.`{identity_column}`
                   AND older.`collected_date` = newer.`collected_date`
                   AND older.`collected_at` < newer.`collected_at`
                """
            )
            cursor.execute(
                f"""
                ALTER TABLE `{table_name}`
                DROP PRIMARY KEY,
                ADD PRIMARY KEY (`{identity_column}`, `collected_date`)
                """
            )

        connection.commit()
    finally:
        cursor.close()


def ensure_series_id(
    cursor: Any,
    series_name: str,
    series_cache: dict[str, int],
) -> Optional[int]:
    cleaned_name = series_name.strip()
    if not cleaned_name:
        return None
    if cleaned_name in series_cache:
        return series_cache[cleaned_name]

    cursor.execute(
        """
        INSERT INTO series (series_name)
        VALUES (%s)
        ON DUPLICATE KEY UPDATE series_name = VALUES(series_name)
        """,
        (cleaned_name,),
    )
    cursor.execute(
        "SELECT series_id FROM series WHERE series_name = %s",
        (cleaned_name,),
    )
    result = cursor.fetchone()
    if result is None:
        raise RuntimeError(f"시리즈 ID를 확인할 수 없습니다: {cleaned_name}")

    series_id = int(result[0])
    series_cache[cleaned_name] = series_id
    return series_id


def upsert_books(
    cursor: Any,
    rows: list[dict[str, str]],
    series_cache: dict[str, int],
) -> int:
    unique_books: dict[str, dict[str, str]] = {}
    for row in rows:
        item_id = row.get("item_id", "").strip()
        if not item_id:
            raise ValueError("item_id가 비어 있는 Gold 행이 있습니다.")
        unique_books[item_id] = row

    parameters = []
    for item_id, row in unique_books.items():
        series_id = ensure_series_id(
            cursor,
            row.get("series_name", ""),
            series_cache,
        )
        parameters.append(
            (
                item_id,
                series_id,
                row.get("title", "").strip(),
                nullable_text(row.get("vol_no")),
                nullable_text(row.get("edition_type")),
                nullable_text(row.get("special_benefits")),
                nullable_text(row.get("author")),
                nullable_text(row.get("publisher")),
                nullable_text(row.get("release_date")),
            )
        )

    if not parameters:
        return 0

    cursor.executemany(
        """
        INSERT INTO books (
            item_id, series_id, title, vol_no, edition_type,
            special_benefits, author, publisher, release_date
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            series_id = VALUES(series_id),
            title = VALUES(title),
            vol_no = VALUES(vol_no),
            edition_type = VALUES(edition_type),
            special_benefits = VALUES(special_benefits),
            author = VALUES(author),
            publisher = VALUES(publisher),
            release_date = VALUES(release_date)
        """,
        parameters,
    )
    return len(parameters)


def upsert_book_snapshots(cursor: Any, rows: list[dict[str, str]]) -> int:
    parameters = []
    for row in rows:
        item_id = row.get("item_id", "").strip()
        if not item_id:
            raise ValueError("item_id가 비어 있는 Gold 행이 있습니다.")

        parameters.append(
            (
                item_id,
                parse_mysql_datetime(row["collected_at"]),
                parse_int(row.get("rank")),
                parse_int(row.get("price")),
                parse_decimal(row.get("rating")),
                parse_int(row.get("sales_point")),
                parse_int(row.get("previous_rank")),
                parse_int(row.get("rank_change")),
                parse_int(row.get("previous_sales_point")),
                parse_int(row.get("sales_point_change")),
                parse_int(row.get("is_new")) or 0,
                parse_int(row.get("is_out")) or 0,
            )
        )

    if not parameters:
        return 0

    cursor.executemany(
        """
        INSERT INTO book_snapshots (
            item_id, collected_at, rank_no, price, rating, sales_point,
            previous_rank, rank_change, previous_sales_point,
            sales_point_change, is_new, is_out
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            collected_at = VALUES(collected_at),
            rank_no = VALUES(rank_no),
            price = VALUES(price),
            rating = VALUES(rating),
            sales_point = VALUES(sales_point),
            previous_rank = VALUES(previous_rank),
            rank_change = VALUES(rank_change),
            previous_sales_point = VALUES(previous_sales_point),
            sales_point_change = VALUES(sales_point_change),
            is_new = VALUES(is_new),
            is_out = VALUES(is_out)
        """,
        parameters,
    )
    return len(parameters)


def upsert_series_stats(
    cursor: Any,
    rows: list[dict[str, str]],
    series_cache: dict[str, int],
) -> int:
    parameters = []
    for row in rows:
        series_id = ensure_series_id(
            cursor,
            row.get("series_name", ""),
            series_cache,
        )
        if series_id is None:
            continue

        parameters.append(
            (
                series_id,
                parse_mysql_datetime(row["collected_at"]),
                parse_int(row.get("series_rank")) or 0,
                parse_int(row.get("volume_count")) or 0,
                parse_int(row.get("best_rank")),
                parse_decimal(row.get("avg_rank")),
                parse_int(row.get("total_sales_point")),
                parse_decimal(row.get("avg_sales_point")),
            )
        )

    if not parameters:
        return 0

    cursor.executemany(
        """
        INSERT INTO series_daily_stats (
            series_id, collected_at, series_rank, volume_count,
            best_rank, avg_rank, total_sales_point, avg_sales_point
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            collected_at = VALUES(collected_at),
            series_rank = VALUES(series_rank),
            volume_count = VALUES(volume_count),
            best_rank = VALUES(best_rank),
            avg_rank = VALUES(avg_rank),
            total_sales_point = VALUES(total_sales_point),
            avg_sales_point = VALUES(avg_sales_point)
        """,
        parameters,
    )
    return len(parameters)


def build_config(args: argparse.Namespace) -> DatabaseConfig:
    return DatabaseConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="알라딘 Gold 데이터를 MySQL에 적재")
    parser.add_argument("--book-input", type=Path, default=DEFAULT_BOOK_INPUT)
    parser.add_argument("--series-input", type=Path, default=DEFAULT_SERIES_INPUT)
    parser.add_argument("--host", default=os.getenv("ALADIN_MYSQL_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ALADIN_MYSQL_PORT", "3306")),
    )
    parser.add_argument("--user", default=os.getenv("ALADIN_MYSQL_USER", "root"))
    parser.add_argument(
        "--password",
        default=os.getenv("ALADIN_MYSQL_PASSWORD", ""),
    )
    parser.add_argument(
        "--database",
        default=os.getenv("ALADIN_MYSQL_DATABASE", "aladin_manga"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="MySQL에 접속하지 않고 입력 CSV만 검증",
    )
    args = parser.parse_args()

    book_rows, book_fields = load_csv(args.book_input)
    series_rows, series_fields = load_csv(args.series_input)

    required_book_fields = {
        "item_id",
        "title",
        "collected_at",
        "rank",
        "sales_point",
    }
    required_series_fields = {
        "collected_at",
        "series_name",
        "series_rank",
        "volume_count",
    }
    if not required_book_fields.issubset(book_fields):
        missing = ", ".join(sorted(required_book_fields - set(book_fields)))
        raise ValueError(f"도서 Gold CSV 필수 컬럼이 없습니다: {missing}")
    if not required_series_fields.issubset(series_fields):
        missing = ", ".join(sorted(required_series_fields - set(series_fields)))
        raise ValueError(f"시리즈 Gold CSV 필수 컬럼이 없습니다: {missing}")

    book_rows = deduplicate_daily_rows(
        book_rows,
        identity_fields=("item_id", "title"),
    )
    series_rows = deduplicate_daily_rows(
        series_rows,
        identity_fields=("series_name",),
    )

    if args.dry_run:
        print(f"도서 Gold 행: {len(book_rows)}개")
        print(f"시리즈 Gold 행: {len(series_rows)}개")
        print("입력 CSV 검증을 완료했습니다.")
        return

    config = build_config(args)
    connection = connect_database(config)
    try:
        create_tables(connection)
        migrate_daily_snapshot_keys(connection, config.database)
        cursor = connection.cursor()
        try:
            series_cache: dict[str, int] = {}
            book_count = upsert_books(cursor, book_rows, series_cache)
            snapshot_count = upsert_book_snapshots(cursor, book_rows)
            series_stat_count = upsert_series_stats(
                cursor,
                series_rows,
                series_cache,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    print(f"books 적재: {book_count}개")
    print(f"book_snapshots 적재: {snapshot_count}개")
    print(f"series_daily_stats 적재: {series_stat_count}개")
    print(f"MySQL 데이터베이스: {config.database}")


if __name__ == "__main__":
    main()
