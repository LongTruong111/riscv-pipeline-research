# RTL Reconnaissance Log

- Repository: https://github.com/estufa-cin-ufpe/RISC-V-Pipeline.git
- Commit: 0df37c9a1c32c6fc8e87bfcb2cd4b6dab7f21685
- Date: 2026-09-13
- Simulator: 
- OS: Linux
- Top module: 
- Initial observations: 

## Repository Structure

- Top module: riscv (Testbench: tb_top)
- Pipeline datapath: design/Datapath.sv
- Control unit: design/Controller.sv, design/ALUController.sv, design/BranchUnit.sv
- Hazard/forwarding unit: design/HazardDetection.sv, design/ForwardingUnit.sv
- Instruction memory: design/instructionmemory.sv
- Register file: design/RegFile.sv
- Testbench: verif/tb_top.sv
- Simulation command: iverilog -g2012 -o sim/sim.out design/*.sv design/*.v verif/tb_top.sv && vvp sim/sim.out
