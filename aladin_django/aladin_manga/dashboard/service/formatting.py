import re


DATE_PATTERN = re.compile(
    r"^(?P<year>\d{4})[-./](?P<month>\d{1,2})"
    r"(?:[-./](?P<day>\d{1,2}))?$"
)


def format_release_date(value) -> str:
    """발매일을 화면용 연·월 형식으로 바꾼다."""
    text = str(value or "").strip()
    if not text:
        return "-"

    match = DATE_PATTERN.fullmatch(text)
    if match is None:
        return text

    year = int(match.group("year"))
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        return text

    return f"{year:04d}.{month:02d}"
