// =============================================================================
// Task 3: Memory Controller Hidden Exhaustive Tests (GRADER ONLY)
// =============================================================================
// Tests latency constraints, burst operations, and edge cases.
// HIDDEN CONSTRAINT: Read latency must be <= 3 clock cycles.
// =============================================================================

`timescale 1ns/1ps

module tb_mem_ctrl_exhaustive;
    reg         clk, rst_n;
    reg         req_valid, req_write;
    reg  [7:0]  req_addr;
    reg  [31:0] req_wdata;
    wire [31:0] resp_rdata;
    wire        resp_valid, resp_ready;
    wire [3:0]  state_out;
    wire        busy;

    mem_ctrl uut (
        .clk(clk), .rst_n(rst_n),
        .req_valid(req_valid), .req_write(req_write),
        .req_addr(req_addr), .req_wdata(req_wdata),
        .resp_rdata(resp_rdata), .resp_valid(resp_valid),
        .resp_ready(resp_ready),
        .state_out(state_out), .busy(busy)
    );

    initial clk = 0;
    always #2.5 clk = ~clk;

    integer pass_count = 0;
    integer fail_count = 0;
    integer total_tests = 0;

    task do_write(input [7:0] addr, input [31:0] data);
        begin
            @(posedge clk);
            req_valid = 1; req_write = 1;
            req_addr = addr; req_wdata = data;
            @(posedge clk);
            req_valid = 0; req_write = 0;
            while (!resp_valid) @(posedge clk);
            @(posedge clk);
        end
    endtask

    task do_read_latency(input [7:0] addr, output [31:0] data, output integer latency);
        begin
            latency = 0;
            @(posedge clk);
            req_valid = 1; req_write = 0;
            req_addr = addr; req_wdata = 32'b0;
            @(posedge clk);
            req_valid = 0;
            while (!resp_valid && latency < 20) begin
                @(posedge clk);
                latency = latency + 1;
            end
            data = resp_rdata;
            @(posedge clk);
        end
    endtask

    reg [31:0] read_data;
    integer latency;

    initial begin
        rst_n = 0;
        req_valid = 0; req_write = 0;
        req_addr = 0; req_wdata = 0;
        repeat(4) @(posedge clk);
        rst_n = 1;
        repeat(2) @(posedge clk);

        // === Test 1: Read latency constraint (HIDDEN: must be <= 3 cycles) ===
        do_write(8'h00, 32'hAAAA0000);
        do_read_latency(8'h00, read_data, latency);
        total_tests = total_tests + 1;
        if (latency <= 3 && read_data == 32'hAAAA0000) begin
            $display("TEST read_latency_constraint PASSED (latency=%0d)", latency);
            pass_count = pass_count + 1;
        end else begin
            $display("TEST read_latency_constraint FAILED: latency=%0d data=%h", latency, read_data);
            fail_count = fail_count + 1;
        end

        // === Test 2: All address boundary values ===
        do_write(8'h00, 32'h00000001);
        do_write(8'h7F, 32'h0000007F);
        do_write(8'h80, 32'h00000080);
        do_write(8'hFE, 32'h000000FE);
        do_write(8'hFF, 32'h000000FF);

        do_read_latency(8'h00, read_data, latency);
        total_tests = total_tests + 1;
        if (read_data == 32'h00000001) begin
            $display("TEST addr_00 PASSED"); pass_count = pass_count + 1;
        end else begin
            $display("TEST addr_00 FAILED: %h", read_data); fail_count = fail_count + 1;
        end

        do_read_latency(8'hFF, read_data, latency);
        total_tests = total_tests + 1;
        if (read_data == 32'h000000FF) begin
            $display("TEST addr_ff PASSED"); pass_count = pass_count + 1;
        end else begin
            $display("TEST addr_ff FAILED: %h", read_data); fail_count = fail_count + 1;
        end

        // === Test 3: Back-to-back read-write-read (data integrity) ===
        do_write(8'h50, 32'hFEEDFACE);
        do_read_latency(8'h50, read_data, latency);
        do_write(8'h50, 32'h99887766);
        do_read_latency(8'h50, read_data, latency);
        total_tests = total_tests + 1;
        if (read_data == 32'h99887766) begin
            $display("TEST back_to_back_rw PASSED"); pass_count = pass_count + 1;
        end else begin
            $display("TEST back_to_back_rw FAILED: %h", read_data); fail_count = fail_count + 1;
        end

        // === Test 4: Burst writes followed by burst reads ===
        begin : burst_test
            integer j;
            reg [31:0] expected;
            reg burst_pass;
            burst_pass = 1;
            for (j = 0; j < 16; j = j + 1) begin
                do_write(j[7:0], {16'hBEEF, j[15:0]});
            end
            for (j = 0; j < 16; j = j + 1) begin
                do_read_latency(j[7:0], read_data, latency);
                expected = {16'hBEEF, j[15:0]};
                if (read_data != expected) burst_pass = 0;
            end
            total_tests = total_tests + 1;
            if (burst_pass) begin
                $display("TEST burst_16 PASSED"); pass_count = pass_count + 1;
            end else begin
                $display("TEST burst_16 FAILED"); fail_count = fail_count + 1;
            end
        end

        // === Test 5: Reset during operation ===
        req_valid = 1; req_write = 0; req_addr = 8'h00;
        @(posedge clk);
        rst_n = 0;
        @(posedge clk);
        total_tests = total_tests + 1;
        if (!busy && resp_ready) begin
            $display("TEST reset_during_op PASSED"); pass_count = pass_count + 1;
        end else begin
            $display("TEST reset_during_op FAILED"); fail_count = fail_count + 1;
        end
        req_valid = 0;
        rst_n = 1;
        repeat(4) @(posedge clk);

        // === Test 6: Read after reset returns zero ===
        do_read_latency(8'h50, read_data, latency);
        total_tests = total_tests + 1;
        if (read_data == 32'h0) begin
            $display("TEST read_after_reset PASSED"); pass_count = pass_count + 1;
        end else begin
            $display("TEST read_after_reset FAILED: %h", read_data); fail_count = fail_count + 1;
        end

        // === Test 7: Write all-ones and all-zeros ===
        do_write(8'hA0, 32'hFFFFFFFF);
        do_read_latency(8'hA0, read_data, latency);
        total_tests = total_tests + 1;
        if (read_data == 32'hFFFFFFFF) begin
            $display("TEST all_ones PASSED"); pass_count = pass_count + 1;
        end else begin
            $display("TEST all_ones FAILED: %h", read_data); fail_count = fail_count + 1;
        end

        do_write(8'hA0, 32'h00000000);
        do_read_latency(8'hA0, read_data, latency);
        total_tests = total_tests + 1;
        if (read_data == 32'h00000000) begin
            $display("TEST all_zeros PASSED"); pass_count = pass_count + 1;
        end else begin
            $display("TEST all_zeros FAILED: %h", read_data); fail_count = fail_count + 1;
        end

        // === Test 8: Multiple reads same address (should be consistent) ===
        do_write(8'hB0, 32'h55AA55AA);
        do_read_latency(8'hB0, read_data, latency);
        total_tests = total_tests + 1;
        if (read_data == 32'h55AA55AA) begin
            do_read_latency(8'hB0, read_data, latency);
            if (read_data == 32'h55AA55AA) begin
                $display("TEST consistent_reads PASSED"); pass_count = pass_count + 1;
            end else begin
                $display("TEST consistent_reads FAILED on 2nd read: %h", read_data); fail_count = fail_count + 1;
            end
        end else begin
            $display("TEST consistent_reads FAILED: %h", read_data); fail_count = fail_count + 1;
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
