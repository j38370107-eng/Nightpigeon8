import re
from datetime import timedelta

MAX_DURATION_DAYS = 180

DURATION_PATTERN = re.compile(
    r"^(\d+)(s|m|h|d|w|mo|y)$", re.IGNORECASE
)

UNIT_MAP = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "mo": 86400 * 30,
    "y": 86400 * 365,
}


def parse_duration(text: str) -> timedelta | None:
    """
    Parse a duration string into a timedelta.
    Returns None for 'permanent'/'perm'.
    Raises ValueError if over 180 days or invalid format.
    """
    if not text:
        return None

    text = text.strip().lower()

    if text in ("permanent", "perm"):
        return None

    match = DURATION_PATTERN.match(text)
    if not match:
        raise ValueError(
            f"Invalid duration format: `{text}`. "
            f"Use formats like: 30s, 5m, 2h, 7d, 1w, 1mo, 1y"
        )

    amount = int(match.group(1))
    unit = match.group(2).lower()
    seconds = amount * UNIT_MAP[unit]

    if seconds > MAX_DURATION_DAYS * 86400:
        raise ValueError(
            f"Duration cannot exceed {MAX_DURATION_DAYS} days."
        )

    return timedelta(seconds=seconds)


def format_duration(td: timedelta | None) -> str:
    """Format a timedelta into a human-readable string."""
    if td is None:
        return "permanent"

    total = int(td.total_seconds())
    if total <= 0:
        return "0s"

    parts = []
    units = [
        ("y", 365 * 86400),
        ("mo", 30 * 86400),
        ("w", 7 * 86400),
        ("d", 86400),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    ]
    for suffix, secs in units:
        if total >= secs:
            val = total // secs
            total %= secs
            parts.append(f"{val}{suffix}")
    return " ".join(parts) if parts else "0s"
