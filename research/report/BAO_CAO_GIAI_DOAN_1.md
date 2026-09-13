# BÁO CÁO GIAI ĐOẠN 1 (TUẦN 1–2)
## Khảo sát và Baseline Verification bộ xử lý RISC-V 5-Stage Pipeline

| Mục | Thông tin |
|---|---|
| Người thực hiện | [Họ tên — MSSV] |
| Repo | https://github.com/LongTruong111/riscv-pipeline-research |
| Repo gốc khảo sát | github.com/AngeloJacobo/RISC-V-5-Stage-Pipelined-Processor |
| Công cụ | Icarus Verilog, GTKWave, Git |

## 1. Mục tiêu
1. Khảo sát kiến trúc RTL bộ xử lý RISC-V pipeline 5 stage
2. Xây dựng golden trace cho chương trình tuần tự và chương trình RAW hazard
3. Port mô phỏng từ IP Altera sang Icarus Verilog + GTKWave
4. Kiểm chứng hành vi pipeline đối chiếu golden trace

## 2. Tổng quan đối tượng
RTL SystemVerilog target FPGA; pipeline IF/ID/EX/MEM/WB; có ForwardingUnit + HazardDetection.
Cây hierarchy (instance): tb_top → riscV → dp → pcreg, pcmux, pcadd, instr_mem, data_mem, rf,
Ext_Imm, alu_module, ac, c, detect, forunit, FAmux, FBmux, A(IF/ID), B(ID/EX), C(EX/MEM), D(MEM/WB).

## 3. Tuần 1 — Khảo sát
- 3.1 Workspace + nhánh research/rtl-reconnaissance (9cbf26d)
- 3.2 Khảo sát cấu trúc repo → RECONNAISSANCE_LOG.md (00ab75a)
- 3.3 Audit IMEM & Register File → RTL_CHARACTERISTICS.md [điền 3 dòng kết luận chính] (802f0a0)
- 3.4 Endianness (little-endian, 1 byte/dòng) + mapping địa chỉ → MEMORY_ENDIANNESS.md (8da0c67)
- 3.5 Golden trace: Trace A + Program B (I0: addi x1,x0,10; I1: addi x2,x1,5; I2: add x3,x2,x1)
  - Hazard Analysis: I1 phụ thuộc x1(I0) kc 1; I2 phụ thuộc x2(I1) kc 1 và x1(I0) kc 2
  - Kỳ vọng: forwarding C3 (ngõ A I1 = 10), C4 (ngõ A I2 = 15, ngõ B I2 = 10); 0 stall; x1=10, x2=15, x3=25

## 4. Tuần 2 — Baseline verification
### 4.1 Port môi trường mô phỏng (a898f78)
- altsyncram (IP Altera) → RAM behavioral + $readmemh — bắt buộc vì iverilog không chạy IP Altera
- Fix: always_ff @(*) → always @*; always_comb → always @*
- Build: research/build.sh — RegPack.sv đứng TRƯỚC vì package phải compile trước file import
- Known limitation iverilog: "constant selects in always_*" (alu.sv:41) — vô hại

### 4.2 Chương trình test
- ALU test 27 lệnh (addi, or, add, sll, srl, sra, slt, sltu, sub, xori, ori, andi, xor) — có RAW ở đầu
- Program B tối giản 3 lệnh, encode tay: 93 00 a0 00 | 13 81 50 00 | b3 01 11 00
### 4.3 Kết quả (e8312bb)
Console Program B: x1=10 (0x0a), x2=15 (0x0f), x3=25 (0x19) — khớp 100% kỳ vọng.
| Kiểm tra | Kết quả |
|---|---|
| Reset giữ PC khi reset=1 | ✅ |
| PC tăng đều từng chu kỳ | ✅ |
| Forwarding bật (Forward_A 0→01) | ✅ |
| Register writes khớp kỳ vọng | ✅ |
| Phụ: add x3,x2,x2 → 30=15+15 → forward cả 2 ngõ ALU | ✅ |

### 4.4 Signal inventory — checkpoint 8
Lớp A (architectural): PC, instruction, RF · Lớp B (microarch): stall, Forward_A/B, pipeline regs ·
Lớp C (derived): loại lệnh/cycle, số forward, số stall → research/signals/SIGNAL_INVENTORY.md

### 4.5 Probe test — checkpoint 9 (2f53fa4)
P1 RAW forwarding · P2 forward 2 ngõ · P3 reset · P4 PC — PASS hết → research/signals/PROBE_TEST.md

## 5. Kết quả chính
Pipeline baseline đúng golden trace: RAW xử lý bằng forwarding, 0 stall. Golden trace được
kiểm chứng TRỰC TIẾP bằng test tối giản (mạnh hơn so với chỉ xem waveform).

## 6. Vấn đề & giải quyết
| # | Vấn đề | Nguyên nhân | Giải pháp |
|---|---|---|---|
| 1 | Compile lỗi Datapath.sv:34 | import package khi package chưa compile | RegPack.sv đứng đầu lệnh iverilog |
| 2 | $readmemh warning [0:65535] | hex ít hơn 64K từ | Vô hại |
| 3 | Không thấy PC/ForwardingUnit | tên instance viết tắt | pcreg.q / forunit / detect |
| 4 | x3=30 thay vì 25 | encode nhầm rs1/rs2 | encode lại → 25 (30 vô tình chứng minh forward 2 ngõ) |
| 5 | 403 khi push | token thiếu scope repo | gh auth login |

## 7. Kết luận & hướng tuần 3
Baseline chắc chắn, sẵn sàng thí nghiệm vi kiến trúc. Tuần 3: test load/store (data.hex có dữ liệu)
+ probe load-use stall (detect.stall); test branch + flush; đo độ phủ lệnh theo lớp C.

## 8. Phụ lục
- Build & chạy: bash research/build.sh
- Waveform: gtkwave research/waveforms/baseline.gtkw
- Lịch sử: git log --oneline — 9 commit nghiên cứu trên nhánh research/rtl-reconnaissance
