from __future__ import annotations

from research.week5.impl.execution_event import (
    ExecutionEvent,
)
from research.week10.adaptive.campaign_telemetry import (
    CampaignCheckpointRecord,
    EpochTelemetryRecord,
)
from research.week15.reproducibility.canonical_trace import (
    AdaptiveCanonicalTraceRecorder,
)


_SELECTION_MODES = (
    "epsilon_exploration",
    "greedy_exploitation",
    "q_floor_uniform",
)


class ReproTraceSession:
    """
    O(1)-instruction-history Week15 trace adapter.

    No reward, Q, coverage or instruction identity is
    recomputed here. Only authoritative runtime records
    are projected into the frozen canonical serializer.
    """

    def __init__(self) -> None:
        self._recorder = (
            AdaptiveCanonicalTraceRecorder()
        )

        self._selection_counts = {
            mode: 0
            for mode in _SELECTION_MODES
        }

    def record_instruction_event(
        self,
        event: ExecutionEvent,
    ) -> None:
        if not isinstance(
            event,
            ExecutionEvent,
        ):
            raise TypeError(
                "event must be ExecutionEvent"
            )

        self._recorder.record_instruction(
            accepted_instruction_index=(
                event.instruction_index
            ),
            pc=event.pc,
            instruction_word=(
                event.instruction
            ),
        )

    def record_epoch(
        self,
        record: EpochTelemetryRecord,
    ) -> None:
        if record.selection_mode not in (
            self._selection_counts
        ):
            raise ValueError(
                "unknown adaptive selection mode: "
                f"{record.selection_mode}"
            )

        self._selection_counts[
            record.selection_mode
        ] += 1

        self._recorder.record_epoch(
            record
        )

    def record_checkpoint(
        self,
        record: CampaignCheckpointRecord,
    ) -> None:
        self._recorder.record_checkpoint(
            record
        )

    def snapshot(self) -> dict:
        return {
            "trace_digests": (
                self._recorder.digests()
            ),
            "trace_record_counts": (
                self._recorder
                .record_counts()
            ),
            "selection_counts": dict(
                sorted(
                    self._selection_counts.items()
                )
            ),
        }
