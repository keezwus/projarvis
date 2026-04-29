import pytest
from datetime import datetime
from projarvis.planner.time_epoch import (
    MINUTES_PER_SLOT,
    SLOTS_PER_HOUR,
    SLOTS_PER_DAY,
    SLOTS_PER_WEEK,
    DAY_NAMES,
    hhmm_to_minutes,
    minutes_to_hhmm,
    hhmm_to_slot,
    slot_to_hhmm,
    is_iso_datetime,
    TimeEpoch,
)
from projarvis.planner.exceptions import TimeMappingError


class TestTimeEpochCore:
    def test_iso_to_real_slot_same_day(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")  # Monday
        assert epoch.iso_to_real_slot("2026-05-04T09:00:00") == 36

    def test_iso_to_real_slot_week_later(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        assert epoch.iso_to_real_slot("2026-05-11T00:00:00") == 672

    def test_iso_to_real_slot_before_epoch_rejected(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        with pytest.raises(TimeMappingError, match="before epoch"):
            epoch.iso_to_real_slot("2026-05-03T23:00:00")

    def test_iso_to_real_slot_unaligned_rejected(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        with pytest.raises(TimeMappingError, match="not aligned"):
            epoch.iso_to_real_slot("2026-05-04T09:07:00")

    def test_real_slot_to_datetime(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        dt = epoch.real_slot_to_datetime(36)
        assert dt == datetime.fromisoformat("2026-05-04T09:00:00")

    def test_real_slot_to_iso(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        assert epoch.real_slot_to_iso(36) == "2026-05-04T09:00:00"

    def test_roundtrip(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        iso = "2026-05-04T14:30:00"
        slot = epoch.iso_to_real_slot(iso)
        assert epoch.real_slot_to_iso(slot) == iso


class TestTimeEpochSlotArithmetic:
    def test_week_index(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")  # Monday
        assert epoch.week_index(0) == 0            # Mon 00:00
        assert epoch.week_index(671) == 0          # Sun 23:45
        assert epoch.week_index(672) == 1          # Next Mon 00:00

    def test_day_of_week(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")  # Monday
        assert epoch.day_of_week(0) == 0            # Monday
        assert epoch.day_of_week(96) == 1           # Tuesday
        assert epoch.day_of_week(96 * 6) == 6       # Sunday

    def test_day_name(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        assert epoch.day_name(0) == "monday"
        assert epoch.day_name(96) == "tuesday"

    def test_time_of_day(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        assert epoch.time_of_day(0) == "00:00"
        assert epoch.time_of_day(36) == "09:00"
        assert epoch.time_of_day(95) == "23:45"

    def test_hour_and_minute(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        assert epoch.hour(36) == 9
        assert epoch.minute(36) == 0
        assert epoch.hour(0) == 0
        assert epoch.hour(95) == 23
        assert epoch.minute(95) == 45


class TestTimeEpochWeekBoundaries:
    def test_week_start_slot(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        assert epoch.week_start_slot(0) == 0
        assert epoch.week_start_slot(1) == 672
        assert epoch.week_start_slot(2) == 1344

    def test_week_start_iso(self):
        epoch = TimeEpoch("2026-05-04T00:00:00")
        assert epoch.week_start_iso(0) == "2026-05-04T00:00:00"
        assert epoch.week_start_iso(1) == "2026-05-11T00:00:00"


class TestTimeEpochValidation:
    def test_unaligned_epoch_start_rejected(self):
        with pytest.raises(TimeMappingError, match="not aligned"):
            TimeEpoch("2026-05-04T09:07:00")

    def test_epoch_start_with_seconds_rejected(self):
        with pytest.raises(TimeMappingError, match="not aligned"):
            TimeEpoch("2026-05-04T09:00:30")

    def test_epoch_start_exact_minute_accepted(self):
        epoch = TimeEpoch("2026-05-04T09:00:00")
        assert epoch.real_slot_to_iso(0) == "2026-05-04T09:00:00"


class TestIsIsoDatetime:
    def test_valid_iso(self):
        assert is_iso_datetime("2026-05-04T09:00:00") is True

    def test_not_iso(self):
        assert is_iso_datetime("hello") is False
        assert is_iso_datetime("09:00") is False
        assert is_iso_datetime("") is False

    def test_non_string(self):
        assert is_iso_datetime(42) is False
        assert is_iso_datetime(None) is False
        assert is_iso_datetime(["2026-05-04T09:00:00"]) is False


class TestModuleConstants:
    def test_slot_constants(self):
        assert MINUTES_PER_SLOT == 15
        assert SLOTS_PER_HOUR == 4
        assert SLOTS_PER_DAY == 96
        assert SLOTS_PER_WEEK == 672

    def test_day_names(self):
        assert DAY_NAMES[0] == "monday"
        assert DAY_NAMES[6] == "sunday"
        assert len(DAY_NAMES) == 7
