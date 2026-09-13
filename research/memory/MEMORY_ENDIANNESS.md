# Memory Addressing and Endianness

## 1. Instruction Memory Representation

- Memory element width: 8 bit (4 song song tạo thành từ lệnh 32 bit)
- Address input width: 16 bit (hiệu dụng từ raddress[15:0]), giới hạn bởi PC 9 bit
- PC representation: Byte address (tăng 4 đơn vị mỗi chu kỳ lệnh thông thường)
- PC-to-memory mapping: Byte-addressed memory (Case B). memBlock0 = PC+0, memBlock1 = PC+1, memBlock2 = PC+2, memBlock3 = PC+3

## 2. Initialization

- System task: Altera MIF parameter / $readmemh qua testbench
- Input file: verif/instructions.txt (hoặc instruction.mif cho FPGA)
- One line represents: 32-bit instruction (hexadecimal) hoặc từng byte tùy bộ nạp
- Example line: 00100093 (addi x1, x0, 1)
- Expected memory element value: 
  - mem[PC+0] = 0x93
  - mem[PC+1] = 0x00
  - mem[PC+2] = 0x10
  - mem[PC+3] = 0x00

## 3. Endianness

- Byte ordering: Little-Endian
- Evidence from RTL: design/Memoria32.sv dòng 60-63: Dataout = {outS3, outS2, outS1, outS0} tương ứng với {mem[addr+3], mem[addr+2], mem[addr+1], mem[addr+0]}
- Evidence from simulation: Sườn âm clock đọc 4 byte ghép thành instruction hợp lệ khớp với định dạng RV32I
- Conclusion: Memory interface là Little-Endian chuẩn RISC-V.

## 4. Probe Result

| PC   | Expected instruction | Observed instruction | Result |
|:---  |:-------------------- |:-------------------- |:------ |
| 0x00 | addi x1, x0, 1       | 0x00100093           | PASS   |
| 0x04 | addi x2, x0, 2       | 0x00200113           | PASS   |
| 0x08 | addi x3, x0, 3       | 0x00300193           | PASS   |
| 0x0C | nop (addi x0, x0, 0) | 0x00000013           | PASS   |

## 5. Risks

- Phụ thuộc IP Altera: Module `ramOnChip32` dùng thư nguyên mẫu `altsyncram`, nếu mô phỏng bằng Icarus Verilog thuần có thể cần thay thế wrapper hoặc nạp thẳng mảng bộ nhớ.
- Độ rộng PC 9-bit: Giới hạn tối đa địa chỉ lệnh ở 512 byte (0x1FF).
