from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ArmID(str, Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"
    A5 = "A5"
    A6 = "A6"
    A7 = "A7"
    A8 = "A8"
    A9 = "A9"


class Distance(str, Enum):
    D1 = "d1"
    D2 = "d2"
    D1_D2 = "d1_d2"


class RegisterPolicy(str, Enum):
    """Semantic register constraints, not the target-selection algorithm."""

    UNCOVERED_FIRST_SINGLE = "uncovered_first_single"
    UNCOVERED_FIRST_DUAL_DISTINCT = "uncovered_first_dual_distinct"
    STORE_DATA_RS2 = "store_data_rs2"
    SAME_RD_NEWEST_WRITER = "same_rd_newest_writer"


class FillerPolicy(str, Enum):
    """
    Structural instructions required by a template.

    This is distinct from the frozen campaign-level 80:20
    targeted-template/background-filler ratio.
    """

    NONE = "none"
    ONE_INDEPENDENT_FOR_D2 = "one_independent_for_d2"
    CONTROL_FLOW_STRUCTURAL = "control_flow_structural"


@dataclass(frozen=True)
class TemplateSpec:
    arm_id: ArmID
    hazard_class: str
    producer: tuple[str, ...]
    consumer: tuple[str, ...]
    distance: Distance
    register_policy: RegisterPolicy
    filler_policy: FillerPolicy

    # Diagnostic mapping only. L1 is not the adaptive objective.
    l1_bins: tuple[str, ...]

    notes: tuple[str, ...] = ()


_TEMPLATE_LIBRARY = {
    ArmID.A0: TemplateSpec(
        arm_id=ArmID.A0,
        hazard_class="ALU_D1",
        producer=("ALU",),
        consumer=("RS1 consumer", "RS2 consumer"),
        distance=Distance.D1,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_SINGLE,
        filler_policy=FillerPolicy.NONE,
        l1_bins=("H01", "H02"),
        notes=(
            "ALU producer.",
            "RS1/RS2 consumer variants are selected uniformly.",
        ),
    ),
    ArmID.A1: TemplateSpec(
        arm_id=ArmID.A1,
        hazard_class="ALU_D2",
        producer=("ALU",),
        consumer=("RS1 consumer", "RS2 consumer"),
        distance=Distance.D2,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_SINGLE,
        filler_policy=FillerPolicy.ONE_INDEPENDENT_FOR_D2,
        l1_bins=("H03", "H04"),
        notes=("Exactly one independent structural instruction realizes d2.",),
    ),
    ArmID.A2: TemplateSpec(
        arm_id=ArmID.A2,
        hazard_class="LOAD_D1",
        producer=("LOAD",),
        consumer=("RS1 consumer", "RS2 consumer"),
        distance=Distance.D1,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_SINGLE,
        filler_policy=FillerPolicy.NONE,
        l1_bins=("H06", "H07"),
        notes=("Expected load-use interlock semantics apply.",),
    ),
    ArmID.A3: TemplateSpec(
        arm_id=ArmID.A3,
        hazard_class="LOAD_D2",
        producer=("LOAD",),
        consumer=("RS1 consumer", "RS2 consumer"),
        distance=Distance.D2,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_SINGLE,
        filler_policy=FillerPolicy.ONE_INDEPENDENT_FOR_D2,
        l1_bins=("H08", "H09"),
        notes=("Exactly one independent structural instruction realizes d2.",),
    ),
    ArmID.A4: TemplateSpec(
        arm_id=ArmID.A4,
        hazard_class="DUAL_D1_D2",
        producer=("d2 producer", "d1 producer"),
        consumer=("dual-source consumer",),
        distance=Distance.D1_D2,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_DUAL_DISTINCT,
        filler_policy=FillerPolicy.NONE,
        l1_bins=("H10",),
        notes=(
            "Consumer receives one d1 and one d2 dependency.",
            "The two dependency registers must be distinct.",
        ),
    ),
    ArmID.A5: TemplateSpec(
        arm_id=ArmID.A5,
        hazard_class="SPECIAL_WB_D1",
        producer=("LUI", "AUIPC"),
        consumer=("register consumer",),
        distance=Distance.D1,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_SINGLE,
        filler_policy=FillerPolicy.NONE,
        l1_bins=("H11", "H13"),
        notes=("LUI/AUIPC producer variants use frozen 1:1 selection.",),
    ),
    ArmID.A6: TemplateSpec(
        arm_id=ArmID.A6,
        hazard_class="SPECIAL_WB_D2",
        producer=("LUI", "AUIPC"),
        consumer=("register consumer",),
        distance=Distance.D2,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_SINGLE,
        filler_policy=FillerPolicy.ONE_INDEPENDENT_FOR_D2,
        l1_bins=("H12", "H14"),
        notes=("LUI/AUIPC producer variants use frozen 1:1 selection.",),
    ),
    ArmID.A7: TemplateSpec(
        arm_id=ArmID.A7,
        hazard_class="LINK_D1",
        producer=("JAL", "JALR"),
        consumer=("link-register consumer",),
        distance=Distance.D1,
        register_policy=RegisterPolicy.UNCOVERED_FIRST_SINGLE,
        filler_policy=FillerPolicy.CONTROL_FLOW_STRUCTURAL,
        l1_bins=("H15",),
        notes=(
            "Flushed fall-through instructions are never consumers.",
            "Positive target register must not be x0.",
        ),
    ),
    ArmID.A8: TemplateSpec(
        arm_id=ArmID.A8,
        hazard_class="STORE_DATA_D1",
        producer=("register-writing producer",),
        consumer=("STORE",),
        distance=Distance.D1,
        register_policy=RegisterPolicy.STORE_DATA_RS2,
        filler_policy=FillerPolicy.NONE,
        l1_bins=("H16",),
        notes=("Dependency is architectural store-data rs2.",),
    ),
    ArmID.A9: TemplateSpec(
        arm_id=ArmID.A9,
        hazard_class="PRIORITY_D1",
        producer=("older d2 writer", "newest d1 writer"),
        consumer=("register consumer",),
        distance=Distance.D1,
        register_policy=RegisterPolicy.SAME_RD_NEWEST_WRITER,
        filler_policy=FillerPolicy.NONE,
        l1_bins=("H17",),
        notes=(
            "Both producers write the same rd.",
            "Newest d1 writer is the active producer.",
            "Older d2 writer is shadowed and creates no positive L2 hit.",
        ),
    ),
}


TEMPLATE_LIBRARY: Mapping[ArmID, TemplateSpec] = MappingProxyType(
    _TEMPLATE_LIBRARY
)


def get_template(arm_id: ArmID) -> TemplateSpec:
    """Return the immutable specification for one adaptive arm."""
    try:
        return TEMPLATE_LIBRARY[arm_id]
    except KeyError as exc:
        raise ValueError(f"unknown adaptive arm: {arm_id!r}") from exc


def validate_template_library() -> None:
    """Fail fast if frozen A0-A9 semantics are structurally inconsistent."""

    expected_ids = set(ArmID)

    if set(TEMPLATE_LIBRARY) != expected_ids:
        missing = expected_ids - set(TEMPLATE_LIBRARY)
        extra = set(TEMPLATE_LIBRARY) - expected_ids
        raise RuntimeError(
            f"adaptive arm taxonomy mismatch: missing={missing}, extra={extra}"
        )

    if len(TEMPLATE_LIBRARY) != 10:
        raise RuntimeError("Adaptive CGS must contain exactly 10 arms")

    a4 = TEMPLATE_LIBRARY[ArmID.A4]
    if a4.distance is not Distance.D1_D2:
        raise RuntimeError("A4 must represent simultaneous d1/d2 dependencies")
    if a4.register_policy is not RegisterPolicy.UNCOVERED_FIRST_DUAL_DISTINCT:
        raise RuntimeError("A4 requires distinct d1/d2 target registers")

    a8 = TEMPLATE_LIBRARY[ArmID.A8]
    if a8.register_policy is not RegisterPolicy.STORE_DATA_RS2:
        raise RuntimeError("A8 dependency must use architectural store-data rs2")

    a9 = TEMPLATE_LIBRARY[ArmID.A9]
    if a9.register_policy is not RegisterPolicy.SAME_RD_NEWEST_WRITER:
        raise RuntimeError("A9 must implement newest-writer priority semantics")

    expected_l1 = {
        "H01", "H02", "H03", "H04",
        "H06", "H07", "H08", "H09",
        "H10", "H11", "H12", "H13",
        "H14", "H15", "H16", "H17",
    }

    observed_l1 = {
        bin_id
        for spec in TEMPLATE_LIBRARY.values()
        for bin_id in spec.l1_bins
    }

    if observed_l1 != expected_l1:
        raise RuntimeError(
            f"adaptive L1 semantic mapping mismatch: {observed_l1}"
        )


validate_template_library()
