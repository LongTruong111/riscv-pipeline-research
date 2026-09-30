from __future__ import annotations

import hashlib
import json
from pathlib import Path
from random import Random


from research.week10.adaptive.campaign_seed import (
    SEED_DOMAIN,
    derive_campaign_seeds,
)
from research.week10.adaptive.decision_engine import (
    ARM_ORDER,
    DEFAULT_Q_FLOOR,
    Q_INIT,
)
from research.week10.adaptive.filler_policy import (
    FILLER_LUI_IMM20,
    TARGETED_INSTRUCTIONS_PER_FILLER,
    FillerKind,
    build_filler_instruction,
    select_auxiliary_register,
)
from research.week10.adaptive.register_policy import (
    L2IntentCoverageState,
    POSITIVE_REGISTERS,
    RegisterTargetPolicy,
    TargetSelection,
)
from research.week10.adaptive.reward_engine import (
    EpochRewardTracker,
    L2IntentBin,
)
from research.week10.adaptive.template_library import (
    ArmID,
    Distance,
    get_template,
)
from research.week13.adaptive.selected_config import (
    SELECTED_ALPHA,
    SELECTED_EPSILON,
    SELECTED_NOMINAL_BATCH,
    SELECTED_Q_FLOOR,
)


ROOT = Path(__file__).resolve().parents[3]

CONTRACT_PATH = (
    ROOT
    / "research/week15/contracts/"
    "adaptive_cgs_freeze.yaml"
)

CONTRACT_HASH_PATH = Path(
    str(CONTRACT_PATH) + ".sha256"
)

MANIFEST_PATH = (
    ROOT
    / "research/week15/audit/"
    "adaptive_cgs_authority_manifest.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def load_contract() -> dict:
    # The .yaml file deliberately uses the JSON subset of YAML 1.2.
    return json.loads(
        CONTRACT_PATH.read_text(
            encoding="utf-8"
        )
    )


def load_manifest() -> dict:
    return json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )


def referenced_authority_ids(
    value,
) -> set[str]:
    result: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if (
                    key == "authority"
                    and isinstance(child, list)
                ):
                    result.update(child)
                else:
                    walk(child)

        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return result


def test_contract_sidecar_hash_matches_exact_bytes():
    expected = (
        CONTRACT_HASH_PATH
        .read_text(encoding="utf-8")
        .split()[0]
    )

    assert sha256(CONTRACT_PATH) == expected


def test_required_freeze_fields_are_contract_driven_and_complete():
    contract = load_contract()

    required = contract[
        "required_freeze_fields"
    ]
    freeze = contract["freeze"]

    assert required
    assert len(required) == len(set(required))

    assert set(required) == set(freeze)

    for field in required:
        assert freeze[field] not in (
            None,
            "",
            {},
            [],
        )


def test_authority_manifest_pointer_matches_current_manifest():
    contract = load_contract()

    assert (
        contract["provenance"]
        ["authority_manifest"]
        ["sha256"]
        == sha256(MANIFEST_PATH)
    )


def test_every_contract_authority_resolves_and_source_hash_matches():
    contract = load_contract()
    manifest = load_manifest()

    records = {
        record["authority_id"]: record
        for record in manifest["authorities"]
    }

    referenced = referenced_authority_ids(
        contract["freeze"]
    )

    assert referenced
    assert referenced <= set(records)

    for authority_id in referenced:
        record = records[authority_id]

        source = ROOT / record["path"]

        assert source.is_file(), (
            authority_id,
            source,
        )

        assert sha256(source) == record["sha256"], (
            authority_id,
            source,
        )


def test_week13_selected_hyperparameters_match_contract():
    freeze = load_contract()["freeze"]

    assert (
        SELECTED_EPSILON
        == freeze["epsilon"]["value"]
        == 0.10
    )

    assert (
        SELECTED_ALPHA
        == freeze["alpha"]["value"]
        == 0.5
    )

    assert (
        SELECTED_Q_FLOOR
        == freeze["q_floor"]["value"]
        == 0.05
    )

    assert (
        SELECTED_NOMINAL_BATCH
        == freeze["batch_semantics"]
        ["nominal_batch"]
        == 500
    )


def test_historical_week10_alpha_is_not_final_authority():
    alpha = (
        load_contract()
        ["freeze"]
        ["alpha"]
    )

    assert alpha["value"] == 0.5

    assert (
        alpha[
            "historical_week10_engineering_value"
        ]
        == 0.30
    )

    assert (
        alpha[
            "historical_value_is_final_authority"
        ]
        is False
    )


