# T5 Input Baseline

## 1. Purpose

This document freezes the technical inputs inherited from GĐ1 before
the T5 vPlan, Hazard Space, Hazard Truth Table, coverage model, CGS
policy, and experimental protocol are defined.

Dependency chain:

DUT Freeze
→ Timing Contract
→ Signal Inventory
→ Hazard Space
→ Coverage Model
→ Experimental Protocol.

Expected behavior shall not be derived solely from the current RTL
implementation. Architectural semantics and intended microarchitecture
must remain distinguishable from observed RTL behavior.

---

## 2. DUT Baseline

### 2.1 Frozen DUT

* Frozen commit:
  `e0c1ae1e35f55630fd27116a19af53a19c5243bd`
* Baseline tag:
  `DUT_BASELINE_T3`
* Freeze artifact:
  `research/week3/RTL_FREEZE.md`
* Freeze boundary:

  * `design/`
  * DUT-related files under `verif/`

### 2.2 Current repository state

- Research branch:
  `research/week5-vplan`
- Current repository HEAD:
  `ae34d02...`
- Complete GĐ1 gate tag:
  `GATE_GD1_COMPLETE`
- Frozen DUT baseline:
  `DUT_BASELINE_T3`
- Frozen DUT commit:
  `e0c1ae1e35f55630fd27116a19af53a19c5243bd`

The current repository HEAD contains the completed GĐ1 verification
artifacts and Week-4 timing infrastructure.

The current repository HEAD is not used as the DUT identity.

The DUT identity for T5 remains:

`DUT_BASELINE_T3`

at commit:

`e0c1ae1e35f55630fd27116a19af53a19c5243bd`.

No modification to the frozen `design/` or DUT-related `verif/`
boundary is present between `DUT_BASELINE_T3` and the current T5
baseline.

### 2.3 Post-freeze integrity

Checks performed:

```bash
git diff --name-status e0c1ae1..HEAD -- design verif
git diff --stat e0c1ae1..HEAD -- design verif
git status --short design verif
```

Observed result:

All three commands produced no output.

Therefore no tracked or local modifications to the frozen DUT boundary
were observed between `DUT_BASELINE_T3` and the current repository
state.

**Status: PASS**

### 2.4 Freeze claim limitation

Gate T3 established a stable DUT baseline through:

1. an independent three-instruction ADDI smoke test;
2. automated architectural checking;
3. waveform-level reset, PC, fetch, stall, and pipeline inspection.

This establishes DUT stability only.

It does not establish complete functional verification of the
processor.

---

## 3. Signal Inventory Baseline

Source artifact:

`research/signals/SIGNAL_INVENTORY.md`

**Status: PASS**

The GĐ1 Signal Inventory provides the baseline observability map for:

- architectural state;
- pipeline registers;
- forwarding controls;
- stall indication;
- forwarded operand values.

The original GĐ1 inventory is sufficient for high-level observability
but does not explicitly enumerate every field required by the T5 hazard
model.

Therefore, T5 maintains a field-level extension in:

`research/week5/vplan/HAZARD_SIGNAL_MAP.md`

The T5 extension completes the required mapping for:

- source registers (`rs1`, `rs2`);
- destination register (`rd`);
- instruction/opcode identity;
- pipeline-stage instruction state;
- register-write enable;
- forwarding control for operand A;
- forwarding control for operand B;
- stall/interlock;
- flush/control redirect;
- writeback destination;
- writeback data;
- bubble/validity semantics.

The original GĐ1 Signal Inventory remains unchanged.

No signal name shall be invented in T5. RTL hierarchy names and
pipeline fields must originate from either:

1. `research/signals/SIGNAL_INVENTORY.md`; or
2. direct inspection of the frozen RTL documented in
   `research/week5/vplan/HAZARD_SIGNAL_MAP.md`.

---

## 4. Timing Contract Baseline

Source evidence:

- Week-4 commit:
  `77fc28e9f4a95e1f7b4f27a402d7e29af487dba5`
- `research/week4/TIMING_RULES.md`
- `research/week4/race_demonstration.md`
- `tests/timing_utils.py`

Frozen T5 contract:

`research/week5/vplan/TIMING_CONTRACT.md`

Rules:

- functional drive: `FallingEdge(clk)`;
- sequential observation: `RisingEdge(clk) -> ReadOnly()`;
- reset deassertion away from active sampling edge;
- one clock owner per clock;
- no same-timestamp observe-and-dependent-drive feedback;
- shared timing helpers shall preserve these semantics.

The Week-4 probe used active-low reset, but reset polarity is
DUT-specific. T5 inherits the timing rule, not the probe's polarity.

**Status: PASS**

---

## 5. Hazard-Specific RTL Checks

| Check                                             |  Status  |
|---------------------------------------------------|----------|
| `rd != 0` gate in forwarding logic                |   PASS   |
| d3 / register-file write-read behavior            |   PASS   |
| forwarding priority when multiple producers match |   PASS   |
| exact load-use stall predicate                    |   PASS   |
| stall/flush interaction                           |   PASS   |

---

## 6. Step-0 Status

Current status:

** PASS **

Completed:

- [x] Frozen DUT identified.
- [x] Baseline tag verified.
- [x] Freeze boundary verified unchanged.
- [x] Signal Inventory reviewed and extended by the T5 hazard map.
- [x] Timing Contract extracted and frozen.
- [x] x0 forwarding behavior checked.
- [x] d3/write-read behavior checked.
- [x] forwarding priority checked.
- [x] load-use behavior checked.
- [x] stall/flush behavior checked.

---

## 7. Final Status

`PASS / FROZEN`

The T5 input baseline, DUT freeze boundary, signal mapping, and timing
assumptions are complete and frozen for Gate T5.
