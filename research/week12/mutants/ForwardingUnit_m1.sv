`timescale 1ns / 1ps

/*
 * Week-12 M1-smoke mutant.
 *
 * Mutation:
 *   Disable the EX/MEM -> Forward_A path only.
 *
 * Preserved:
 *   - module name and interface;
 *   - MEM/WB -> Forward_A path;
 *   - complete Forward_B behavior;
 *   - x0 exclusion.
 *
 * This file is compiled only by the isolated Week-12 mutation build.
 * Canonical design/ForwardingUnit.sv must be excluded from that build.
 */

module ForwardingUnit
    (
     input logic [4:0] RS1,
     input logic [4:0] RS2,
     input logic [4:0] EX_MEM_rd,
     input logic [4:0] MEM_WB_rd,
     input logic EX_MEM_RegWrite,
     input logic MEM_WB_RegWrite,
     output logic [1:0] Forward_A,
     output logic [1:0] Forward_B
    );

    /*
     * M1 mutation:
     *
     * Canonical first branch intentionally removed:
     *
     *   EX_MEM_RegWrite
     *   && EX_MEM_rd != 0
     *   && EX_MEM_rd == RS1
     *       -> Forward_A = 2'b10
     *
     * A matching MEM/WB producer remains available.
     */
    assign Forward_A =
        ((MEM_WB_RegWrite)
         && (MEM_WB_rd != 0)
         && (MEM_WB_rd == RS1))
            ? 2'b01
            : 2'b00;

    /*
     * Forward_B is byte-for-byte semantically canonical.
     */
    assign Forward_B =
        ((EX_MEM_RegWrite)
         && (EX_MEM_rd != 0)
         && (EX_MEM_rd == RS2))
            ? 2'b10
            : ((MEM_WB_RegWrite)
               && (MEM_WB_rd != 0)
               && (MEM_WB_rd == RS2))
                ? 2'b01
                : 2'b00;

endmodule
