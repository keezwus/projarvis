MINUTES_PER_SLOT = 15
SLOTS_PER_HOUR = 60 // MINUTES_PER_SLOT  # 4
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR      # 96
SLOTS_PER_WEEK = 7 * SLOTS_PER_DAY       # 672

DAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def hhmm_to_minutes(hhmm: str) -> int:
    """Convert HH:MM string to minutes since midnight."""
    try:
        hours, minutes = hhmm.split(":")
        return int(hours) * 60 + int(minutes)
    except ValueError:
        raise ValueError(f"Invalid HH:MM format: {hhmm!r}")


def minutes_to_hhmm(minutes: int) -> str:
    """Convert minutes since midnight to HH:MM string."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def hhmm_to_slot(hhmm: str) -> int:
    """Convert HH:MM to real slot index (0-95 per day)."""
    return hhmm_to_minutes(hhmm) // MINUTES_PER_SLOT


def slot_to_hhmm(slot: int) -> str:
    """Convert real slot index (0-95) to HH:MM string."""
    return minutes_to_hhmm(slot * MINUTES_PER_SLOT)
