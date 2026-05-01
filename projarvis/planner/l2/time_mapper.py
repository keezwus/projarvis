from projarvis.planner.time_epoch import (
    MINUTES_PER_SLOT,
    SLOTS_PER_DAY,
    hhmm_to_minutes,
    TimeEpoch,
)
from projarvis.planner.exceptions import ValidationError, TimeMappingError
from .models import TimeSpec


class TimeMapper:
    """Compresses available time blocks into a contiguous integer domain [0, N-1].

    Receives a shared TimeEpoch for all real-slot ↔ datetime conversions.
    """

    def __init__(self, time_spec: TimeSpec, epoch: TimeEpoch):
        self._epoch = epoch
        self._start_slot = epoch.iso_to_real_slot(time_spec.horizon_start)
        self._horizon_days = time_spec.horizon_days
        self._comp_to_offset: list[int] = []
        self._offset_to_comp: dict[int, int] = {}
        self._block_boundaries: list[int] = []
        self._total_slots = 0

        self._build(time_spec.weekly_base, time_spec.overrides)

    # ── public API ──────────────────────────────────────────────

    def resolve_time_ref(self, iso_string: str) -> int:
        real_slot = self._epoch.iso_to_real_slot(iso_string)
        offset = real_slot - self._start_slot
        comp = self._offset_to_comp.get(offset)
        if comp is None:
            raise TimeMappingError(
                f"Time {iso_string!r} (real slot {real_slot}) is not in available time"
            )
        return comp

    def resolve_or_nearest(self, iso_string: str) -> int:
        """Convert ISO 8601 to compressed slot, scanning backward if outside availability."""
        real_slot = self._epoch.iso_to_real_slot(iso_string)
        offset = real_slot - self._start_slot
        for prev in range(offset, -1, -1):
            comp = self._offset_to_comp.get(prev)
            if comp is not None:
                return comp
        raise TimeMappingError(
            f"Time {iso_string!r} is before all available slots"
        )

    def real_to_compressed(self, real_slot: int) -> int | None:
        return self._offset_to_comp.get(real_slot - self._start_slot)

    def compressed_to_real(self, comp_slot: int) -> int:
        return self._start_slot + self._comp_to_offset[comp_slot]

    def compressed_range_to_real(self, c_start: int, c_end: int) -> tuple[int, int]:
        return (
            self.compressed_to_real(c_start),
            self.compressed_to_real(c_end),
        )

    def real_slot_to_iso(self, real_slot: int) -> str:
        return self._epoch.real_slot_to_iso(real_slot)

    # ── absorbed TimeContext methods ────────────────────────────

    def day_of_week(self, comp_slot: int) -> int:
        real = self.compressed_to_real(comp_slot)
        return self._epoch.day_of_week(real)

    def day_name(self, comp_slot: int) -> str:
        real = self.compressed_to_real(comp_slot)
        return self._epoch.day_name(real)

    def time_of_day(self, comp_slot: int) -> str:
        real = self.compressed_to_real(comp_slot)
        return self._epoch.time_of_day(real)

    def hour(self, comp_slot: int) -> int:
        real = self.compressed_to_real(comp_slot)
        return self._epoch.hour(real)

    def minute(self, comp_slot: int) -> int:
        real = self.compressed_to_real(comp_slot)
        return self._epoch.minute(real)

    def is_morning(self, comp_slot: int) -> bool:
        return self.hour(comp_slot) < 12

    def is_afternoon(self, comp_slot: int) -> bool:
        return 12 <= self.hour(comp_slot) < 18

    def is_evening(self, comp_slot: int) -> bool:
        return self.hour(comp_slot) >= 18

    # ── properties ──────────────────────────────────────────────

    @property
    def total_slots(self) -> int:
        return self._total_slots

    @property
    def block_boundaries(self) -> list[int]:
        return list(self._block_boundaries)

    # ── internal helpers ────────────────────────────────────────

    def _build(
        self,
        weekly_base: dict[str, list[list[str]]],
        overrides: list[dict],
    ) -> None:
        self._validate_weekly_base(weekly_base)

        all_blocks: list[tuple[int, int]] = []  # (offset_start, offset_end) per day

        for day_offset in range(self._horizon_days):
            day_start_slot = self._start_slot + day_offset * SLOTS_PER_DAY
            day_name = self._epoch.day_name(day_start_slot)

            day_blocks: list[tuple[int, int]] = []
            for block in weekly_base.get(day_name, []):
                start_min = hhmm_to_minutes(block[0])
                end_min = hhmm_to_minutes(block[1])
                day_blocks.append((start_min, end_min))

            # Apply overrides for this specific date
            for ov in overrides:
                ov_date = self._epoch.real_slot_to_datetime(
                    self._epoch.iso_to_real_slot(ov["date"])
                ).date()
                day_date = self._epoch.real_slot_to_datetime(day_start_slot).date()
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

            # Convert to offset slots
            for start_min, end_min in day_blocks:
                offset_start = day_offset * SLOTS_PER_DAY + start_min // MINUTES_PER_SLOT
                offset_end = day_offset * SLOTS_PER_DAY + end_min // MINUTES_PER_SLOT
                all_blocks.append((offset_start, offset_end))

        # Build compressed mapping from all blocks
        comp_idx = 0
        for i, (offset_start, offset_end) in enumerate(all_blocks):
            for offset in range(offset_start, offset_end):
                self._comp_to_offset.append(offset)
                self._offset_to_comp[offset] = comp_idx
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