def test_arm_order_taxonomy_and_distance_match_contract():
    arm_contract = (
        load_contract()
        ["freeze"]
        ["arm_taxonomy"]
    )

    expected_order = arm_contract[
        "arm_order"
    ]

    assert [
        arm.value
        for arm in ARM_ORDER
    ] == expected_order

    assert len(ARM_ORDER) == 10

    for arm in ARM_ORDER:
        spec = get_template(arm)

        expected = (
            arm_contract["arms"][arm.value]
        )

        assert (
            spec.hazard_class
            == expected["name"]
        )

        assert (
            spec.distance.value
            == expected["distance"]
        )


def test_initial_q_and_q_floor_constants_match_contract():
    freeze = load_contract()["freeze"]

    assert (
        Q_INIT
        == freeze["initialization"]
        ["q_all_arms"]
        == 0.0
    )

    assert (
        DEFAULT_Q_FLOOR
        == freeze["q_floor"]["value"]
        == 0.05
    )

    assert (
        freeze["initialization"]
        ["mandatory_initial_one_pull_per_arm"]
        is False
    )


def test_action_selection_contract_freezes_exact_boundary_rule():
    selection = (
        load_contract()
        ["freeze"]
        ["action_selection"]
    )

    assert (
        selection["algorithm"]
        == "epsilon_greedy"
    )

    assert (
        selection["epsilon_comparison"]
        == "epsilon_draw < epsilon"
    )

    assert (
        selection["exploration_candidates"]
        == "uniform_A0_through_A9"
    )

    assert (
        selection["exploitation_rule"]
        == "maximum_Q"
    )

    assert (
        selection["exact_maximum_tie_break"]
        == (
            "seeded_uniform_over_"
            "tied_max_Q_arms"
        )
    )

    assert (
        selection[
            "first_index_argmax_allowed"
        ]
        is False
    )


def test_seed_derivation_matches_independent_contract_formula():
    contract = (
        load_contract()
        ["freeze"]
        ["seed_handling"]
    )

    assert (
        SEED_DOMAIN
        == contract["seed_domain"]
        == "week10-adaptive-cgs-v1"
    )

    root_seed = 20260921

    expected = {}

    for subsystem in (
        "decision",
        "target",
        "realization",
    ):
        message = (
            f"{SEED_DOMAIN}|"
            f"{root_seed}|"
            f"{subsystem}"
        )

        digest = hashlib.sha256(
            message.encode("utf-8")
        ).digest()

        expected[subsystem] = int.from_bytes(
            digest[:8],
            byteorder="big",
            signed=False,
        )

    actual = derive_campaign_seeds(
        root_seed
    )

    assert (
        actual.decision_seed
        == expected["decision"]
    )

    assert (
        actual.target_seed
        == expected["target"]
    )

    assert (
        actual.realization_seed
        == expected["realization"]
    )

    assert len(
        {
            actual.decision_seed,
            actual.target_seed,
            actual.realization_seed,
        }
    ) == 3


def test_single_distance_targeting_is_uncovered_first():
    all_regs = frozenset(
        POSITIVE_REGISTERS
    )

    coverage = L2IntentCoverageState(
        d1_covered=(
            all_regs - {17}
        )
    )

    target = RegisterTargetPolicy(
        Random(1234)
    ).select(
        ArmID.A0,
        coverage,
    )

    assert target == TargetSelection(
        d1=17
    )


def test_a4_targeting_maximizes_two_uncovered_opportunities():
    all_regs = frozenset(
        POSITIVE_REGISTERS
    )

    coverage = L2IntentCoverageState(
        d1_covered=(
            all_regs - {17}
        ),
        d2_covered=(
            all_regs - {23}
        ),
    )

    target = RegisterTargetPolicy(
        Random(4321)
    ).select(
        ArmID.A4,
        coverage,
    )

    assert target == TargetSelection(
        d1=17,
        d2=23,
    )

    assert target.d1 != target.d2


