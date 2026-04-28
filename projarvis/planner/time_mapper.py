from datetime import datetime, timedelta
from projarvis.planner.constants import (
    MINUTES_PER_SLOT,
    SLOTS_PER_DAY,
    DAY_NAMES,
    hhmm_to_minutes,
)
from projarvis.planner.exceptions import ValidationError, TimeMappingError
from projarvis.planner.models import TimeSpec


class TimeContext:
    """Read-only temporal context for plugins to query slot properties."""

    def __init__(self, mapper: "TimeMapper"):
        self._mapper = mapper

    def day_of_week(self, comp_slot: int) -> int:
        """0=Monday, 6=Sunday."""
        dt = self._mapper._slot_datetime(self._mapper.compressed_to_real(comp_slot))
        return dt.weekday()

    def day_name(self, comp_slot: int) -> str:
        return DAY_NAMES[self.day_of_week(comp_slot)]

    def time_of_day(self, comp_slot: int) -> str:
        dt = self._mapper._slot_datetime(self._mapper.compressed_to_real(comp_slot))
        return f"{dt.hour:02d}:{dt.minute:02d}"

    def hour(self, comp_slot: int) -> int:
        return self._mapper._slot_datetime(
            self._mapper.compressed_to_real(comp_slot)
        ).hour

    def minute(self, comp_slot: int) -> int:
        return self._mapper._slot_datetime(
            self._mapper.compressed_to_real(comp_slot)
        ).minute

    def is_morning(self, comp_slot: int) -> bool:
        return self.hour(comp_slot) < 12

    def is_afternoon(self, comp_slot: int) -> bool:
        return 12 <= self.hour(comp_slot) < 18

    def is_evening(self, comp_slot: int) -> bool:
        return self.hour(comp_slot) >= 18

    def real_slot(self, comp_slot: int) -> int:
        return self._mapper.compressed_to_real(comp_slot)


