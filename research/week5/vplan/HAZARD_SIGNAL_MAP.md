# Hazard Signal Map — T5

## 1. Purpose

This document extends the GĐ1 Signal Inventory with the exact RTL
fields required by the T5 hazard model and coverage collector.

Baseline sources:

- `research/signals/SIGNAL_INVENTORY.md`
- frozen DUT tag: `DUT_BASELINE_T3`
- frozen DUT commit:
  `e0c1ae1e35f55630fd27116a19af53a19c5243bd`

The original GĐ1 Signal Inventory is preserved unchanged.

---

## 2. Pipeline Register Mapping

| Stage boundary | RTL object | Relevant fields |
|---|---|---|
| IF/ID | `dp.A` | `Curr_Instr` |
| ID/EX | `dp.B` | `Curr_Instr`, `RS_One`, `RS_Two`, `rd`, `RegWrite`, `MemRead` |
| EX/MEM | `dp.C` | `Curr_Instr`, `rd`, `RegWrite` |
| MEM/WB | `dp.D` | `Curr_Instr`, `rd`, `RegWrite` |

Field definitions originate from `design/RegPack.sv`.

---

## 3. Hazard-Relevant Signal Mapping

| Semantic | RTL path / expression | Stage | Status |
|---|---|---|---|
| Decode rs1 | `dp.A.Curr_Instr[19:15]` | ID | KNOWN |
| Decode rs2 | `dp.A.Curr_Instr[24:20]` | ID | KNOWN |
| Decode rd | `dp.A.Curr_Instr[11:7]` | ID | KNOWN |
| EX rs1 index | `dp.B.RS_One` | EX | KNOWN |
| EX rs2 index | `dp.B.RS_Two` | EX | KNOWN |
| EX destination | `dp.B.rd` | EX | KNOWN |
| EX/MEM destination | `dp.C.rd` | MEM | KNOWN |
| MEM/WB destination | `dp.D.rd` | WB | KNOWN |
| EX RegWrite | `dp.B.RegWrite` | EX | KNOWN |
| EX/MEM RegWrite | `dp.C.RegWrite` | MEM | KNOWN |
| MEM/WB RegWrite | `dp.D.RegWrite` | WB | KNOWN |
| EX load indicator | `dp.B.MemRead` | EX | KNOWN |
| Forward A control | `dp.forunit.Forward_A` / `FAmuxSel` | EX | KNOWN |
| Forward B control | `dp.forunit.Forward_B` / `FBmuxSel` | EX | KNOWN |
| Forwarded rs1 value | `dp.FAmux.y` | EX | KNOWN |
| Forwarded rs2 value | `dp.FBmux.y` | EX | KNOWN |
| Stall | `dp.detect.stall` / `Reg_Stall` | ID/EX interlock | KNOWN |
| Flush/control redirect | `dp.PcSel` | EX/control | KNOWN |
| Instruction at IF/ID | `dp.A.Curr_Instr` | ID | KNOWN |
| Instruction at ID/EX | `dp.B.Curr_Instr` | EX | KNOWN |
| Instruction at EX/MEM | `dp.C.Curr_Instr` | MEM | KNOWN |
| Instruction at MEM/WB | `dp.D.Curr_Instr` | WB | KNOWN |
| WB data | — inspect Datapath WB mux | WB | KNOW |
| Explicit valid bit | none found | — | ABSENT |

---

## 4. Instruction-Type Reconstruction

The DUT carries `Curr_Instr` through the pipeline registers.

Therefore ProducerType and ConsumerType can be derived from the
instruction opcode rather than inferred solely from control signals.

Decode-stage opcode:

`dp.A.Curr_Instr[6:0]`

Relevant controller behavior includes:

- `RegWrite`
- `MemRead`
- `MemWrite`
- `Branch`
- `JalrSel`

Exact T5 ProducerType/ConsumerType classes will be frozen in the
Hazard Space definition.

---

## 5. x0 Forwarding Rule

`design/ForwardingUnit.sv` explicitly gates forwarding using:

~~~systemverilog
EX_MEM_rd != 0
MEM_WB_rd != 0
~~~

for both source operands.

Therefore an architectural write targeting `x0` does not become a
forwarding dependency.

**Status: PASS**

Note:

The separately documented Register File x0 issue must not be confused
with forwarding logic. The forwarding unit itself correctly excludes
`rd == 0`.

---

## 6. Forwarding Priority

For both source operands, the forwarding selection has the form:

~~~text
EX/MEM match
→ otherwise MEM/WB match
→ otherwise RegFile
~~~

Encoding observed:

~~~text
10 = EX/MEM
01 = MEM/WB
00 = RegFile
~~~

Therefore when EX/MEM and MEM/WB both match the same consumer source,
EX/MEM takes priority.

This corresponds to selecting the newer producer.

**Status: PASS**

---

## 7. Stall Mapping

Load-use detection is instantiated as:

~~~text
HazardDetection(
    A.Curr_Instr[19:15],
    A.Curr_Instr[24:20],
    B.rd,
    B.MemRead,
    Reg_Stall
)
~~~

Thus the hazard detector compares decode-stage source fields against
the destination register of the instruction currently in ID/EX.

The exact boolean predicate remains to be verified directly from
`design/HazardDetection.sv`.

**KNOWN RTL BEHAVIOR / FALSE-STALL RISK**
**Status: PASS**

