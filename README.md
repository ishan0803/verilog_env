---
title: EDA Hardware Optimization Environment
emoji: ⚡
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: true
---

# ⚡ EDA Hardware Optimization — OpenEnv Environment

> **Agentic RTL-to-GDSII Optimization via LLM-Driven EDA Workflows**

An OpenEnv-compliant POMDP environment where LLM agents optimize Verilog RTL designs for **Power, Performance, and Area (PPA)** while maintaining absolute functional correctness. Models the full semiconductor physical design pipeline using production EDA tools (Icarus Verilog, Yosys) inside a Dockerized, deterministic evaluation harness.

## Real-World Motivation

Modern semiconductor design requires architects to iteratively optimize RTL code through a complex pipeline: parsing → compilation → simulation → logic synthesis → timing analysis → physical design. This process is manually intensive, requiring deep domain expertise to navigate tradeoffs between area, power, and performance.

**This environment enables LLM agents to autonomously navigate this pipeline**, making design decisions that human engineers typically spend weeks on. The agent must:
- Understand Verilog RTL structure and identify optimization opportunities
- Invoke EDA tools strategically (compile, simulate, synthesize, time)
- Apply modifications that improve PPA without breaking functionality
- Handle hidden design constraints that are only revealed through tool feedback
- Recover from failed modifications using version rollback

This directly addresses the semiconductor industry's growing need for AI-assisted design automation, where the design space is too large for exhaustive search and requires the kind of reasoning that LLMs excel at.

## Environment Overview

### POMDP Formulation

| Component | Description |
|-----------|-------------|
| **State** | Full RTL ASTs, hidden constraints, intermediate netlists, git-tracked file history |
| **Observation** | Bounded tool outputs, requested PPA metrics, workspace diffs (partial view) |
| **Actions** | 8 tool interfaces (compile, simulate, synthesize, time, query, modify, constrain, rollback) |
| **Transitions** | EDA tool execution modifies workspace; caches invalidated on RTL changes |
| **Reward** | `R = F_correct × [α·δ_PPA + T_closure + I_progress] - P_invalid` |

The agent **never** sees: ground truth ASTs, hidden constraints, intermediate binary artifacts, or full system history. All information comes through bounded tool output text.

## Action Space

| Tool | Signature | Description |
|------|-----------|-------------|
| `compile_and_lint` | `(target_file: str)` | Syntax check via Icarus Verilog |
| `run_simulation` | `(testbench_file: str)` | Execute testbench, parse PASS/FAIL |
| `run_synthesis` | `(effort_level: str, flatten: bool)` | Yosys logic synthesis + area stats |
| `run_timing_analysis` | `(clock_period_ns: float)` | Analytical timing estimation |
| `query_metrics` | `(metric_type: str)` | PPA dashboard (area/power/timing/all) |
| `modify_rtl` | `(file_path: str, diff_patch: str)` | Apply code changes + cache invalidation |
| `adjust_constraints` | `(constraint_file: str, modifications: str)` | Modify SDC timing constraints |
| `rollback_version` | `(step_id: int)` | Git-backed workspace rollback |

## Observation Space

| Component | Content | Max Size |
|-----------|---------|----------|
| `action_success` | Boolean success/failure of last tool call | 1 bit |
| `exit_code` | System exit code | int |
| `tool_output` | Truncated EDA tool text output | 4000 chars |
| `metrics` | PPA values (only if `query_metrics` was called) | dict or null |
| `workspace_diff` | Files modified since last operation | list |
| `available_files` | Current workspace file listing | list |

## Reward Design

```
R_t = F_correct(t) × [α × δ_PPA(t) + T_closure(t) + I_progress(t)] - P_invalid(t)
```

| Component | Formula | Purpose |
|-----------|---------|---------|
| **F_correct** | Test pass rate [0.0, 1.0] | **Multiplicative gate** — prevents reward hacking by deleting logic |
| **δ_PPA** | `(baseline - current) / baseline` | Continuous PPA improvement signal |
| **T_closure** | +5.0 if WNS ≥ 0.0 | Sparse timing closure bonus |
| **I_progress** | +0.1 per fixed error, +0.05 per synthesis | Dense incremental progress |
| **P_invalid** | -0.5 new errors, -1.0 regression | Penalty for breaking working code |

