// =============================================================================
// Task 1: ALU Testbench — Visible Tests
// =============================================================================
// Tests basic ALU operations. The agent can see these test vectors.
// Hidden exhaustive tests cover edge cases (overflow, zero, max values).
// =============================================================================

`timescale 1ns/1ps

module tb_alu;
    reg  [15:0] a, b;
    reg  [3:0]  op;
    wire [15:0] result;
    wire        carry_out, zero_flag, overflow_flag;

    alu uut (
        .a(a), .b(b), .op(op),
        .result(result), .carry_out(carry_out),
        .zero_flag(zero_flag), .overflow_flag(overflow_flag)
    );

    integer pass_count = 0;
    integer fail_count = 0;

    task check(input [15:0] expected, input string test_name);
        begin
            #1;
            if (result === expected) begin
                $display("TEST %s PASSED", test_name);
                pass_count = pass_count + 1;
            end else begin
                $display("TEST %s FAILED: got %h, expected %h", test_name, result, expected);
                fail_count = fail_count + 1;
            end
        end
    endtask

    initial begin
        // ADD tests
        a = 16'h0005; b = 16'h0003; op = 4'b0000;
        check(16'h0008, "ADD_basic");

        a = 16'h0000; b = 16'h0000; op = 4'b0000;
        check(16'h0000, "ADD_zero");

        a = 16'hFFFF; b = 16'h0001; op = 4'b0000;
        check(16'h0000, "ADD_overflow");

        // SUB tests
        a = 16'h000A; b = 16'h0003; op = 4'b0001;
        check(16'h0007, "SUB_basic");

        a = 16'h0000; b = 16'h0001; op = 4'b0001;
        check(16'hFFFF, "SUB_underflow");

        // AND test
        a = 16'hFF00; b = 16'h0F0F; op = 4'b0010;
        check(16'h0F00, "AND_basic");

        // OR test
        a = 16'hFF00; b = 16'h00FF; op = 4'b0011;
        check(16'hFFFF, "OR_basic");

        // XOR test
        a = 16'hAAAA; b = 16'h5555; op = 4'b0100;
        check(16'hFFFF, "XOR_basic");

        // SLL test
        a = 16'h0001; b = 16'h0004; op = 4'b0101;
        check(16'h0010, "SLL_basic");

        // SRL test
        a = 16'h0080; b = 16'h0004; op = 4'b0110;
        check(16'h0008, "SRL_basic");

        // SLT test
        a = 16'h0001; b = 16'h0002; op = 4'b1000;
        check(16'h0001, "SLT_true");

        a = 16'h0005; b = 16'h0002; op = 4'b1000;
        check(16'h0000, "SLT_false");

        // SEQ test
        a = 16'hABCD; b = 16'hABCD; op = 4'b1001;
        check(16'h0001, "SEQ_true");

        // Pass A
        a = 16'h1234; b = 16'h5678; op = 4'b1110;
        check(16'h1234, "PASS_A");

        // Pass B
        a = 16'h1234; b = 16'h5678; op = 4'b1111;
        check(16'h5678, "PASS_B");

        $display("");
        $display("=== VISIBLE TEST SUMMARY ===");
        $display("PASSED: %0d / %0d", pass_count, pass_count + fail_count);
        if (fail_count == 0)
            $display("ALL TESTS PASSED");
        else
            $display("SOME TESTS FAILED");
        $finish;
    end
endmodule