---

## 8. Flush Mapping

`PcSel` is used as the pipeline control redirect / flush condition.

Observed behavior in `Datapath.sv`:

- IF/ID state is cleared on `reset || PcSel`;
- ID/EX state is cleared on
  `reset || Reg_Stall || PcSel`.

No explicit pipeline `valid` bit was found.

Therefore pipeline validity cannot be modeled using a nonexistent
`valid` signal. T5 must instead define validity/bubble semantics from
instruction/control contents produced by reset, stall, and flush.

Status:

**Status: PASS**

---

## 9. Register-File and d3 Semantics

`design/RegFile.sv` implements:

- write at `negedge clk`;
- asynchronous/combinational register reads;
- no architectural hardwire protecting `x0`.

The relevant RTL behavior is:

~~~systemverilog
always @(negedge clk)
begin
    if (rst == 1'b1)
        ...
    else if (rg_wrt_en == 1'b1)
        register_file[rg_wrt_dest] <= rg_wrt_data;
end

assign rg_rd_data1 = register_file[rg_rd_addr1];
assign rg_rd_data2 = register_file[rg_rd_addr2];
~~~

Therefore a value committed by the WB stage at the falling edge becomes
visible through the register-file read ports before the following
rising edge.

For the T5 hazard model, the d3 case is therefore interpreted as
phase-separated WB-to-ID register-file visibility rather than a
dedicated forwarding path.

A consumer reaching ID while its producer is in WB can observe the
updated value through the register file before the next ID/EX capture.

Status:

**PASS**

### x0 Register-File Limitation

The register file allows writes to register index zero because no
`rg_wrt_dest != 0` condition is present.

Reads from register zero are also not explicitly forced to constant
zero.

Therefore the DUT contains a confirmed Register File x0 semantic
defect.

This defect is separate from the ForwardingUnit behavior. The
ForwardingUnit correctly excludes `rd == 0`.

Status:

**KNOWN DUT DEFECT**

---

## 10. Load-Use Detection Semantics

The exact predicate implemented by `design/HazardDetection.sv` is:

~~~systemverilog
stall =
    ID_EX_MemRead &&
    ((ID_EX_rd == IF_ID_RS1) ||
     (ID_EX_rd == IF_ID_RS2));
~~~

The detector compares:

- `B.rd` from the ID/EX producer;
- `A.Curr_Instr[19:15]`;
- `A.Curr_Instr[24:20]`.

The detector does not:

- require `ID_EX_rd != 0`;
- qualify whether the consumer opcode actually uses `rs1`;
- qualify whether the consumer opcode actually uses `rs2`.

Therefore the RTL can generate unnecessary stalls when a non-source
instruction bit field happens to match the load destination.

This behavior is treated as a verification target rather than being
silently corrected in the vPlan.

Status:

**KNOWN RTL BEHAVIOR / FALSE-STALL RISK**

---

## 11. Bubble and Validity Semantics

The DUT has no explicit pipeline `valid` bit.

For ID/EX register `B`, the condition:

~~~systemverilog
reset || Reg_Stall || PcSel
~~~

injects a functional bubble by clearing relevant state, including:

- `RegWrite`
- `MemRead`
- `MemWrite`
- `Branch`
- `JalrSel`
- `rd`
- `RS_One`
- `RS_Two`
- associated datapath/control fields

However:

~~~systemverilog
B.Curr_Instr <= A.Curr_Instr;
~~~

is still executed in this bubble path.

Therefore `B.Curr_Instr` alone must not be interpreted as proof that a
valid instruction is executing in EX.

Coverage and monitoring logic must derive validity from functional
control state and pipeline semantics rather than from `Curr_Instr`
alone.

Status:

**PASS**

---

## 12. Writeback Mapping

The architectural writeback interface is:

- write enable: `D.RegWrite`
- destination register: `D.rd`
- write data: `WRMuxResult`
- observable writeback alias: `WB_Data`

The final writeback value is generated by:

~~~text
D.Alu_Result ----\
D.MemReadData ----> resmux ---> WrmuxSrc --\
                                          |
D.Pc_Four ------------------------------- |
D.Imm_Out ------------------------------- |--> wrsmux --> WRMuxResult
D.Pc_Imm --------------------------------/
~~~

The selected value is supplied directly to the Register File:

~~~text
RegFile write data = WRMuxResult
~~~

Status:

**PASS**

---

## 13. RTL-Side Step-0 Summary

Completed:

- frozen DUT identity: PASS
- post-freeze DUT integrity: PASS
- source-register mapping: PASS
- destination-register mapping: PASS
- RegWrite mapping: PASS
- instruction propagation mapping: PASS
- x0 forwarding exclusion: PASS
- forwarding priority: PASS
- flush/control redirect mapping: PASS
- bubble semantics: PASS
- load-use predicate: KNOWN
- d3/register-file timing: PASS
- writeback mapping: PASS

Known DUT limitations retained for verification:

- Register File does not enforce architectural `x0`;
- HazardDetection may generate unnecessary stalls.

Timing dependency:

The simulation timing contract is frozen in:

`research/week5/vplan/TIMING_CONTRACT.md`

Required sampling phase:

`RisingEdge(clk) -> ReadOnly()`

Required normal functional drive phase:

`FallingEdge(clk)`

T5 Hazard Signal Map:

**PASS / FROZEN**
