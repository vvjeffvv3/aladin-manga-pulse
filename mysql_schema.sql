CREATE TABLE IF NOT EXISTS series (
    series_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    series_name VARCHAR(255) NOT NULL,
    PRIMARY KEY (series_id),
    UNIQUE KEY uq_series_name (series_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS owned_series (
    owned_series_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    series_id BIGINT UNSIGNED NOT NULL,
    owned_volume_no INT UNSIGNED NOT NULL DEFAULT 0,
    latest_volume_no INT UNSIGNED NULL,
    latest_checked_at DATETIME NULL,
    source_url VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (owned_series_id),
    UNIQUE KEY uq_owned_series_series_id (series_id),
    CONSTRAINT fk_owned_series_series
        FOREIGN KEY (series_id) REFERENCES series(series_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS owned_series_volumes (
    owned_series_id BIGINT UNSIGNED NOT NULL,
    volume_no INT UNSIGNED NOT NULL,
    PRIMARY KEY (owned_series_id, volume_no),
    CONSTRAINT fk_owned_series_volumes_owned_series
        FOREIGN KEY (owned_series_id) REFERENCES owned_series(owned_series_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS owned_folders (
    folder_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    folder_name VARCHAR(100) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (folder_id),
    UNIQUE KEY uq_owned_folders_folder_name (folder_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS owned_series_folders (
    owned_series_id BIGINT UNSIGNED NOT NULL,
    folder_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (owned_series_id),
    KEY idx_owned_series_folders_folder_id (folder_id),
    CONSTRAINT fk_owned_series_folders_owned_series
        FOREIGN KEY (owned_series_id) REFERENCES owned_series(owned_series_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_owned_series_folders_folder
        FOREIGN KEY (folder_id) REFERENCES owned_folders(folder_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS owned_series_positions (
    owned_series_id BIGINT UNSIGNED NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    PRIMARY KEY (owned_series_id),
    CONSTRAINT fk_owned_series_positions_owned_series
        FOREIGN KEY (owned_series_id) REFERENCES owned_series(owned_series_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS books (
    item_id VARCHAR(32) NOT NULL,
    series_id BIGINT UNSIGNED NULL,
    title VARCHAR(500) NOT NULL,
    vol_no VARCHAR(50) NULL,
    edition_type VARCHAR(255) NULL,
    special_benefits TEXT NULL,
    author VARCHAR(500) NULL,
    publisher VARCHAR(255) NULL,
    release_date VARCHAR(10) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id),
    KEY idx_books_series_id (series_id),
    CONSTRAINT fk_books_series
        FOREIGN KEY (series_id) REFERENCES series(series_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS book_snapshots (
    item_id VARCHAR(32) NOT NULL,
    collected_at DATETIME NOT NULL,
    collected_date DATE GENERATED ALWAYS AS (DATE(collected_at)) STORED,
    rank_no INT NULL,
    price INT NULL,
    rating DECIMAL(4,2) NULL,
    sales_point BIGINT NULL,
    previous_rank INT NULL,
    rank_change INT NULL,
    previous_sales_point BIGINT NULL,
    sales_point_change BIGINT NULL,
    is_new TINYINT(1) NOT NULL DEFAULT 0,
    is_out TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, collected_date),
    KEY idx_book_snapshots_collected_at (collected_at),
    KEY idx_book_snapshots_rank_no (rank_no),
    CONSTRAINT fk_book_snapshots_book
        FOREIGN KEY (item_id) REFERENCES books(item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS series_daily_stats (
    series_id BIGINT UNSIGNED NOT NULL,
    collected_at DATETIME NOT NULL,
    collected_date DATE GENERATED ALWAYS AS (DATE(collected_at)) STORED,
    series_rank INT NOT NULL,
    volume_count INT NOT NULL,
    best_rank INT NULL,
    avg_rank DECIMAL(10,2) NULL,
    total_sales_point BIGINT NULL,
    avg_sales_point DECIMAL(14,2) NULL,
    PRIMARY KEY (series_id, collected_date),
    KEY idx_series_stats_collected_at (collected_at),
    KEY idx_series_stats_rank (series_rank),
    CONSTRAINT fk_series_stats_series
        FOREIGN KEY (series_id) REFERENCES series(series_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
