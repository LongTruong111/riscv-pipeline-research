"""Week-9 long-run benchmark and bounded-memory metrics."""

from dataclasses import dataclass
from typing import Optional


T5_MINIMAL_CYCLES_PER_S = 17862.941
T5_MONITOR_CYCLES_PER_S = 13923.913


def parse_proc_status_rss_kib(text: str) -> int:
    """Parse current resident set size from Linux /proc/*/status."""

    if not isinstance(text, str):
        raise TypeError("text must be str")

    for line in text.splitlines():
        if not line.startswith("VmRSS:"):
            continue

        fields = line.split()

        if len(fields) != 3 or fields[2] != "kB":
            raise ValueError(
                f"malformed VmRSS line: {line!r}"
            )

        try:
            value = int(fields[1])
        except ValueError as exc:
            raise ValueError(
                f"invalid VmRSS value: {line!r}"
            ) from exc

        if value < 0:
            raise ValueError("VmRSS cannot be negative")

        return value

    raise ValueError("VmRSS not found in proc status")


def read_current_rss_kib() -> int:
    """Read current process RSS, not historical peak RSS."""

    with open(
        "/proc/self/status",
        "r",
        encoding="utf-8",
    ) as handle:
        return parse_proc_status_rss_kib(
            handle.read()
        )


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    cycle: int
    executed_instructions: int
    wall_ns: int
    rss_kib: int

    pending_hits: int
    retained_performance: int
    timing_observations: int
    architectural_steps: int
    recent_events: int

    def __post_init__(self) -> None:
        values = (
            self.cycle,
            self.executed_instructions,
            self.wall_ns,
            self.rss_kib,
            self.pending_hits,
            self.retained_performance,
            self.timing_observations,
            self.architectural_steps,
            self.recent_events,
        )

        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in values
        ):
            raise ValueError(
                "benchmark sample fields must be "
                "non-negative integers"
            )


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    cycles: int
    executed_instructions: int
    wall_seconds: float

    cycles_per_second: float
    instructions_per_second: float

    first_half_cycles_per_second: float
    second_half_cycles_per_second: float
    throughput_degradation_pct: float

    rss_start_kib: int
    rss_mid_kib: int
    rss_end_kib: int
    rss_mid_delta_kib: int
    rss_end_delta_kib: int

    max_pending_hits: int
    max_retained_performance: int
    max_timing_observations: int
    max_architectural_steps: int
    max_recent_events: int

    slowdown_vs_t5_minimal_pct: float
    slowdown_vs_t5_monitor_pct: float

    estimated_100k_instruction_seconds: float


