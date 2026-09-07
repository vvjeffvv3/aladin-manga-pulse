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
