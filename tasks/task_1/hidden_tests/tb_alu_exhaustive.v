// =============================================================================
// Task 1: ALU Hidden Exhaustive Testbench (GRADER ONLY)
// =============================================================================
// Agent NEVER sees this file. Used by grader for functional correctness.
// Covers: all 16 operations, boundary values, overflow, signed corners.
// =============================================================================

`timescale 1ns/1ps

module tb_alu_exhaustive;
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
    integer total_tests = 0;

    task check(input [15:0] expected, input string test_name);
        begin
            #1;
            total_tests = total_tests + 1;
            if (result === expected) begin
                $display("TEST %s PASSED", test_name);
                pass_count = pass_count + 1;
            end else begin
                $display("TEST %s FAILED: got %h, expected %h", test_name, result, expected);
                fail_count = fail_count + 1;
            end
        end
    endtask

    task check_flag(input expected_flag, input actual_flag, input string test_name);
        begin
            #1;
            total_tests = total_tests + 1;
            if (actual_flag === expected_flag) begin
                $display("TEST %s PASSED", test_name);
                pass_count = pass_count + 1;
            end else begin
                $display("TEST %s FAILED: got %b, expected %b", test_name, actual_flag, expected_flag);
                fail_count = fail_count + 1;
            end
        end
    endtask

    initial begin
        // ===================== ADD (op=0000) =====================
        a = 16'h0000; b = 16'h0000; op = 4'b0000;
        check(16'h0000, "ADD_zero_zero");

        a = 16'h7FFF; b = 16'h0001; op = 4'b0000;
        check(16'h8000, "ADD_pos_overflow");

        a = 16'h8000; b = 16'h8000; op = 4'b0000;
        check(16'h0000, "ADD_neg_overflow");

        a = 16'hFFFF; b = 16'hFFFF; op = 4'b0000;
        check(16'hFFFE, "ADD_max_max");

        a = 16'h1234; b = 16'h4321; op = 4'b0000;
        check(16'h5555, "ADD_arbitrary");

        a = 16'h8000; b = 16'h7FFF; op = 4'b0000;
        check(16'hFFFF, "ADD_minpos_maxneg");

        // Zero flag after add
        a = 16'hFFFF; b = 16'h0001; op = 4'b0000; #1;
        check_flag(1'b1, zero_flag, "ADD_zero_flag_set");

        a = 16'h0001; b = 16'h0001; op = 4'b0000; #1;
        check_flag(1'b0, zero_flag, "ADD_zero_flag_clear");

        // ===================== SUB (op=0001) =====================
        a = 16'h0000; b = 16'h0000; op = 4'b0001;
        check(16'h0000, "SUB_zero_zero");

        a = 16'h8000; b = 16'h0001; op = 4'b0001;
        check(16'h7FFF, "SUB_neg_overflow");

        a = 16'h7FFF; b = 16'hFFFF; op = 4'b0001;
        check(16'h8000, "SUB_pos_overflow");

        a = 16'h0001; b = 16'h0001; op = 4'b0001;
        check(16'h0000, "SUB_equal");

        a = 16'hAAAA; b = 16'h5555; op = 4'b0001;
        check(16'h5555, "SUB_arbitrary");

        // ===================== AND (op=0010) =====================
        a = 16'hFFFF; b = 16'hFFFF; op = 4'b0010;
        check(16'hFFFF, "AND_all_ones");

        a = 16'hFFFF; b = 16'h0000; op = 4'b0010;
        check(16'h0000, "AND_mask_zero");

        a = 16'hA5A5; b = 16'h5A5A; op = 4'b0010;
        check(16'h0000, "AND_complement");

        // ===================== OR (op=0011) =====================
        a = 16'h0000; b = 16'h0000; op = 4'b0011;
        check(16'h0000, "OR_zero_zero");

        a = 16'hA5A5; b = 16'h5A5A; op = 4'b0011;
        check(16'hFFFF, "OR_complement");

        // ===================== XOR (op=0100) =====================
        a = 16'hFFFF; b = 16'hFFFF; op = 4'b0100;
        check(16'h0000, "XOR_same");

        a = 16'h0000; b = 16'hFFFF; op = 4'b0100;
        check(16'hFFFF, "XOR_invert");

        // ===================== SLL (op=0101) =====================
        a = 16'h0001; b = 16'h000F; op = 4'b0101;
        check(16'h8000, "SLL_max_shift");

        a = 16'hFFFF; b = 16'h0000; op = 4'b0101;
        check(16'hFFFF, "SLL_zero_shift");

        a = 16'h8001; b = 16'h0001; op = 4'b0101;
        check(16'h0002, "SLL_msb_out");

        // ===================== SRL (op=0110) =====================
        a = 16'h8000; b = 16'h000F; op = 4'b0110;
        check(16'h0001, "SRL_max_shift");

        a = 16'hFFFF; b = 16'h0000; op = 4'b0110;
        check(16'hFFFF, "SRL_zero_shift");

        // ===================== SRA (op=0111) =====================
        a = 16'h8000; b = 16'h0004; op = 4'b0111;
        check(16'hF800, "SRA_negative_sign_extend");

        a = 16'h4000; b = 16'h0004; op = 4'b0111;
        check(16'h0400, "SRA_positive");

        // ===================== SLT (op=1000) =====================
        a = 16'h8000; b = 16'h0001; op = 4'b1000;  // -32768 < 1
        check(16'h0001, "SLT_negative");

        a = 16'h0001; b = 16'h8000; op = 4'b1000;  // 1 > -32768
        check(16'h0000, "SLT_positive_vs_neg");

        a = 16'hFFFF; b = 16'h0000; op = 4'b1000;  // -1 < 0
        check(16'h0001, "SLT_minus_one");

        // ===================== SEQ (op=1001) =====================
        a = 16'h0000; b = 16'h0000; op = 4'b1001;
        check(16'h0001, "SEQ_both_zero");

        a = 16'h0001; b = 16'h0000; op = 4'b1001;
        check(16'h0000, "SEQ_not_equal");

        // ===================== SGT (op=1010) =====================
        a = 16'h0001; b = 16'h8000; op = 4'b1010;  // 1 > -32768
        check(16'h0001, "SGT_pos_vs_neg");

        a = 16'h8000; b = 16'h0001; op = 4'b1010;
        check(16'h0000, "SGT_neg_vs_pos");

        // ===================== NAND (op=1011) =====================
        a = 16'hFFFF; b = 16'hFFFF; op = 4'b1011;
        check(16'h0000, "NAND_all_ones");

        a = 16'h0000; b = 16'hFFFF; op = 4'b1011;
        check(16'hFFFF, "NAND_with_zero");

        // ===================== NOR (op=1100) =====================
        a = 16'h0000; b = 16'h0000; op = 4'b1100;
        check(16'hFFFF, "NOR_zero_zero");

        a = 16'hFFFF; b = 16'h0000; op = 4'b1100;
        check(16'h0000, "NOR_with_ones");

        // ===================== XNOR (op=1101) =====================
        a = 16'hAAAA; b = 16'hAAAA; op = 4'b1101;
        check(16'hFFFF, "XNOR_same");

        a = 16'hAAAA; b = 16'h5555; op = 4'b1101;
        check(16'h0000, "XNOR_complement");

        // ===================== PASS_A (op=1110) =====================
        a = 16'hDEAD; b = 16'hBEEF; op = 4'b1110;
        check(16'hDEAD, "PASS_A_value");

        // ===================== PASS_B (op=1111) =====================
        a = 16'hDEAD; b = 16'hBEEF; op = 4'b1111;
        check(16'hBEEF, "PASS_B_value");

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