class BenchmarkTracker:
    """Collect constant-size benchmark state.

    Exactly three lifecycle samples are retained:
    start, midpoint, end.

    Maxima are scalar counters, so retained memory is O(1)
    with respect to campaign length.
    """

    def __init__(self) -> None:
        self._start: Optional[BenchmarkSample] = None
        self._mid: Optional[BenchmarkSample] = None
        self._end: Optional[BenchmarkSample] = None

        self._max_pending_hits = 0
        self._max_retained_performance = 0
        self._max_timing_observations = 0
        self._max_architectural_steps = 0
        self._max_recent_events = 0

    def _update_maxima(
        self,
        sample: BenchmarkSample,
    ) -> None:
        self._max_pending_hits = max(
            self._max_pending_hits,
            sample.pending_hits,
        )

        self._max_retained_performance = max(
            self._max_retained_performance,
            sample.retained_performance,
        )

        self._max_timing_observations = max(
            self._max_timing_observations,
            sample.timing_observations,
        )

        self._max_architectural_steps = max(
            self._max_architectural_steps,
            sample.architectural_steps,
        )

        self._max_recent_events = max(
            self._max_recent_events,
            sample.recent_events,
        )

    def observe_state(
        self,
        sample: BenchmarkSample,
    ) -> None:
        """Update bounded maxima without retaining the sample."""

        self._update_maxima(sample)

    def record_start(
        self,
        sample: BenchmarkSample,
    ) -> None:
        if self._start is not None:
            raise ValueError("benchmark start already recorded")

        if sample.cycle != 0:
            raise ValueError(
                "benchmark start cycle must be zero"
            )

        if sample.executed_instructions != 0:
            raise ValueError(
                "benchmark start instruction count must be zero"
            )

        self._start = sample
        self._update_maxima(sample)

    def record_mid(
        self,
        sample: BenchmarkSample,
    ) -> None:
        if self._start is None:
            raise ValueError(
                "benchmark start must be recorded first"
            )

        if self._mid is not None:
            raise ValueError("benchmark midpoint already recorded")

        if sample.cycle <= self._start.cycle:
            raise ValueError(
                "midpoint cycle must follow start"
            )

        if sample.wall_ns <= self._start.wall_ns:
            raise ValueError(
                "midpoint wall time must follow start"
            )

        self._mid = sample
        self._update_maxima(sample)

    def record_end(
        self,
        sample: BenchmarkSample,
    ) -> None:
        if self._mid is None:
            raise ValueError(
                "benchmark midpoint must be recorded first"
            )

        if self._end is not None:
            raise ValueError("benchmark end already recorded")

        if sample.cycle <= self._mid.cycle:
            raise ValueError(
                "end cycle must follow midpoint"
            )

        if sample.wall_ns <= self._mid.wall_ns:
            raise ValueError(
                "end wall time must follow midpoint"
            )

        self._end = sample
        self._update_maxima(sample)

    @staticmethod
    def _rate(
        count_delta: int,
        ns_delta: int,
    ) -> float:
        if ns_delta <= 0:
            raise ValueError(
                "elapsed wall time must be positive"
            )

        return (
            count_delta
            / (ns_delta / 1_000_000_000)
        )

    def summary(self) -> BenchmarkSummary:
        if (
            self._start is None
            or self._mid is None
            or self._end is None
        ):
            raise ValueError(
                "start, midpoint, and end samples "
                "are required"
            )

        start = self._start
        mid = self._mid
        end = self._end

        cycles = end.cycle - start.cycle

        executed = (
            end.executed_instructions
            - start.executed_instructions
        )

        elapsed_ns = (
            end.wall_ns - start.wall_ns
        )

        cycles_per_second = self._rate(
            cycles,
            elapsed_ns,
        )

        instructions_per_second = self._rate(
            executed,
            elapsed_ns,
        )

        first_half_cps = self._rate(
            mid.cycle - start.cycle,
            mid.wall_ns - start.wall_ns,
        )

        second_half_cps = self._rate(
            end.cycle - mid.cycle,
            end.wall_ns - mid.wall_ns,
        )

        degradation_pct = (
            (
                1.0
                - second_half_cps
                / first_half_cps
            )
            * 100.0
        )

        slowdown_minimal_pct = (
            (
                1.0
                - cycles_per_second
                / T5_MINIMAL_CYCLES_PER_S
            )
            * 100.0
        )

        slowdown_monitor_pct = (
            (
                1.0
                - cycles_per_second
                / T5_MONITOR_CYCLES_PER_S
            )
            * 100.0
        )

        if instructions_per_second <= 0:
            estimated_100k_s = float("inf")
        else:
            estimated_100k_s = (
                100_000
                / instructions_per_second
            )

        return BenchmarkSummary(
            cycles=cycles,
            executed_instructions=executed,
            wall_seconds=(
                elapsed_ns / 1_000_000_000
            ),
            cycles_per_second=cycles_per_second,
            instructions_per_second=(
                instructions_per_second
            ),
            first_half_cycles_per_second=(
                first_half_cps
            ),
            second_half_cycles_per_second=(
                second_half_cps
            ),
            throughput_degradation_pct=(
                degradation_pct
            ),
            rss_start_kib=start.rss_kib,
            rss_mid_kib=mid.rss_kib,
            rss_end_kib=end.rss_kib,
            rss_mid_delta_kib=(
                mid.rss_kib - start.rss_kib
            ),
            rss_end_delta_kib=(
                end.rss_kib - start.rss_kib
            ),
            max_pending_hits=(
                self._max_pending_hits
            ),
            max_retained_performance=(
                self._max_retained_performance
            ),
            max_timing_observations=(
                self._max_timing_observations
            ),
            max_architectural_steps=(
                self._max_architectural_steps
            ),
            max_recent_events=(
                self._max_recent_events
            ),
            slowdown_vs_t5_minimal_pct=(
                slowdown_minimal_pct
            ),
            slowdown_vs_t5_monitor_pct=(
                slowdown_monitor_pct
            ),
            estimated_100k_instruction_seconds=(
                estimated_100k_s
            ),
        )
