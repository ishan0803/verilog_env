// =============================================================================
// Task 2: Simple RISC-V-style Pipeline Stage (Medium)
// =============================================================================
// A 4-stage pipeline (IF/ID/EX/WB) with a timing-violating critical path
// in the execute stage. The combinational logic between EX register input
// and output is too long — needs pipeline register insertion (retiming).
//
// Agent goal: Achieve timing closure (WNS >= 0) at 4ns clock by
// inserting pipeline registers to split the long combinational path.
// =============================================================================

module pipeline (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] instruction,
    input  wire        valid_in,
    output reg  [31:0] result_out,
    output reg         valid_out,
    output reg         stall
);

    // Pipeline registers
    reg [31:0] if_id_instr;
    reg        if_id_valid;

    reg [31:0] id_ex_op_a;
    reg [31:0] id_ex_op_b;
    reg [3:0]  id_ex_alu_op;
    reg        id_ex_valid;

    reg [31:0] ex_wb_result;
    reg        ex_wb_valid;

    // Decode fields
    wire [6:0]  opcode   = if_id_instr[6:0];
    wire [4:0]  rd       = if_id_instr[11:7];
    wire [2:0]  funct3   = if_id_instr[14:12];
    wire [4:0]  rs1      = if_id_instr[19:15];
    wire [4:0]  rs2      = if_id_instr[24:20];
    wire [6:0]  funct7   = if_id_instr[31:25];
    wire [11:0] imm_i    = if_id_instr[31:20];

    // Simple register file (8 registers for demo)
    reg [31:0] regfile [0:7];
    integer i;

    // =========================================================================
    // DELIBERATELY LONG COMBINATIONAL CHAIN IN EXECUTE STAGE
    // This is the critical path that violates 4ns timing.
    // The agent should split this with pipeline registers.
    // =========================================================================
    wire [31:0] alu_a = id_ex_op_a;
    wire [31:0] alu_b = id_ex_op_b;

    // Stage 1: Basic ALU
    wire [31:0] add_result = alu_a + alu_b;
    wire [31:0] sub_result = alu_a - alu_b;
    wire [31:0] and_result = alu_a & alu_b;
    wire [31:0] or_result  = alu_a | alu_b;
    wire [31:0] xor_result = alu_a ^ alu_b;

    // Stage 2: Multiply (expensive — adds to critical path)
    wire [63:0] mul_full = alu_a * alu_b;
    wire [31:0] mul_result = mul_full[31:0];

    // Stage 3: Shift operations chained after multiply mux
    wire [31:0] sll_result = alu_a << alu_b[4:0];
    wire [31:0] srl_result = alu_a >> alu_b[4:0];
    wire [31:0] sra_result = $signed(alu_a) >>> alu_b[4:0];

    // Stage 4: Complex comparison (chained after arithmetic)
    wire signed [31:0] signed_a = $signed(alu_a);
    wire signed [31:0] signed_b = $signed(alu_b);
    wire [31:0] slt_result = {31'b0, signed_a < signed_b};
    wire [31:0] sltu_result = {31'b0, alu_a < alu_b};

    // Stage 5: Post-processing — additional logic depth
    wire [31:0] post_add = add_result + mul_result;
    wire [31:0] post_xor = post_add ^ sll_result;
    wire [31:0] final_blend = (post_xor & or_result) | (~post_xor & and_result);

    // Giant mux selecting final ALU result (adds more delay)
    reg [31:0] alu_result;
    always @(*) begin
        case (id_ex_alu_op)
            4'b0000: alu_result = add_result;
            4'b0001: alu_result = sub_result;
            4'b0010: alu_result = and_result;
            4'b0011: alu_result = or_result;
            4'b0100: alu_result = xor_result;
            4'b0101: alu_result = sll_result;
            4'b0110: alu_result = srl_result;
            4'b0111: alu_result = sra_result;
            4'b1000: alu_result = mul_result;
            4'b1001: alu_result = slt_result;
            4'b1010: alu_result = sltu_result;
            4'b1011: alu_result = final_blend;
            default: alu_result = 32'b0;
        endcase
    end

    // Pipeline stages (sequential)
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            if_id_instr  <= 32'b0;
            if_id_valid  <= 1'b0;
            id_ex_op_a   <= 32'b0;
            id_ex_op_b   <= 32'b0;
            id_ex_alu_op <= 4'b0;
            id_ex_valid  <= 1'b0;
            ex_wb_result <= 32'b0;
            ex_wb_valid  <= 1'b0;
            result_out   <= 32'b0;
            valid_out    <= 1'b0;
            stall        <= 1'b0;
            for (i = 0; i < 8; i = i + 1)
                regfile[i] <= 32'b0;
        end else begin
            stall <= 1'b0;

            // IF -> ID
            if_id_instr <= instruction;
            if_id_valid <= valid_in;

            // ID -> EX (decode and register read)
            id_ex_op_a   <= regfile[rs1[2:0]];
            id_ex_op_b   <= (opcode == 7'b0010011) ?
                            {{20{imm_i[11]}}, imm_i} : regfile[rs2[2:0]];
            id_ex_alu_op <= {funct7[5], funct3};
            id_ex_valid  <= if_id_valid;

            // EX -> WB (the long combinational path feeds here)
            ex_wb_result <= alu_result;
            ex_wb_valid  <= id_ex_valid;

            // WB: write back to register file
            if (ex_wb_valid && rd != 5'b0) begin
                regfile[rd[2:0]] <= ex_wb_result;
            end
            result_out <= ex_wb_result;
            valid_out  <= ex_wb_valid;
        end
    end

endmodule
