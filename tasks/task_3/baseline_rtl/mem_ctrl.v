// =============================================================================
// Task 3: Memory Controller with Power Optimization Opportunity (Hard)
// =============================================================================
// Simple memory controller with read/write FSM interfacing an SRAM-like
// memory. No clock gating — all logic is always active.
//
// HIDDEN CONSTRAINT: Max read latency = 3 clock cycles.
// The agent must implement clock gating to reduce dynamic power WITHOUT
// violating the latency constraint.
// =============================================================================

module mem_ctrl (
    input  wire        clk,
    input  wire        rst_n,

    // Host interface
    input  wire        req_valid,
    input  wire        req_write,    // 1=write, 0=read
    input  wire [7:0]  req_addr,
    input  wire [31:0] req_wdata,
    output reg  [31:0] resp_rdata,
    output reg         resp_valid,
    output reg         resp_ready,   // Controller ready for new request

    // Status
    output reg  [3:0]  state_out,
    output reg         busy
);

    // FSM states
    localparam IDLE     = 4'd0;
    localparam READ_1   = 4'd1;
    localparam READ_2   = 4'd2;
    localparam READ_3   = 4'd3;
    localparam WRITE_1  = 4'd4;
    localparam WRITE_2  = 4'd5;
    localparam RESP     = 4'd6;
    localparam ERROR    = 4'd7;

    reg [3:0] state, next_state;

    // Internal SRAM (256 x 32-bit)
    reg [31:0] sram [0:255];

    // Request capture registers
    reg [7:0]  addr_reg;
    reg [31:0] wdata_reg;
    reg        write_reg;

    // Read data pipeline — deliberately not gated
    reg [31:0] read_data_pipe_1;
    reg [31:0] read_data_pipe_2;
    reg [31:0] read_data_pipe_3;

    // Power-wasteful: always-running counters (candidate for clock gating)
    reg [15:0] cycle_counter;
    reg [15:0] read_counter;
    reg [15:0] write_counter;
    reg [15:0] idle_counter;

    // Power-wasteful: always computing even when idle
    wire [31:0] addr_decode_full = {24'b0, addr_reg};
    wire [31:0] addr_plus_one   = addr_decode_full + 32'd1;
    wire [31:0] addr_plus_two   = addr_decode_full + 32'd2;
    wire [31:0] data_xor_check  = wdata_reg ^ 32'hDEADBEEF;
    wire [31:0] data_parity     = {31'b0, ^wdata_reg};

    // Power-wasteful: redundant read path (always active)
    wire [31:0] sram_read_0 = sram[addr_reg];
    wire [31:0] sram_read_1 = sram[addr_reg + 1];
    wire [31:0] sram_read_prefetch = sram[addr_reg + 2];

    integer i;

    // FSM next-state logic
    always @(*) begin
        next_state = state;
        case (state)
            IDLE: begin
                if (req_valid) begin
                    if (req_write)
                        next_state = WRITE_1;
                    else
                        next_state = READ_1;
                end
            end
            READ_1:  next_state = READ_2;
            READ_2:  next_state = RESP;
            WRITE_1: next_state = WRITE_2;
            WRITE_2: next_state = RESP;
            RESP:    next_state = IDLE;
            ERROR:   next_state = IDLE;
            default: next_state = IDLE;
        endcase
    end

    // FSM sequential logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= IDLE;
            addr_reg        <= 8'b0;
            wdata_reg       <= 32'b0;
            write_reg       <= 1'b0;
            resp_rdata      <= 32'b0;
            resp_valid      <= 1'b0;
            resp_ready      <= 1'b1;
            state_out       <= 4'b0;
            busy            <= 1'b0;
            read_data_pipe_1 <= 32'b0;
            read_data_pipe_2 <= 32'b0;
            read_data_pipe_3 <= 32'b0;
            cycle_counter   <= 16'b0;
            read_counter    <= 16'b0;
            write_counter   <= 16'b0;
            idle_counter    <= 16'b0;

            for (i = 0; i < 256; i = i + 1)
                sram[i] <= 32'b0;
        end else begin
            state     <= next_state;
            state_out <= next_state;

            // Always-running counters (power waste — should be gated)
            cycle_counter <= cycle_counter + 16'd1;

            // Default outputs
            resp_valid <= 1'b0;

            case (state)
                IDLE: begin
                    busy       <= 1'b0;
                    resp_ready <= 1'b1;
                    idle_counter <= idle_counter + 16'd1;

                    if (req_valid) begin
                        addr_reg  <= req_addr;
                        wdata_reg <= req_wdata;
                        write_reg <= req_write;
                        busy      <= 1'b1;
                        resp_ready <= 1'b0;
                    end

                    // Power waste: read pipeline always clocking
                    read_data_pipe_1 <= sram_read_0;
                    read_data_pipe_2 <= read_data_pipe_1;
                    read_data_pipe_3 <= read_data_pipe_2;
                end

                READ_1: begin
                    busy <= 1'b1;
                    resp_ready <= 1'b0;
                    read_data_pipe_1 <= sram[addr_reg];
                    read_counter <= read_counter + 16'd1;
                end

                READ_2: begin
                    read_data_pipe_2 <= read_data_pipe_1;
                    resp_rdata <= read_data_pipe_1;
                end

                WRITE_1: begin
                    busy <= 1'b1;
                    sram[addr_reg] <= wdata_reg;
                    write_counter <= write_counter + 16'd1;
                end

                WRITE_2: begin
                    // Write committed
                end

                RESP: begin
                    resp_valid <= 1'b1;
                    resp_ready <= 1'b0;
                end

                ERROR: begin
                    resp_valid <= 1'b0;
                    resp_ready <= 1'b1;
                    busy <= 1'b0;
                end
            endcase
        end
    end

endmodule