**Key property**: `F_correct` as a multiplicative gate means an agent that achieves 50% area reduction by deleting all logic gets `0.0 × 50% = 0.0` reward. Functional correctness is non-negotiable.

## Task Suite

### Task 1: ALU Area Optimization (Easy)
- **Baseline**: 16-bit ALU with redundant adder/subtractor and duplicated comparators
- **Goal**: Minimize cell area via resource sharing
- **Constraint**: Combinational only (no timing)
- **Challenge**: Recognize mathematically equivalent operations

### Task 2: Pipeline Timing Closure (Medium)
- **Baseline**: 4-stage pipeline with timing-violating execute stage (long combinational chain)
- **Goal**: Achieve WNS ≥ 0.0 at 4ns clock (250 MHz)
- **Constraint**: Must maintain pipeline throughput
- **Challenge**: Insert pipeline registers to split critical path; balance area vs. timing

### Task 3: Memory Controller Power (Hard)
- **Baseline**: Memory controller with always-active counters and ungated read pipeline
- **Goal**: Reduce dynamic power via clock gating
- **Constraint**: 5ns clock + **hidden** max 3-cycle read latency
- **Challenge**: Clock gating without introducing sim-synth mismatch; hidden constraint discovery

## Grading

```
Score = 0.40 × functional_correctness
      + 0.30 × ppa_improvement
      + 0.20 × timing_closure
      + 0.10 × trajectory_stability
```

- **Functional correctness**: Hidden exhaustive test vectors (different from visible testbench)
- **PPA improvement**: Normalized vs. baseline (full score at 15% improvement)
- **Timing closure**: Binary — met or not at target frequency
- **Trajectory stability**: Penalizes compile-error loops and excessive rollbacks

All grading is **fully deterministic** — same RTL always produces the same score.

## Baseline Scores

| Task | Random Agent | Greedy Agent |
|------|-------------|--------------|
| Task 1 (ALU) | 0.20 | 0.55 |
| Task 2 (Pipeline) | 0.10 | 0.40 |
| Task 3 (Mem Ctrl) | 0.10 | 0.35 |

*Scores from running 100 episodes with random action selection and a heuristic greedy strategy.*

## Setup Instructions

### Docker (Recommended)

```bash
# Build the image (includes iverilog, yosys, git)
docker build -t eda-openenv .

# Run the server
docker run -p 8000:8000 eda-openenv

# Validate
openenv validate --url http://localhost:8000
```

### Local Development

```bash
# Install dependencies
uv sync

# Start the server (EDA tools not available locally — runs in limited mode)
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
```

### Running Inference

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export OPENAI_API_KEY="your-key"

python inference.py
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_BASE_URL` | Yes | `https://router.huggingface.co/v1` | LLM endpoint |
| `MODEL_NAME` | Yes | `Qwen/Qwen2.5-72B-Instruct` | Model ID |
| `OPENAI_API_KEY` | Yes | — | API key |
| `HF_TOKEN` | No | — | HuggingFace token |
| `IMAGE_NAME` | No | — | Docker image name |

## Architecture

```
verilog_env/
├── server/
│   ├── environment.py          # Core POMDP environment
│   ├── state_manager.py        # Git-backed episodic state
│   ├── reward.py               # 5-component reward function
│   ├── observation.py          # Partial observability enforcer
│   └── tool_wrappers/          # 7 EDA tool interfaces
├── tasks/                      # 3 tasks with Verilog + testbenches
├── graders/                    # Deterministic scoring
├── models.py                   # Pydantic Action/Observation
├── inference.py                # LLM agent driver
└── Dockerfile                  # Containerized EDA toolchain
```

## EDA Tools Used

| Tool | Version | Purpose |
|------|---------|---------|
| **Icarus Verilog** | 12+ | Compilation, lint, simulation |
| **Yosys** | 0.36+ | Logic synthesis, cell statistics |
| **Git** | 2.x | State versioning, rollback |
| **GNU patch** | 2.x | RTL modification |

All tools are installed inside the Docker container. No local installation required.
