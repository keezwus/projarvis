import pytest
from projarvis.planner.constants import (
    hhmm_to_minutes,
    minutes_to_hhmm,
    hhmm_to_slot,
    slot_to_hhmm,
    MINUTES_PER_SLOT,
    SLOTS_PER_HOUR,
    SLOTS_PER_DAY,
    SLOTS_PER_WEEK,
)
from projarvis.planner.models import TimeSpec
from projarvis.planner.time_mapper import TimeMapper, TimeContext
from projarvis.planner.exceptions import ValidationError, TimeMappingError


def make_time_spec(**overrides) -> TimeSpec:
    defaults = {
        "horizon_start": "2026-05-04T00:00:00",
        "horizon_days": 5,
        "weekly_base": {
            "monday": [["09:00", "12:00"], ["14:00", "18:00"]],
            "tuesday": [["09:00", "12:00"], ["14:00", "18:00"]],
            "wednesday": [["09:00", "12:00"], ["14:00", "18:00"]],
            "thursday": [["09:00", "12:00"], ["14:00", "18:00"]],
            "friday": [["09:00", "12:00"], ["14:00", "17:00"]],
            "saturday": [],
            "sunday": [],
        },
        "overrides": [],
    }
    defaults.update(overrides)
    return TimeSpec(**defaults)


