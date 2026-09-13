# RTL Characteristics

## 1. Repository
- Repository: https://github.com/estufa-cin-ufpe/RISC-V-Pipeline.git
- Commit: 0df37c9a1c32c6fc8e87bfcb2cd4b6dab7f21685
- Date: 2026-09-13
- HDL: SystemVerilog / Verilog
- Simulator: Icarus Verilog (iverilog)

## 2. Top-level
- Top module: riscv (Testbench: tb_top)
- Clock: clk (kích hoạt ở posedge cho Datapath, negedge cho RegFile và IMEM)
- Reset: reset
- Reset polarity: Active-High (reset = 1)
- Reset synchronous/asynchronous: Synchronous (posedge clk)

## 3. Instruction Memory
- Module/file: design/instructionmemory.sv bọc design/Memoria32.sv
- Memory element width: 8 bit (ghép 4 byte song song thành từ lệnh 32 bit)
- Number of elements: 65,536 elements mỗi bank (4 banks)
- Total capacity: 64 KiB logic (thực tế bị giới hạn 512 Byte do bus PC chỉ rộng 9 bit)
- Address input: PC (9 bit mở rộng lên 32 bit)
- Address interpretation: Byte address (truy xuất addr + 0, + 1, + 2, + 3)
- Read behavior: Synchronous tại sườn âm xung nhịp (~clk)
- Initialization mechanism: Altera MIF (altsyncram init_file)
- Initialization file: instruction.mif
- Evidence:
  - File: design/Memoria32.sv (Line 35, 37-40, 60-63, 70-78)
  - File: design/Datapath.sv (Line 92-95)
  - File: design/instructionmemory.sv (Line 5, 18)
  - File: design/ramOnChip32.v (Line 96, 101)

## 4. Register File
- Module/file: design/RegFile.sv
- Number of registers: 32
- Register width: 32 bit
- Read ports: 2 cổng bất đồng bộ (rg_rd_addr1, rg_rd_addr2)
- Write ports: 1 cổng đồng bộ (rg_wrt_dest, rg_wrt_data)
- x0 behavior: Không hardwire về 0 (lỗi thiết kế: có thể bị ghi đè nếu rd = x0)
- Read timing: Combinational / Asynchronous (assign trực tiếp)
- Write timing: Synchronous tại sườn âm xung nhịp (negedge clk)
- Reset behavior: Synchronous (negedge clk), xóa toàn bộ 32 thanh ghi về 0
- Bypass behavior: Không có bypass nội bộ
- Evidence:
  - File: design/RegFile.sv
  - Line: 5-7, 26, 28, 30-34, 38-39

## 5. Pipeline
- Stages: 5 stages (IF, ID, EX, MEM, WB)
- Pipeline registers: IF/ID (IF_ID_Reg), ID/EX, EX/MEM, MEM/WB
- Branch resolution stage: EX stage (BranchUnit)
- Forwarding sources: ForwardingUnit (từ EX/MEM và MEM/WB về EX)
- Stall condition: HazardDetection (phát hiện Load-Use hazard)
- Flush condition: Phát hiện rẽ nhánh hợp lệ (PcSel) hoặc Reset

## 6. Uncertainties
- Cơ chế nạp mã mô phỏng: ramOnChip32 dùng IP Altera (.mif), cần xem xét khả năng tương thích khi mô phỏng bằng Icarus Verilog hoặc thay thế bằng $readmemh.
- Lỗi logic x0: Cần chú ý khi viết test không ghi đè vào thanh ghi x0.
