// =============================================================================
// Task 2: Pipeline Testbench — Visible Tests
// =============================================================================

`timescale 1ns/1ps

module tb_pipeline;
    reg         clk, rst_n;
    reg  [31:0] instruction;
    reg         valid_in;
    wire [31:0] result_out;
    wire        valid_out, stall;

    pipeline uut (
        .clk(clk), .rst_n(rst_n),
        .instruction(instruction), .valid_in(valid_in),
        .result_out(result_out), .valid_out(valid_out),
        .stall(stall)
    );

    // Clock: 4ns period (250 MHz target)
    initial clk = 0;
    always #2 clk = ~clk;

    integer pass_count = 0;
    integer fail_count = 0;

    task wait_valid;
        integer timeout;
        begin
            timeout = 0;
            while (!valid_out && timeout < 20) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
        end
    endtask

    initial begin
        rst_n = 0;
        instruction = 32'b0;
        valid_in = 0;
        repeat(4) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        // Test 1: ADDI x1, x0, 5  (opcode=0010011, funct3=000, rd=1, rs1=0, imm=5)
        instruction = {12'd5, 5'd0, 3'b000, 5'd1, 7'b0010011};
        valid_in = 1;
        @(posedge clk);
        valid_in = 0;
        instruction = 32'b0;

        // Wait for pipeline to produce result
        repeat(5) @(posedge clk);

        // Test 2: ADDI x2, x0, 10
        instruction = {12'd10, 5'd0, 3'b000, 5'd2, 7'b0010011};
        valid_in = 1;
        @(posedge clk);
        valid_in = 0;
        instruction = 32'b0;

        repeat(5) @(posedge clk);

        // Test 3: ADD x3, x1, x2 (opcode=0110011, funct3=000, funct7=0)
        instruction = {7'b0000000, 5'd2, 5'd1, 3'b000, 5'd3, 7'b0110011};
        valid_in = 1;
        @(posedge clk);
        valid_in = 0;
        instruction = 32'b0;

        repeat(5) @(posedge clk);

        // Test 4: Sequential pipeline throughput — feed multiple instructions
        instruction = {12'd1, 5'd0, 3'b000, 5'd4, 7'b0010011}; // x4 = 1
        valid_in = 1;
        @(posedge clk);
        instruction = {12'd2, 5'd0, 3'b000, 5'd5, 7'b0010011}; // x5 = 2
        @(posedge clk);
        instruction = {12'd3, 5'd0, 3'b000, 5'd6, 7'b0010011}; // x6 = 3
        @(posedge clk);
        valid_in = 0;
        instruction = 32'b0;

        repeat(8) @(posedge clk);

        // Check: pipeline should have processed all instructions without stalling
        if (!stall) begin
            $display("TEST pipeline_throughput PASSED");
            pass_count = pass_count + 1;
        end else begin
            $display("TEST pipeline_throughput FAILED: unexpected stall");
            fail_count = fail_count + 1;
        end

        // Verify reset behavior
        rst_n = 0;
        @(posedge clk);
        if (result_out == 32'b0 && valid_out == 0) begin
            $display("TEST reset_clears_output PASSED");
            pass_count = pass_count + 1;
        end else begin
            $display("TEST reset_clears_output FAILED");
            fail_count = fail_count + 1;
        end
        rst_n = 1;
        @(posedge clk);

        $display("");
        $display("=== VISIBLE TEST SUMMARY ===");
        $display("PASSED: %0d / %0d", pass_count, pass_count + fail_count);
        if (fail_count == 0)
            $display("ALL TESTS PASSED");
        $finish;
    end
endmodule
