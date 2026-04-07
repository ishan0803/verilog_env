// =============================================================================
// Task 3: Memory Controller Testbench — Visible Tests
// =============================================================================

`timescale 1ns/1ps

module tb_mem_ctrl;
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
    always #2.5 clk = ~clk; // 5ns clock (200 MHz)

    integer pass_count = 0;
    integer fail_count = 0;

    task do_write(input [7:0] addr, input [31:0] data);
        begin
            @(posedge clk);
            req_valid = 1; req_write = 1;
            req_addr = addr; req_wdata = data;
            @(posedge clk);
            req_valid = 0; req_write = 0;
            // Wait for response
            while (!resp_valid) @(posedge clk);
            @(posedge clk);
        end
    endtask

    task do_read(input [7:0] addr, output [31:0] data);
        begin
            @(posedge clk);
            req_valid = 1; req_write = 0;
            req_addr = addr; req_wdata = 32'b0;
            @(posedge clk);
            req_valid = 0;
            while (!resp_valid) @(posedge clk);
            data = resp_rdata;
            @(posedge clk);
        end
    endtask

    reg [31:0] read_data;

    initial begin
        rst_n = 0;
        req_valid = 0; req_write = 0;
        req_addr = 0; req_wdata = 0;
        repeat(4) @(posedge clk);
        rst_n = 1;
        repeat(2) @(posedge clk);

        // Test 1: Basic write then read
        do_write(8'h00, 32'hDEADBEEF);
        do_read(8'h00, read_data);
        if (read_data == 32'hDEADBEEF) begin
            $display("TEST write_read_basic PASSED");
            pass_count = pass_count + 1;
        end else begin
            $display("TEST write_read_basic FAILED: got %h", read_data);
            fail_count = fail_count + 1;
        end

        // Test 2: Write to different address
        do_write(8'hFF, 32'hCAFEBABE);
        do_read(8'hFF, read_data);
        if (read_data == 32'hCAFEBABE) begin
            $display("TEST write_read_addr_ff PASSED");
            pass_count = pass_count + 1;
        end else begin
            $display("TEST write_read_addr_ff FAILED: got %h", read_data);
            fail_count = fail_count + 1;
        end

        // Test 3: Overwrite
        do_write(8'h00, 32'h12345678);
        do_read(8'h00, read_data);
        if (read_data == 32'h12345678) begin
            $display("TEST overwrite PASSED");
            pass_count = pass_count + 1;
        end else begin
            $display("TEST overwrite FAILED: got %h", read_data);
            fail_count = fail_count + 1;
        end

        // Test 4: Multiple sequential writes
        do_write(8'h10, 32'h11111111);
        do_write(8'h11, 32'h22222222);
        do_write(8'h12, 32'h33333333);
        do_read(8'h10, read_data);
        if (read_data == 32'h11111111) begin
            $display("TEST sequential_writes PASSED");
            pass_count = pass_count + 1;
        end else begin
            $display("TEST sequential_writes FAILED: got %h", read_data);
            fail_count = fail_count + 1;
        end

        // Test 5: Ready signal
        if (resp_ready) begin
            $display("TEST ready_after_ops PASSED");
            pass_count = pass_count + 1;
        end else begin
            $display("TEST ready_after_ops FAILED");
            fail_count = fail_count + 1;
        end

        $display("");
        $display("=== VISIBLE TEST SUMMARY ===");
        $display("PASSED: %0d / %0d", pass_count, pass_count + fail_count);
        if (fail_count == 0)
            $display("ALL TESTS PASSED");
        $finish;
    end
endmodule