class TimeMapper:
    """Compresses available time blocks into a contiguous integer domain [0, N-1]."""

    def __init__(self, time_spec: TimeSpec):
        self._horizon_start = datetime.fromisoformat(time_spec.horizon_start)
        self._horizon_days = time_spec.horizon_days
        self._comp_to_real: list[int] = []
        self._real_to_comp: dict[int, int] = {}
        self._block_boundaries: list[int] = []
        self._total_slots = 0
        self._context = TimeContext(self)

        self._build(time_spec.weekly_base, time_spec.overrides)

    # ── public API ──────────────────────────────────────────────

    def resolve_time_ref(self, iso_string: str) -> int:
        dt = datetime.fromisoformat(iso_string)
        delta_minutes = (dt - self._horizon_start).total_seconds() / 60.0
        if delta_minutes < 0:
            raise TimeMappingError(
                f"Time {iso_string!r} is before horizon_start "
                f"{self._horizon_start.isoformat()}"
            )
        if delta_minutes % MINUTES_PER_SLOT != 0:
            raise TimeMappingError(
                f"Time {iso_string!r} is not aligned to {MINUTES_PER_SLOT}-minute slots"
            )
        real_slot = int(delta_minutes / MINUTES_PER_SLOT)
        comp_slot = self._real_to_comp.get(real_slot)
        if comp_slot is None:
            raise TimeMappingError(
                f"Time {iso_string!r} (real slot {real_slot}) is not in available time"
            )
        return comp_slot

    def real_to_compressed(self, real_slot: int) -> int | None:
        return self._real_to_comp.get(real_slot)

    def compressed_to_real(self, comp_slot: int) -> int:
        return self._comp_to_real[comp_slot]

    def compressed_range_to_real(self, c_start: int, c_end: int) -> tuple[int, int]:
        return (
            self.compressed_to_real(c_start),
            self.compressed_to_real(c_end),
        )

    @property
    def total_slots(self) -> int:
        return self._total_slots

    @property
    def context(self) -> TimeContext:
        return self._context

    @property
    def block_boundaries(self) -> list[int]:
        return list(self._block_boundaries)

    # ── internal helpers ────────────────────────────────────────

    def _slot_datetime(self, real_slot: int) -> datetime:
        return self._horizon_start + timedelta(
            minutes=real_slot * MINUTES_PER_SLOT
        )

    def _build(
        self,
        weekly_base: dict[str, list[list[str]]],
        overrides: list[dict],
    ) -> None:
        self._validate_weekly_base(weekly_base)

        all_blocks: list[tuple[int, int]] = []  # (real_start, real_end) per day

        for day_offset in range(self._horizon_days):
            day_date = self._horizon_start.date() + timedelta(days=day_offset)
            weekday = day_date.weekday()  # 0=Mon
            day_name = DAY_NAMES[weekday]

            # Start with base blocks for this day-of-week
            day_blocks: list[tuple[int, int]] = []
            for block in weekly_base.get(day_name, []):
                start_min = hhmm_to_minutes(block[0])
                end_min = hhmm_to_minutes(block[1])
                day_blocks.append((start_min, end_min))

            # Apply overrides for this specific date
            for ov in overrides:
                ov_date = datetime.fromisoformat(ov["date"]).date()
                if ov_date != day_date:
                    continue

                action = ov["action"]
                for block in ov["blocks"]:
                    ov_start = hhmm_to_minutes(block[0])
                    ov_end = hhmm_to_minutes(block[1])
                    if action == "remove":
                        day_blocks = self._subtract_blocks(day_blocks, ov_start, ov_end)
                    elif action == "add":
                        day_blocks = self._add_block(day_blocks, ov_start, ov_end)

            # Convert to real slots for this day
            day_base_slot = day_offset * SLOTS_PER_DAY
            for start_min, end_min in day_blocks:
                real_start = day_base_slot + start_min // MINUTES_PER_SLOT
                real_end = day_base_slot + end_min // MINUTES_PER_SLOT
                all_blocks.append((real_start, real_end))

        # Build compressed mapping from all blocks
        comp_idx = 0
        for i, (real_start, real_end) in enumerate(all_blocks):
            for real_slot in range(real_start, real_end):
                self._comp_to_real.append(real_slot)
                self._real_to_comp[real_slot] = comp_idx
                comp_idx += 1
            if i < len(all_blocks) - 1:
                self._block_boundaries.append(comp_idx)

        self._total_slots = comp_idx

    @staticmethod
    def _validate_weekly_base(weekly_base: dict[str, list[list[str]]]) -> None:
        for day, blocks in weekly_base.items():
            intervals: list[tuple[int, int]] = []
            for block in blocks:
                if len(block) != 2:
                    raise ValidationError(
                        f"Block in weekly_base[{day!r}] must be [start, end], got {block!r}"
                    )
                start = hhmm_to_minutes(block[0])
                end = hhmm_to_minutes(block[1])
                if start >= end:
                    raise ValidationError(
                        f"Block {block!r} in weekly_base[{day!r}] has start >= end"
                    )
                intervals.append((start, end))
            # Check for overlap
            intervals.sort()
            for i in range(len(intervals) - 1):
                if intervals[i][1] > intervals[i + 1][0]:
                    raise ValidationError(
                        f"Overlapping blocks in weekly_base[{day!r}]: "
                        f"{intervals[i]} and {intervals[i + 1]}"
                    )

    @staticmethod
    def _subtract_blocks(
        blocks: list[tuple[int, int]], remove_start: int, remove_end: int
    ) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        for b_start, b_end in blocks:
            if remove_end <= b_start or remove_start >= b_end:
                result.append((b_start, b_end))
            elif remove_start <= b_start and remove_end >= b_end:
                continue
            elif remove_start <= b_start:
                result.append((remove_end, b_end))
            elif remove_end >= b_end:
                result.append((b_start, remove_start))
            else:
                result.append((b_start, remove_start))
                result.append((remove_end, b_end))
        return result

    @staticmethod
    def _add_block(
        blocks: list[tuple[int, int]], add_start: int, add_end: int
    ) -> list[tuple[int, int]]:
        blocks.append((add_start, add_end))
        blocks.sort()
        merged: list[tuple[int, int]] = []
        for b in blocks:
            if merged and merged[-1][1] >= b[0]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b[1]))
            else:
                merged.append(b)
        return merged
