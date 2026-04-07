// =============================================================================
// Task 1: 16-bit ALU with Redundant Logic (Easy)
// =============================================================================
// This ALU implements 8 operations but uses redundant hardware:
// - Separate adder and subtractor instead of shared adder with invert
// - Duplicated comparison logic
// - Unoptimized mux tree
//
// Agent goal: Minimize area by sharing resources while preserving
// functional correctness across all operations.
// =============================================================================

module alu (
    input  wire [15:0] a,
    input  wire [15:0] b,
    input  wire [3:0]  op,
    output reg  [15:0] result,
    output reg         carry_out,
    output reg         zero_flag,
    output reg         overflow_flag
);

    // Redundant: separate wires for add and subtract
    wire [16:0] add_result;
    wire [16:0] sub_result;

    // Redundant: two full adders instead of one with invert control
    assign add_result = {1'b0, a} + {1'b0, b};
    assign sub_result = {1'b0, a} - {1'b0, b};

    // Redundant: separate comparison circuits
    wire is_equal;
    wire is_less_than;
    wire is_greater_than;
    wire is_less_equal;
    wire is_greater_equal;

    assign is_equal        = (a == b);
    assign is_less_than    = ($signed(a) < $signed(b));
    assign is_greater_than = ($signed(a) > $signed(b));
    assign is_less_equal   = ($signed(a) <= $signed(b));
    assign is_greater_equal = ($signed(a) >= $signed(b));

    always @(*) begin
        carry_out     = 1'b0;
        zero_flag     = 1'b0;
        overflow_flag = 1'b0;
        result        = 16'h0000;

        case (op)
            4'b0000: begin // ADD
                result    = add_result[15:0];
                carry_out = add_result[16];
                overflow_flag = (a[15] == b[15]) && (result[15] != a[15]);
            end

            4'b0001: begin // SUB
                result    = sub_result[15:0];
                carry_out = sub_result[16];
                overflow_flag = (a[15] != b[15]) && (result[15] != a[15]);
            end

            4'b0010: begin // AND
                result = a & b;
            end

            4'b0011: begin // OR
                result = a | b;
            end

            4'b0100: begin // XOR
                result = a ^ b;
            end

            4'b0101: begin // SLL (Shift Left Logical)
                result = a << b[3:0];
            end

            4'b0110: begin // SRL (Shift Right Logical)
                result = a >> b[3:0];
            end

            4'b0111: begin // SRA (Shift Right Arithmetic)
                result = $signed(a) >>> b[3:0];
            end

            4'b1000: begin // Set Less Than (signed)
                result = {15'b0, is_less_than};
            end

            4'b1001: begin // Set Equal
                result = {15'b0, is_equal};
            end

            4'b1010: begin // Set Greater Than (signed)
                result = {15'b0, is_greater_than};
            end

            4'b1011: begin // NAND
                result = ~(a & b);
            end

            4'b1100: begin // NOR
                result = ~(a | b);
            end

            4'b1101: begin // XNOR
                result = ~(a ^ b);
            end

            4'b1110: begin // Pass A
                result = a;
            end

            4'b1111: begin // Pass B
                result = b;
            end
        endcase

        zero_flag = (result == 16'h0000);
    end

endmodule
