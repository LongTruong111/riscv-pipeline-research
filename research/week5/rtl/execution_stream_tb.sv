`timescale 1ns / 1ps

module execution_stream_tb;

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
     * Frozen DUT.
     *
     * The wrapper does not modify DUT behavior. It only exposes verification
     * probes through hierarchical observation.
     */
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
     * Pre-edge IF/ID state.
     */
    wire [8:0]  probe_a_pc    = core.dp.A.Curr_Pc;
    wire [31:0] probe_a_instr = core.dp.A.Curr_Instr;

    /*
     * Pre-edge control qualification.
     */
    wire probe_stall = core.dp.Reg_Stall;
    wire probe_flush = core.dp.PcSel;

    /*
     * Settled EX forwarding selection.
     */
    wire [1:0] probe_fwd_a = core.dp.FAmuxSel;
    wire [1:0] probe_fwd_b = core.dp.FBmuxSel;

    /*
     * ID/EX state used to validate reconstruction after RisingEdge+ReadOnly.
     */
    wire [8:0]  probe_b_pc    = core.dp.B.Curr_Pc;
    wire [31:0] probe_b_instr = core.dp.B.Curr_Instr;

    /*
     * Pipeline identity probes for architectural commit tracing.
     *
     * Curr_Instr is used only as an identity cross-check when the
     * verification-side pipeline tag says the stage is functionally valid.
     * It is NOT treated as a valid bit.
     */
    wire [31:0] probe_c_instr = core.dp.C.Curr_Instr;
    wire [31:0] probe_d_instr = core.dp.D.Curr_Instr;

    /*
     * Architectural x0 observation.
     *
     * The frozen RegFile does not protect register zero, so this probe is
     * required to validate the architectural invariant x0 == 0 directly.
     */
    wire [31:0] probe_x0 = core.dp.rf.register_file[0];
    /*
     * Functional bubble indicator.
     *
     * B.Curr_Instr alone is not a valid-bit because the frozen RTL preserves
     * that debug field while injecting a stall/flush bubble.
     */
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