def test_filler_policy_matches_frozen_four_to_one_contract():
    filler_contract = (
        load_contract()
        ["freeze"]
        ["template_filler_policy"]
    )

    assert (
        TARGETED_INSTRUCTIONS_PER_FILLER
        == 4
    )

    assert (
        filler_contract[
            "targeted_to_campaign_filler_ratio"
        ]
        == "4:1"
    )

    assert (
        FILLER_LUI_IMM20
        == 0x13579
    )

    assert (
        select_auxiliary_register(
            {1, 2, 3}
        )
        == 4
    )

    filler = build_filler_instruction(
        kind=FillerKind.CAMPAIGN_BACKGROUND,
        protected_registers={1, 2, 3},
    )

    assert filler.rd == 4
    assert filler.reads == ()
    assert filler.writes == (4,)


def test_reward_uses_only_new_attributable_bin_and_actual_denominator():
    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(
            d1=7
        ),
        covered_at_epoch_start=(),
    )

    attributable = L2IntentBin(
        distance=Distance.D1,
        register=7,
    )

    incidental = L2IntentBin(
        distance=Distance.D2,
        register=8,
    )

    tracker.record_attributable_intent_hit(
        attributable
    )

    # Globally valid Intent, but not attributable
    # to the selected A0 target.
    tracker.record_intent_hit(
        incidental
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.global_new_count == 2
    assert result.attributable_new_count == 1

    assert result.reward == 2.0


def test_zero_new_attributable_bins_produce_zero_reward():
    already_covered = L2IntentBin(
        distance=Distance.D1,
        register=7,
    )

    tracker = EpochRewardTracker(
        arm_id=ArmID.A0,
        target=TargetSelection(
            d1=7
        ),
        covered_at_epoch_start={
            already_covered
        },
    )

    tracker.record_attributable_intent_hit(
        already_covered
    )

    result = tracker.finalize(
        actual_executed_instructions=500
    )

    assert result.attributable_new_count == 0
    assert result.reward == 0.0


def test_batch_semantics_do_not_claim_fixed_epoch_count():
    batch = (
        load_contract()
        ["freeze"]
        ["batch_semantics"]
    )

    assert batch["nominal_batch"] == 500

    assert (
        batch[
            "ordinary_epoch_may_overshoot_nominal_batch"
        ]
        is True
    )

    assert (
        batch[
            "epoch_count_is_fixed_by_budget_divided_by_batch"
        ]
        is False
    )


def test_exact_n_stopping_contract_is_not_epoch_rounded():
    stopping = (
        load_contract()
        ["freeze"]
        ["stopping_rule"]
    )

    assert (
        stopping[
            "successful_fixed_budget_condition"
        ]
        == "accepted == configured_N"
    )

    assert (
        stopping[
            "round_to_epoch_boundary"
        ]
        is False
    )

    assert (
        stopping[
            "round_to_template_boundary"
        ]
        is False
    )

    assert (
        stopping[
            "post_cut_clock_edges_allowed"
        ]
        == 0
    )


def test_reproducibility_matrix_uses_only_nonfinal_seeds():
    repro = (
        load_contract()
        ["freeze"]
        ["reproducibility_rule"]
    )

    matrix = repro[
        "qualification_matrix"
    ]

    assert [
        item["seed"]
        for item in matrix
    ] == [
        15001,
        15002,
        15003,
    ]

    assert [
        item["accepted_budget"]
        for item in matrix
    ] == [
        10000,
        10000,
        100000,
    ]

    assert all(
        item["repetitions"]
        == ["A", "B"]
        for item in matrix
    )

    assert (
        repro[
            "qualification_seed_is_final_seed"
        ]
        is False
    )

    assert (
        repro[
            "final_m3_seed_namespace"
        ]
        == "3001..3015"
    )


def test_gate_metrics_do_not_contain_performance_threshold():
    repro = (
        load_contract()
        ["freeze"]
        ["reproducibility_rule"]
    )

    assert (
        repro[
            "performance_threshold_is_gate_condition"
        ]
        is False
    )

    assert (
        repro[
            "coverage_level_is_gate_condition"
        ]
        is False
    )

    assert (
        repro[
            "exploration_count_is_gate_condition"
        ]
        is False
    )


def test_requalification_rule_forbids_selective_rerun():
    rule = (
        load_contract()
        ["freeze"]
        ["requalification_rule"]
    )

    assert (
        rule["silent_rerun_allowed"]
        is False
    )

    assert (
        rule[
            "selective_success_retention_allowed"
        ]
        is False
    )

    assert (
        rule[
            "after_execution_affecting_fix"
        ]
        == "rerun_entire_qualification_matrix"
    )

    assert (
        rule[
            "old_evidence_status_after_fix"
        ]
        == "SUPERSEDED"
    )
