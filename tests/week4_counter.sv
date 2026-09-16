`timescale 1ns/1ps

module week4_counter (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       en,
    output logic [7:0] count
);

    always_ff @(posedge clk) begin
        if (!rst_n)
            count <= 8'd0;
        else if (en)
            count <= count + 8'd1;
    end

    initial begin
        $dumpfile("waveforms/week4_race.vcd");
        $dumpvars(0, week4_counter);
    end

endmodule
