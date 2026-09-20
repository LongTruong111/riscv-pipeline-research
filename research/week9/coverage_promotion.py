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
    """Reject internally inconsistent attribution records.

    Coverage promotion follows the authoritative frozen Week-5
    validation result carried by ``record.validated``.

    Week-9 diagnostic status is independent: an already validated
    frozen hit may still be TIMING_MISMATCH because additional
    Week-7/Week-8 timing evidence is stricter than the frozen
    coverage-promotion rule.
    """

    if record.validated:
        if record.validated_bin != record.intent_bin:
            raise ValueError(
                "validated record must promote its own Intent bin"
            )

        # These fields represent the authoritative frozen Week-5
        # validation dimensions.
        if record.control_pass is not True:
            raise ValueError(
                "validated record requires frozen control PASS"
            )

        if record.functional_pass is not True:
            raise ValueError(
                "validated record requires frozen architectural PASS"
            )

        # REALIZED_CORRECTLY:
        #   frozen validation PASS + all additional evidence PASS.
        #
        # TIMING_MISMATCH:
        #   frozen validation PASS, but additional Week-7/Week-8
        #   timing evidence detected a mismatch.
        #
        # UNRESOLVED:
        #   authoritative frozen validation is already available,
        #   while one of the additional diagnostic layers has not
        #   yet arrived.
        if record.status not in {
            ValidationStatus.REALIZED_CORRECTLY,
            ValidationStatus.TIMING_MISMATCH,
            ValidationStatus.UNRESOLVED,
        }:
            raise ValueError(
                "validated record has inconsistent "
                f"diagnostic status: {record.status}"
            )

    else:
        if record.validated_bin is not None:
            raise ValueError(
                "nonvalidated record cannot carry validated_bin"
            )

        if (
            record.status
            == ValidationStatus.REALIZED_CORRECTLY
        ):
            raise ValueError(
                "REALIZED_CORRECTLY requires "
                "authoritative validation"
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
        True when the authoritative frozen Week-5 validation
        makes this hit eligible for Validated Coverage.

        False when authoritative validation has not promoted
        this concrete hit.

    Notes:
        Diagnostic status is independent of frozen coverage promotion.

        In particular, a record may be:

            validated=True
            status=UNRESOLVED

        when frozen Week-5 control/architectural evidence is complete
        but additional Week-7/Week-8 diagnostic evidence has not yet
        arrived.

        Likewise, a frozen validated hit may later carry
        TIMING_MISMATCH without losing its already-established
        Validated Coverage state.

        CoverageCollector preserves first-hit immutability.
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
