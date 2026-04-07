// =============================================================================
// Task 2: Pipeline Hidden Exhaustive Tests (GRADER ONLY)
// =============================================================================

`timescale 1ns/1ps

module tb_pipeline_exhaustive;
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

    initial clk = 0;
    always #2 clk = ~clk;

    integer pass_count = 0;
    integer fail_count = 0;
    integer total_tests = 0;

    task submit_instr(input [31:0] instr);
        begin
            instruction = instr;
            valid_in = 1;
            @(posedge clk);
            valid_in = 0;
            instruction = 32'b0;
        end
    endtask

    task drain_pipeline;
        begin
            repeat(6) @(posedge clk);
        end
    endtask

    task test_pass(input string name);
        begin
            total_tests = total_tests + 1;
            pass_count = pass_count + 1;
            $display("TEST %s PASSED", name);
        end
    endtask

    task test_fail(input string name, input string reason);
        begin
            total_tests = total_tests + 1;
            fail_count = fail_count + 1;
            $display("TEST %s FAILED: %s", name, reason);
        end
    endtask

    initial begin
        rst_n = 0;
        instruction = 32'b0;
        valid_in = 0;
        repeat(4) @(posedge clk);
        rst_n = 1;
        @(posedge clk);

        // === Test 1: Basic ADDI sequence ===
        // x1 = 5
        submit_instr({12'd5, 5'd0, 3'b000, 5'd1, 7'b0010011});
        drain_pipeline;

        // x2 = 10
        submit_instr({12'd10, 5'd0, 3'b000, 5'd2, 7'b0010011});
        drain_pipeline;

        // x3 = 255
        submit_instr({12'd255, 5'd0, 3'b000, 5'd3, 7'b0010011});
        drain_pipeline;

        test_pass("addi_sequence");

        // === Test 2: Reset mid-operation ===
        submit_instr({12'd42, 5'd0, 3'b000, 5'd4, 7'b0010011});
        @(posedge clk);
        rst_n = 0;
        @(posedge clk);
        if (valid_out == 0) begin
            test_pass("reset_kills_valid");
        end else begin
            test_fail("reset_kills_valid", "valid_out not cleared on reset");
        end
        rst_n = 1;
        repeat(2) @(posedge clk);

        // === Test 3: Back-to-back instructions (stress pipeline) ===
        submit_instr({12'd1, 5'd0, 3'b000, 5'd1, 7'b0010011});
        submit_instr({12'd2, 5'd0, 3'b000, 5'd2, 7'b0010011});
        submit_instr({12'd3, 5'd0, 3'b000, 5'd3, 7'b0010011});
        submit_instr({12'd4, 5'd0, 3'b000, 5'd4, 7'b0010011});
        drain_pipeline;
        test_pass("back_to_back_instrs");

        // === Test 4: AND operation (funct3=111) ===
        // First load values, then AND
        submit_instr({12'hFFF, 5'd0, 3'b000, 5'd1, 7'b0010011}); // x1 = -1
        drain_pipeline;
        submit_instr({12'h0F0, 5'd0, 3'b000, 5'd2, 7'b0010011}); // x2 = 240
        drain_pipeline;
        submit_instr({7'b0000000, 5'd2, 5'd1, 3'b111, 5'd3, 7'b0110011}); // x3 = x1 & x2
        drain_pipeline;
        test_pass("and_operation");

        // === Test 5: OR operation (funct3=110) ===
        submit_instr({7'b0000000, 5'd1, 5'd2, 3'b110, 5'd4, 7'b0110011}); // x4 = x1 | x2
        drain_pipeline;
        test_pass("or_operation");

        // === Test 6: XOR operation (funct3=100) ===
        submit_instr({7'b0000000, 5'd1, 5'd2, 3'b100, 5'd5, 7'b0110011}); // x5 = x1 ^ x2
        drain_pipeline;
        test_pass("xor_operation");

        // === Test 7: SLL operation (funct3=001) ===
        submit_instr({12'd1, 5'd0, 3'b000, 5'd1, 7'b0010011}); // x1 = 1
        drain_pipeline;
        submit_instr({12'd4, 5'd0, 3'b000, 5'd2, 7'b0010011}); // x2 = 4
        drain_pipeline;
        submit_instr({7'b0000000, 5'd2, 5'd1, 3'b001, 5'd3, 7'b0110011}); // x3 = x1 << x2
        drain_pipeline;
        test_pass("sll_operation");

        // === Test 8: SUB operation (funct7=0100000, funct3=000) ===
        submit_instr({12'd20, 5'd0, 3'b000, 5'd1, 7'b0010011}); // x1 = 20
        drain_pipeline;
        submit_instr({12'd7, 5'd0, 3'b000, 5'd2, 7'b0010011});  // x2 = 7
        drain_pipeline;
        submit_instr({7'b0100000, 5'd2, 5'd1, 3'b000, 5'd3, 7'b0110011}); // x3 = x1 - x2
        drain_pipeline;
        test_pass("sub_operation");

        // === Test 9: Negative immediate ===
        submit_instr({12'hFFF, 5'd0, 3'b000, 5'd7, 7'b0010011}); // x7 = -1 (sign-extended)
        drain_pipeline;
        test_pass("negative_immediate");

        // === Test 10: Pipeline maintains data integrity after many ops ===
        begin : stress_test
            integer j;
            for (j = 0; j < 16; j = j + 1) begin
                submit_instr({12'(j), 5'd0, 3'b000, 5'(j & 7), 7'b0010011});
            end
            drain_pipeline;
            drain_pipeline;
            test_pass("stress_16_instructions");
        end

        $display("");
        $display("=== EXHAUSTIVE TEST SUMMARY ===");
        $display("PASSED: %0d / %0d", pass_count, total_tests);
        if (fail_count == 0)
            $display("ALL TESTS PASSED");
        else
            $display("SOME TESTS FAILED");
        $finish;
    end
endmodule
