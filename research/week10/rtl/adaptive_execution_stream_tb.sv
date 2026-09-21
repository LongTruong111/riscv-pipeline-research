`timescale 1ns / 1ps

module adaptive_execution_stream_tb;

    logic clk;
    logic reset;

    logic [31:0] wb_data;
    logic [4:0]  reg_num;
    logic [31:0] reg_data;
    logic        reg_write_sig;

    logic        mem_wr;
    logic        mem_rd;
    logic [8:0]  mem_addr;
    logic [31:0] mem_wr_data;
    logic [31:0] mem_rd_data;

    /*
     * Verification-only instruction-memory backdoor.
     *
     * This does NOT modify frozen DUT RTL. The wrapper writes directly
     * into the four byte banks already instantiated inside the DUT.
     *
     * A word at architectural byte address A is represented as:
     *
     *   memBlock0.mem[A + 0] = word[7:0]
     *   memBlock1.mem[A + 1] = word[15:8]
     *   memBlock2.mem[A + 2] = word[23:16]
     *   memBlock3.mem[A + 3] = word[31:24]
     *
     * The strobe is intentionally independent of the CPU clock so the
     * verification environment can patch an inactive/future location
     * between architectural sampling edges.
     */
    logic        imem_patch_strobe;
    logic [8:0]  imem_patch_addr;
    logic [31:0] imem_patch_data;

    riscv core (
        .clk           (clk),
        .reset         (reset),
        .WB_Data       (wb_data),
        .reg_num       (reg_num),
        .reg_data      (reg_data),
        .reg_write_sig (reg_write_sig),
        .wr            (mem_wr),
        .rd            (mem_rd),
        .addr          (mem_addr),
        .wr_data       (mem_wr_data),
        .rd_data       (mem_rd_data)
    );

    /*
     * Verification-only asynchronous patch event.
     *
     * Addresses are constrained to aligned RV32 instructions in the
     * executable 9-bit PC window. The final valid word starts at 508.
     */
    always @(posedge imem_patch_strobe) begin
        if (imem_patch_addr[1:0] != 2'b00) begin
            $fatal(
                1,
                "IMEM patch address must be 4-byte aligned: %0d",
                imem_patch_addr
            );
        end

        if (imem_patch_addr > 9'd508) begin
            $fatal(
                1,
                "IMEM patch address outside executable word range: %0d",
                imem_patch_addr
            );
        end

        core.dp.instr_mem.meminst.memBlock0.mem[
            imem_patch_addr
        ] = imem_patch_data[7:0];

        core.dp.instr_mem.meminst.memBlock1.mem[
            imem_patch_addr + 9'd1
        ] = imem_patch_data[15:8];

        core.dp.instr_mem.meminst.memBlock2.mem[
            imem_patch_addr + 9'd2
        ] = imem_patch_data[23:16];

        core.dp.instr_mem.meminst.memBlock3.mem[
            imem_patch_addr + 9'd3
        ] = imem_patch_data[31:24];
    end

    /*
     * Existing frozen observation protocol.
     */
    wire [8:0] probe_a_pc =
        core.dp.A.Curr_Pc;

    wire [31:0] probe_a_instr =
        core.dp.A.Curr_Instr;

    wire probe_stall =
        core.dp.Reg_Stall;

    wire probe_flush =
        core.dp.PcSel;

    wire [1:0] probe_fwd_a =
        core.dp.FAmuxSel;

    wire [1:0] probe_fwd_b =
        core.dp.FBmuxSel;

    wire [8:0] probe_b_pc =
        core.dp.B.Curr_Pc;

    wire [31:0] probe_b_instr =
        core.dp.B.Curr_Instr;

    wire [31:0] probe_c_instr =
        core.dp.C.Curr_Instr;

    wire [31:0] probe_d_instr =
        core.dp.D.Curr_Instr;

    wire [31:0] probe_x0 =
        core.dp.rf.register_file[0];

    wire probe_b_control_nonzero =
        core.dp.B.ALUSrc   |
        core.dp.B.MemtoReg |
        core.dp.B.RegWrite |
        core.dp.B.MemRead  |
        core.dp.B.MemWrite |
        (|core.dp.B.ALUOp) |
        core.dp.B.Branch   |
        core.dp.B.JalrSel  |
        (|core.dp.B.RWSel);

endmodule
