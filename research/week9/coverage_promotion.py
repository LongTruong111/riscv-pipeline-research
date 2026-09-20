"""Week 9 adapter from validated attribution to coverage promotion.

This module does not recompute verification verdicts.

Responsibilities:
- accept one ValidatedAttributionRecord;
- verify that its state is internally consistent;
- promote the corresponding L1 bin only when the record is validated;
- preserve CoverageCollector first-hit semantics.
"""

from research.week9.coverage_collector import CoverageCollector
from research.week9.validated_attribution import (
    ValidatedAttributionRecord,
    ValidationStatus,
)


def _validate_record(
    record: ValidatedAttributionRecord,
) -> None:
    """Reject internally inconsistent attribution records."""

    if record.validated:
        if record.validated_bin != record.intent_bin:
            raise ValueError(
                "validated record must promote its own Intent bin"
            )

        if (
            record.status
            != ValidationStatus.REALIZED_CORRECTLY
        ):
            raise ValueError(
                "validated record must have "
                "REALIZED_CORRECTLY status"
            )

        if record.control_pass is not True:
            raise ValueError(
                "validated record requires control_pass=True"
            )

        if record.functional_pass is not True:
            raise ValueError(
                "validated record requires functional_pass=True"
            )

    else:
        if record.validated_bin is not None:
            raise ValueError(
                "non-validated record must not carry "
                "validated_bin"
            )

        if (
            record.status
            == ValidationStatus.REALIZED_CORRECTLY
        ):
            raise ValueError(
                "non-validated record cannot have "
                "REALIZED_CORRECTLY status"
            )


def promote_l1_attribution(
    collector: CoverageCollector,
    record: ValidatedAttributionRecord,
    *,
    resolution_cycle: int,
    wall_ns: int,
) -> bool:
    """Apply one per-hit attribution result to L1 coverage state.

    Returns:
        True if this hit is eligible for validated promotion.
        False if the hit is rejected/unresolved/intended only.

    Notes:
        The collector itself preserves first-hit immutability, so a
        duplicate validated occurrence does not overwrite the first
        validated metadata.
    """

    if not isinstance(collector, CoverageCollector):
        raise TypeError(
            "collector must be a CoverageCollector"
        )

    if not isinstance(
        record,
        ValidatedAttributionRecord,
    ):
        raise TypeError(
            "record must be a ValidatedAttributionRecord"
        )

    _validate_record(record)

    if not record.validated:
        return False

    # CoverageCollector enforces:
    #   Validated => prior Intent
    # and rejects promotion when no Intent evidence exists.
    collector.record_l1_validated(
        record.validated_bin,
        instruction_id=record.instruction_id,
        cycle=resolution_cycle,
        wall_ns=wall_ns,
    )

    return True
