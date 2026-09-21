import pytest

from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
    FillerPolicy,
    RegisterPolicy,
    TEMPLATE_LIBRARY,
    get_template,
    validate_template_library,
)


def test_exactly_ten_frozen_arms():
    assert len(TEMPLATE_LIBRARY) == 10
    assert set(TEMPLATE_LIBRARY) == set(ArmID)


def test_library_validation_passes():
    validate_template_library()


@pytest.mark.parametrize(
    ("arm_id", "distance"),
    [
        (ArmID.A0, Distance.D1),
        (ArmID.A1, Distance.D2),
        (ArmID.A2, Distance.D1),
        (ArmID.A3, Distance.D2),
        (ArmID.A4, Distance.D1_D2),
        (ArmID.A5, Distance.D1),
        (ArmID.A6, Distance.D2),
        (ArmID.A7, Distance.D1),
        (ArmID.A8, Distance.D1),
        (ArmID.A9, Distance.D1),
    ],
)
def test_frozen_distance_semantics(arm_id, distance):
    assert get_template(arm_id).distance is distance


def test_frozen_l1_semantic_mapping():
    expected = {
        ArmID.A0: ("H01", "H02"),
        ArmID.A1: ("H03", "H04"),
        ArmID.A2: ("H06", "H07"),
        ArmID.A3: ("H08", "H09"),
        ArmID.A4: ("H10",),
        ArmID.A5: ("H11", "H13"),
        ArmID.A6: ("H12", "H14"),
        ArmID.A7: ("H15",),
        ArmID.A8: ("H16",),
        ArmID.A9: ("H17",),
    }

    for arm_id, bins in expected.items():
        assert get_template(arm_id).l1_bins == bins


def test_d2_arms_require_one_independent_structural_instruction():
    for arm_id in (ArmID.A1, ArmID.A3, ArmID.A6):
        assert (
            get_template(arm_id).filler_policy
            is FillerPolicy.ONE_INDEPENDENT_FOR_D2
        )


def test_a4_requires_distinct_d1_d2_targets():
    spec = get_template(ArmID.A4)

    assert spec.distance is Distance.D1_D2
    assert (
        spec.register_policy
        is RegisterPolicy.UNCOVERED_FIRST_DUAL_DISTINCT
    )


def test_a5_a6_use_lui_auipc_variants():
    assert get_template(ArmID.A5).producer == ("LUI", "AUIPC")
    assert get_template(ArmID.A6).producer == ("LUI", "AUIPC")


def test_a7_has_control_flow_semantics():
    spec = get_template(ArmID.A7)

    assert spec.producer == ("JAL", "JALR")
    assert spec.filler_policy is FillerPolicy.CONTROL_FLOW_STRUCTURAL
    assert any("Flushed fall-through" in note for note in spec.notes)


def test_a8_is_store_data_rs2_dependency():
    spec = get_template(ArmID.A8)

    assert spec.consumer == ("STORE",)
    assert spec.register_policy is RegisterPolicy.STORE_DATA_RS2


def test_a9_uses_newest_writer_priority():
    spec = get_template(ArmID.A9)

    assert spec.register_policy is RegisterPolicy.SAME_RD_NEWEST_WRITER
    assert "older d2 writer" in spec.producer
    assert "newest d1 writer" in spec.producer
    assert any("shadowed" in note for note in spec.notes)


def test_negative_and_control_only_l1_bins_are_not_adaptive_arms():
    adaptive_bins = {
        bin_id
        for spec in TEMPLATE_LIBRARY.values()
        for bin_id in spec.l1_bins
    }

    assert "H05" not in adaptive_bins
    assert "H18" not in adaptive_bins
    assert "H19" not in adaptive_bins
    assert "H20" not in adaptive_bins