class TestTimeMapper:
    def test_basic_block_expansion(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        # Mon: 09-12 (3h=12 slots) + 14-18 (4h=16 slots) = 28 slots
        assert tm.total_slots == 28

    def test_full_week_expansion(self):
        ts = make_time_spec(horizon_days=5)
        tm = TimeMapper(ts)
        # Mon-Thu: 7h each (28 slots), Fri: 6h (24 slots) = 28*4 + 24 = 136
        assert tm.total_slots == 136

    def test_bidirectional_mapping_consistency(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        for c in range(tm.total_slots):
            real = tm.compressed_to_real(c)
            assert tm.real_to_compressed(real) == c

    def test_block_boundaries(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        # Mon: 09-12 (slots 36-48), 14-18 (slots 56-72)
        # After first block: boundary at 12 (the compressed slot after block 0)
        assert len(tm.block_boundaries) == 1
        assert tm.block_boundaries[0] == 12  # 12 slots in block 0

    def test_reject_before_horizon(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        with pytest.raises(TimeMappingError):
            tm.resolve_time_ref("2026-05-03T09:00:00")

    def test_reject_outside_available(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        # Monday 13:00 (lunch break, not available)
        with pytest.raises(TimeMappingError):
            tm.resolve_time_ref("2026-05-04T13:00:00")

    def test_reject_unaligned_time(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        with pytest.raises(TimeMappingError):
            tm.resolve_time_ref("2026-05-04T09:07:00")

    def test_resolve_time_ref(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        # Monday 09:00 = real slot 36, should be compressed slot 0
        assert tm.resolve_time_ref("2026-05-04T09:00:00") == 0
        # Monday 09:15 = real slot 37, compressed slot 1
        assert tm.resolve_time_ref("2026-05-04T09:15:00") == 1
        # Monday 14:00 = real slot 56 → first slot of second block
        # After block 0 (slots 36-48, 12 compressed), block 1 starts at comp 12
        assert tm.resolve_time_ref("2026-05-04T14:00:00") == 12

    def test_override_remove(self):
        ts = make_time_spec(
            horizon_days=1,
            overrides=[
                {"date": "2026-05-04T00:00:00", "action": "remove", "blocks": [["14:00", "18:00"]]}
            ],
        )
        tm = TimeMapper(ts)
        # Only morning block remains: 12 slots
        assert tm.total_slots == 12

    def test_override_add(self):
        ts = make_time_spec(
            horizon_days=1,
            overrides=[
                {"date": "2026-05-04T00:00:00", "action": "add", "blocks": [["18:00", "20:00"]]}
            ],
        )
        tm = TimeMapper(ts)
        # 28 original + 8 (18-20 = 2h) = 36
        assert tm.total_slots == 36

    def test_override_remove_partial_block(self):
        ts = make_time_spec(
            horizon_days=1,
            overrides=[
                {"date": "2026-05-04T00:00:00", "action": "remove", "blocks": [["15:00", "16:00"]]}
            ],
        )
        tm = TimeMapper(ts)
        # Original: 09-12 (12 slots) + 14-18 (16 slots) = 28
        # After removing 15-16 (4 slots) from afternoon: 28 - 4 = 24
        assert tm.total_slots == 24

    def test_multi_day_context(self):
        ts = make_time_spec(horizon_days=2)
        tm = TimeMapper(ts)
        ctx = tm.context
        # Mon 09:00 = c0
        assert ctx.day_name(0) == "monday"
        assert ctx.time_of_day(0) == "09:00"
        # Tue 09:00 = compressed slot 28 (after Monday 28 slots)
        assert ctx.day_name(28) == "tuesday"
        assert ctx.time_of_day(28) == "09:00"

    def test_time_context_queries(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        ctx = tm.context
        # Mon 09:00
        assert ctx.day_of_week(0) == 0  # Monday
        assert ctx.hour(0) == 9
        assert ctx.minute(0) == 0
        assert ctx.is_morning(0) is True
        assert ctx.is_afternoon(0) is False
        # Mon 14:00 (c12 = start of afternoon block)
        assert ctx.is_morning(12) is False
        assert ctx.is_afternoon(12) is True
        assert ctx.is_evening(12) is False
        # Mon 18:00 slot would be c28 (last slot of afternoon), hour=18
        assert ctx.is_evening(27) is False  # 17:45
        assert ctx.hour(27) == 17

    def test_saturday_only_work(self):
        ts = make_time_spec(
            horizon_start="2026-05-09T00:00:00",  # Saturday
            horizon_days=2,
            weekly_base={
                "monday": [],
                "tuesday": [],
                "wednesday": [],
                "thursday": [],
                "friday": [],
                "saturday": [["10:00", "15:00"]],
                "sunday": [],
            },
        )
        tm = TimeMapper(ts)
        # Sat 10-15 = 20 slots. Sun = 0.
        assert tm.total_slots == 20

    def test_compressed_range_to_real(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        r_start, r_end = tm.compressed_range_to_real(0, 12)
        # c0 = real 36 (09:00), c12 = real 56 (14:00)
        assert r_start == 36
        assert r_end == 56

    def test_no_available_time(self):
        ts = make_time_spec(
            weekly_base={
                "monday": [],
                "tuesday": [],
                "wednesday": [],
                "thursday": [],
                "friday": [],
                "saturday": [],
                "sunday": [],
            }
        )
        tm = TimeMapper(ts)
        assert tm.total_slots == 0
        assert tm.block_boundaries == []

    def test_empty_day_blocks(self):
        ts = TimeSpec(
            horizon_start="2026-05-04T00:00:00",
            horizon_days=1,
            weekly_base={"monday": []},
            overrides=[],
        )
        tm = TimeMapper(ts)
        assert tm.total_slots == 0


class TestWeeklyBaseValidation:
    def test_start_equals_end_rejected(self):
        ts = make_time_spec(
            horizon_days=1,
            weekly_base={"monday": [["09:00", "09:00"]]},
        )
        with pytest.raises(ValidationError):
            TimeMapper(ts)

    def test_start_after_end_rejected(self):
        ts = make_time_spec(
            horizon_days=1,
            weekly_base={"monday": [["14:00", "09:00"]]},
        )
        with pytest.raises(ValidationError):
            TimeMapper(ts)

    def test_overlapping_blocks_rejected(self):
        ts = make_time_spec(
            horizon_days=1,
            weekly_base={"monday": [["09:00", "12:00"], ["11:00", "14:00"]]},
        )
        with pytest.raises(ValidationError):
            TimeMapper(ts)


class TestTimeContextEdgeCases:
    def test_cross_midnight_check(self):
        """Context queries across day boundaries should give correct results."""
        ts = make_time_spec(
            horizon_start="2026-05-04T00:00:00",
            horizon_days=2,
        )
        tm = TimeMapper(ts)
        ctx = tm.context
        # Tue slot c28 = Tue 09:00
        assert ctx.day_name(28) == "tuesday"
        assert ctx.day_of_week(28) == 1

    def test_real_slot(self):
        ts = make_time_spec(horizon_days=1)
        tm = TimeMapper(ts)
        ctx = tm.context
        # c0 = real 36
        assert ctx.real_slot(0) == 36


class TestHourMinuteHelpers:
    def test_hhmm_to_minutes(self):
        assert hhmm_to_minutes("09:00") == 540
        assert hhmm_to_minutes("00:00") == 0
        assert hhmm_to_minutes("23:45") == 1425

    def test_minutes_to_hhmm(self):
        assert minutes_to_hhmm(540) == "09:00"
        assert minutes_to_hhmm(0) == "00:00"
        assert minutes_to_hhmm(1425) == "23:45"

    def test_hhmm_to_slot(self):
        assert hhmm_to_slot("09:00") == 36
        assert hhmm_to_slot("00:00") == 0
        assert hhmm_to_slot("23:45") == 95

    def test_slot_to_hhmm(self):
        assert slot_to_hhmm(36) == "09:00"
        assert slot_to_hhmm(0) == "00:00"
        assert slot_to_hhmm(95) == "23:45"
