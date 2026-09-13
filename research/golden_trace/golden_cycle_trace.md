# Golden Cycle Trace

## Trace Convention

- C0: First cycle after reset is deasserted.
- State is sampled immediately after the active clock edge (posedge clk).
- Pipeline stage labels refer to the instruction stored in that stage register.
- PC is recorded at the same sampling edge.

---

## Program A: Sequential ALU (No Hazard)

### Program
asm
I0: addi x1, x0, 1   # PC = 0x00
I1: addi x2, x0, 2   # PC = 0x04
I2: addi x3, x0, 3   # PC = 0x08
I3: addi x4, x0, 4   # PC = 0x0C


### Assumptions
- Reset: Synchronous active-high, deasserted before C0
- Clock: Posedge active
- PC start: 0x00
- Pipeline stages: 5 (IF, ID, EX, MEM, WB)

### Expected Trace

| Cycle | PC   | IF  | ID  | EX  | MEM | WB  | Notes |
|:------|:-----|:----|:----|:----|:----|:----|:------------------------|
| C0    | 0x00 | I0  | -   | -   | -   | -   | Fetch I0                |
| C1    | 0x04 | I1  | I0  | -   | -   | -   | Fetch I1, Decode I0     |
| C2    | 0x08 | I2  | I1  | I0  | -   | -   | Execute I0 (ALU = 1)    |
| C3    | 0x0C | I3  | I2  | I1  | I0  | -   | Execute I1 (ALU = 2)    |
| C4    | 0x10 | -   | I3  | I2  | I1  | I0  | WB I0: x1 = 1           |
| C5    | 0x14 | -   | -   | I3  | I2  | I1  | WB I1: x2 = 2           |
| C6    | 0x18 | -   | -   | -   | I3  | I2  | WB I2: x3 = 3           |
| C7    | 0x1C | -   | -   | -   | -   | I3  | WB I3: x4 = 4           |

---

## Program B: RAW Hazard

### Program
asm
I0: addi x1, x0, 10  # PC = 0x00
I1: addi x2, x1, 5   # PC = 0x04
I2: add  x3, x2, x1  # PC = 0x08


### Hazard Analysis
- Dependency 1: I1 phụ thuộc x1 từ I0 (khoảng cách 1 chu kỳ).
- Dependency 2: I2 phụ thuộc x2 từ I1 (khoảng cách 1 chu kỳ) và x1 từ I0 (khoảng cách 2 chu kỳ).
- Expected forwarding:
  - Chu kỳ C3: Forwarding từ EX/MEM vào ngõ vào A của ALU cho I1 (giá trị 10).
  - Chu kỳ C4: Forwarding từ EX/MEM vào ngõ vào A của ALU cho I2 (giá trị 15); Forwarding từ MEM/WB vào ngõ vào B của ALU cho I2 (giá trị 10).
- Expected stall: Không có (0 stall cycle).
- Expected final register values: x1 = 10, x2 = 15, x3 = 25.

### Expected Trace

| Cycle | PC   | IF  | ID  | EX  | MEM | WB  | Stall | Flush | Forward A | Forward B | RF Write |
|:------|:-----|:----|:----|:----|:----|:----|:------|:------|:----------|:----------|:---------|
| C0    | 0x00 | I0  | -   | -   | -   | -   | 0     | 0     | None      | None      | None     |
| C1    | 0x04 | I1  | I0  | -   | -   | -   | 0     | 0     | None      | None      | None     |
| C2    | 0x08 | I2  | I1  | I0  | -   | -   | 0     | 0     | None      | None      | None     |
| C3    | 0x0C | -   | I2  | I1  | I0  | -   | 0     | 0     | EX/MEM    | None      | None     |
| C4    | 0x10 | -   | -   | I2  | I1  | I0  | 0     | 0     | EX/MEM    | MEM/WB    | x1 = 10  |
| C5    | 0x14 | -   | -   | -   | I2  | I1  | 0     | 0     | None      | None      | x2 = 15  |
| C6    | 0x18 | -   | -   | -   | -   | I2  | 0     | 0     | None      | None      | x3 = 25  |
