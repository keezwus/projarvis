from datetime import datetime, timedelta

from projarvis.planner.exceptions import TimeMappingError

# ── module-level constants ──────────────────────────────────────

MINUTES_PER_SLOT = 15
SLOTS_PER_HOUR = 60 // MINUTES_PER_SLOT   # 4
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR       # 96
SLOTS_PER_WEEK = 7 * SLOTS_PER_DAY        # 672

DAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

# ── module-level pure functions (no epoch, intra-day only) ─────

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
    """Convert HH:MM to slot index within a single day (0-95)."""
    return hhmm_to_minutes(hhmm) // MINUTES_PER_SLOT


def slot_to_hhmm(slot: int) -> str:
    """Convert slot index (0-95) to HH:MM string."""
    return minutes_to_hhmm(slot * MINUTES_PER_SLOT)


def is_iso_datetime(s: str) -> bool:
    """Return True if *s* looks like an ISO 8601 datetime string."""
    if not isinstance(s, str):
        return False
    if "T" not in s:
        return False
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        return False


# ── TimeEpoch ───────────────────────────────────────────────────

class TimeEpoch:
    """Real-slot timeline anchored at horizon_start.

    Real slot 0 = horizon_start. Each slot = 15 minutes.
    Slots count upward monotonically; real slots are absolute across
    the entire horizon.
    """

    def __init__(self, horizon_start: str) -> None:
        self._epoch_start = datetime.fromisoformat(horizon_start)
        if not _is_aligned(self._epoch_start):
            raise TimeMappingError(
                f"horizon_start {horizon_start!r} is not aligned to "
                f"{MINUTES_PER_SLOT}-minute slots"
            )

    # ── core conversions ────────────────────────────────────────

    def iso_to_real_slot(self, iso: str) -> int:
        dt = datetime.fromisoformat(iso)
        delta = dt - self._epoch_start
        total_minutes = delta.days * 24 * 60 + delta.seconds // 60
        if total_minutes < 0:
            raise TimeMappingError(
                f"Time {iso!r} is before epoch start "
                f"{self._epoch_start.isoformat()}"
            )
        if total_minutes % MINUTES_PER_SLOT != 0:
            raise TimeMappingError(
                f"Time {iso!r} is not aligned to {MINUTES_PER_SLOT}-minute slots"
            )
        return total_minutes // MINUTES_PER_SLOT

    def real_slot_to_datetime(self, slot: int) -> datetime:
        return self._epoch_start + timedelta(
            minutes=slot * MINUTES_PER_SLOT
        )

    def real_slot_to_iso(self, slot: int) -> str:
        return self.real_slot_to_datetime(slot).isoformat()

    # ── slot arithmetic ─────────────────────────────────────────

    def week_index(self, real_slot: int) -> int:
        return real_slot // SLOTS_PER_WEEK

    def day_of_week(self, real_slot: int) -> int:
        dt = self.real_slot_to_datetime(real_slot)
        return dt.weekday()

    def day_name(self, real_slot: int) -> str:
        return DAY_NAMES[self.day_of_week(real_slot)]

    def time_of_day(self, real_slot: int) -> str:
        offset = real_slot % SLOTS_PER_DAY
        return slot_to_hhmm(offset)

    def hour(self, real_slot: int) -> int:
        return self.real_slot_to_datetime(real_slot).hour

    def minute(self, real_slot: int) -> int:
        return self.real_slot_to_datetime(real_slot).minute

    # ── week boundaries (L1 _partition) ─────────────────────────

    def week_start_slot(self, week_index: int) -> int:
        return week_index * SLOTS_PER_WEEK

    def week_start_iso(self, week_index: int) -> str:
        return self.real_slot_to_iso(self.week_start_slot(week_index))


def _is_aligned(dt: datetime) -> bool:
    return dt.minute % MINUTES_PER_SLOT == 0 and dt.second == 0 and dt.microsecond == 0
