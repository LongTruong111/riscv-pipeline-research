`timescale 1ns / 1ps
module ramOnChipData #(
    parameter ramSize = 65536,
    parameter ramWide = 8,
    parameter ramAddrWide = 16
) (
    input wire clk,
    input wire [ramWide-1:0] data,
    input wire [ramAddrWide-1:0] radd,
    input wire [ramAddrWide-1:0] wadd,
    input wire wren,
    output reg [ramWide-1:0] q
);
    reg [ramWide-1:0] mem [0:ramSize-1];
    integer i;

    initial begin
        for (i = 0; i < ramSize; i = i + 1)
            mem[i] = 0;
        $readmemh("data.hex", mem);
    end

    always @(posedge clk) begin
        if (wren) begin
            mem[wadd] <= data;
        end
        q <= mem[radd];
    end
endmodule
