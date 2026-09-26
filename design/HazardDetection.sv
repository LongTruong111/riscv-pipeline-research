`timescale 1ns / 1ps

module HazardDetection
    (
     input logic [4:0] IF_ID_RS1,
     input logic [4:0] IF_ID_RS2,
     input logic [6:0] IF_ID_Opcode,
     input logic [4:0] ID_EX_rd,
     input logic ID_EX_MemRead,
     output logic stall
    );

    localparam logic [6:0] OP_R      = 7'b0110011;
    localparam logic [6:0] OP_LOAD   = 7'b0000011;
    localparam logic [6:0] OP_STORE  = 7'b0100011;
    localparam logic [6:0] OP_IMM    = 7'b0010011;
    localparam logic [6:0] OP_BRANCH = 7'b1100011;
    localparam logic [6:0] OP_JALR   = 7'b1100111;

    logic IF_ID_UsesRS1;
    logic IF_ID_UsesRS2;

    /*
     * Load-use hazard comparison must consider only architectural
     * source operands. Raw instruction fields are not always registers:
     *
     *   I-type [24:20] -> immediate payload, not rs2
     *   U/J-type fields -> immediate payload, not rs1/rs2
     */
    assign IF_ID_UsesRS1 =
        (IF_ID_Opcode == OP_R)      ||
        (IF_ID_Opcode == OP_LOAD)   ||
        (IF_ID_Opcode == OP_STORE)  ||
        (IF_ID_Opcode == OP_IMM)    ||
        (IF_ID_Opcode == OP_BRANCH) ||
        (IF_ID_Opcode == OP_JALR);

    assign IF_ID_UsesRS2 =
        (IF_ID_Opcode == OP_R)      ||
        (IF_ID_Opcode == OP_STORE)  ||
        (IF_ID_Opcode == OP_BRANCH);

    assign stall =
        ID_EX_MemRead
        &&
        (
            (
                IF_ID_UsesRS1
                && (ID_EX_rd == IF_ID_RS1)
            )
            ||
            (
                IF_ID_UsesRS2
                && (ID_EX_rd == IF_ID_RS2)
            )
        );

endmodule
