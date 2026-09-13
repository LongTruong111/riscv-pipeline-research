# SIGNAL_INVENTORY

Nguồn: baseline.vcd — cây SST GTKWave (tb_top → riscV → dp → ...)

## Mục A — Architectural observability
| Signal | Đường dẫn | Width | Mô tả |
|---|---|---|---|
| PC | dp.pcreg.q | 9 | Program counter |
| Instruction | dp.instr_mem.get_dataOut | 32 | Lệnh đang fetch |
| x1–x31 | dp.<tên-instance-RegFile> | 32 | Thanh ghi kiến trúc |

## Mục B — Microarchitectural
| Signal | Đường dẫn | Width | Mô tả |
|---|---|---|---|
| stall/flush | dp.detect.<output> | ? | Hazard detection |
| forwardA/forwardB | dp.forunit.<output> | 2 | Forwarding select |
| rs1 sau forwarding | dp.FAmux.y | 32 | |
| rs2 sau forwarding | dp.FBmux.y | 32 | |
| Pipeline regs (IF/ID→MEM/WB) | dp.<...> | ? | Điền khi duyệt SST |

## Mục C — Derived coverage
- Loại lệnh mỗi cycle (R/I/load/store/branch/...)
- Số lần forwarding bật, số chu kỳ stall (đếm từ Mục B)
