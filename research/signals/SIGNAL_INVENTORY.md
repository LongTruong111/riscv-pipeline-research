# SIGNAL_INVENTORY

Nguồn: baseline.vcd — cây SST GTKWave (tb_top → riscV → dp → ...) + RTL

## Mục A — Architectural observability
| Signal | Đường dẫn | Width | Mô tả |
|---|---|---|---|
| PC | dp.pcreg.q | 9 | Program counter |
| Instruction | dp.instr_mem.get_dataOut | 32 | Lệnh đang fetch |
| x1–x31 | dp.rf | 32×32 | Thanh ghi kiến trúc (instance `rf`) |

## Mục B — Microarchitectural
| Signal | Đường dẫn | Width | Mô tả |
|---|---|---|---|
| stall | dp.detect.stall | 1 | Hazard detection (load-use) |
| Forward_A | dp.forunit.Forward_A | 2 | Chọn nguồn rs1 (00=RegFile, 01/10=forward) |
| Forward_B | dp.forunit.Forward_B | 2 | Chọn nguồn rs2 |
| rs1 sau forwarding | dp.FAmux.y | 32 | Giá trị rs1 forwarding tới ALU |
| rs2 sau forwarding | dp.FBmux.y | 32 | Giá trị rs2 forwarding tới ALU |
| IF_ID reg | dp.A | struct (Pipe_Buf_Reg_PKG) | Pipeline register IF→ID |
| ID_EX reg | dp.B | struct | Pipeline register ID→EX |
| EX_MEM reg | dp.C | struct | Pipeline register EX→MEM |
| MEM_WB reg | dp.D | struct | Pipeline register MEM→WB |

## Mục C — Derived coverage
- Loại lệnh mỗi cycle (R/I/load/store/branch/...)
- Số lần Forward_A/B ≠ 00 (forwarding events), số chu kỳ stall=1
