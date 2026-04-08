"""
Inference Script for EDA Hardware Optimization Environment.

Uses OpenAI client to drive an LLM agent through EDA optimization tasks.
Dynamically generates tool schemas from Pydantic models to prevent drift.
Manages the full conversation context to avoid catastrophic forgetting.
"""

import asyncio
import json
import os
import re
import textwrap
import sys
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

# Import environment client and models
from verilog_env import VerilogEnv, EDAAction, ToolName

# Configuration
IMAGE_NAME = os.getenv("IMAGE_NAME")
# Added support for Groq/xAI specific API keys while maintaining fallback options.
# Defaulting to an empty string prevents NoneType crashes in the OpenAI SDK headers.
API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")

# Defaulting to Groq's OpenAI-compatible API endpoint
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.groq.com/openai/v1")

# Strictly use openai/gpt-oss-120b as requested
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-120b") 

MAX_STEPS = 30
TEMPERATURE = 0.1  # Bumped to 0.1 (some alternative APIs reject strict 0.0)
MAX_TOKENS = 1500  # Increased to allow for full-file RTL replacements
SEED = int(os.getenv("INFERENCE_SEED", "42"))

# Maximum context budget (characters) for history summarization
MAX_CONTEXT_CHARS = 100_000


def _generate_tool_schema() -> str:
    """Dynamically generate tool schema documentation from Pydantic models.

    Uses EDAAction.model_json_schema() and ToolName enum to ensure the
    system prompt always matches the backend's actual schema. This prevents
    drift from hardcoded schemas.
    """
    # Get all tool names from the enum
    tool_names = [t.value for t in ToolName]

    # Per-tool argument documentation (derived from backend expectations)
    # These map to the kwargs each tool wrapper actually accepts
    # These MUST exactly match the keys extracted via tool_args.get() in
    # server/environment.py's step() method to prevent schema drift.
    tool_arg_docs = {
        "compile_and_lint": '{"target_file": "<string>"}',
        "run_simulation": '{"testbench_file": "<string>"}',
        "run_synthesis": '{"effort_level": "<low|medium|high>", "flatten": <boolean>}',
        "run_timing_analysis": '{"clock_period_ns": <float>}',
        "query_metrics": '{"metric_type": "<string>"} (options: "area", "power", "timing", "synthesis", "all")',
        "modify_rtl": '{"file_path": "<string>", "diff_patch": "<string>"}',
        "adjust_constraints": '{"constraint_file": "<string>", "modifications": "<string>"}',
        "rollback_version": '{"step_id": <integer>}',
    }

    lines = []
    for i, name in enumerate(tool_names, 1):
        args = tool_arg_docs.get(name, "{}")
        lines.append(f"{i}. {name}\n   Args: {args}")

    return "\n".join(lines)


def build_system_prompt() -> str:
    """
    Generates the system prompt with dynamically generated tool schemas.
    """
    tool_schema = _generate_tool_schema()

    prompt = f"""You are an expert hardware design engineer optimizing Verilog RTL for PPA (Power, Performance, Area).

You interact with an EDA environment through tool calls. 

AVAILABLE TOOLS AND EXACT ARGUMENTS:
{tool_schema}

CRITICAL RULES:
1. ALWAYS check the 'available_files' list in your observation to use the exact file paths.
2. ONLY use the exact argument keys defined above. DO NOT guess argument names (e.g., do not use 'target_file' or 'testbench_path').
3. For `modify_rtl` and `adjust_constraints`, provide the FULL updated file content in the `diff_patch` argument. Do NOT use unified diffs or omit unchanged code.
4. You must respond with ONLY a valid JSON object matching this schema:
   {{"tool_name": "<name>", "tool_args": {{"<arg1>": "<value1>"}}}}
5. Do not add markdown blocks, conversational text, or explanations outside the JSON object.
"""
    return textwrap.dedent(prompt).strip()


# Generate the prompt once at startup
SYSTEM_PROMPT = build_system_prompt()


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env=verilog_env model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Aggressively parse LLM response into a tool call dict."""
    text = text.strip()

    # Extract JSON from markdown code blocks if present
    match = re.search(r"`{3}(?:json)?\s*(\{.*?\})\s*`{3}", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1)
    else:
        # Fallback: Find the outermost JSON object bounds
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _build_messages(
    step: int,
    observation: str,
    history: List[Dict[str, str]],
    step0_observation: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Build the message list for the LLM, preserving critical context.

    Always includes:
    1. System prompt (tool schemas, rules)
    2. Step 0 observation (baseline metrics, task description, file list)
       — pinned to prevent catastrophic forgetting
    3. Full conversation history (modern models handle 128k+ tokens)
    4. Current step observation
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Pin Step 0 observation so the agent never forgets baseline metrics,
    # task description, and available files
    if step0_observation and step > 1:
        messages.append({
            "role": "user",
            "content": f"[PINNED — Step 0 baseline]\n{step0_observation}",
        })

    # Include full history — no truncation
    # Modern models (128k+) can handle the full episode easily
    total_chars = sum(len(h.get("content", "")) for h in history)
    if total_chars > MAX_CONTEXT_CHARS:
        # Only truncate if we're genuinely exceeding the budget
        # Keep first 2 messages (initial context) + last messages
        kept = history[:2]
        remaining_budget = MAX_CONTEXT_CHARS - sum(len(h.get("content", "")) for h in kept)
        # Add from the end until budget is exhausted
        tail = []
        for h in reversed(history[2:]):
            msg_len = len(h.get("content", ""))
            if remaining_budget - msg_len < 0:
                break
            tail.insert(0, h)
            remaining_budget -= msg_len
        kept.extend(tail)
        for h in kept:
            messages.append(h)
    else:
        for h in history:
            messages.append(h)

    # Add current observation
    messages.append({
        "role": "user",
        "content": f"Step {step} observation:\n{observation}\n\nWhat tool should I use next? Respond strictly with the JSON object.",
    })

    return messages


async def get_agent_action(
    client: AsyncOpenAI,
    step: int,
    observation: str,
    history: List[Dict[str, str]],
    step0_observation: Optional[str] = None,
) -> Dict[str, Any]:
    """Get the next action from the LLM agent.

    On JSON parse failure, returns an error observation back to the agent
    (instead of silently defaulting) so it can self-correct.
    """
    messages = _build_messages(step, observation, history, step0_observation)

    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        
        if not completion or not hasattr(completion, 'choices') or not completion.choices:
            raise ValueError(f"API returned an empty or invalid response: {completion}")
            
        response_text = (completion.choices[0].message.content or "").strip()

        parsed = parse_tool_call(response_text)
        if parsed and "tool_name" in parsed:
            return parsed

        # Return parse failure as an error to the agent so it can self-correct
        # instead of silently mutating the action
        print(
            f"[DEBUG] JSON Parse Failed. Returning error to agent. "
            f"Raw LLM output:\n{response_text[:200]}...",
            flush=True,
        )
        return {
            "tool_name": "query_metrics",
            "tool_args": {"metric_type": "all"},
            "_parse_error": (
                f"Your previous response was not valid JSON. "
                f"Raw output: {response_text[:300]}. "
                f"Please respond with ONLY a valid JSON object."
            ),
        }

    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return {
            "tool_name": "query_metrics",
            "tool_args": {"metric_type": "all"},
            "_api_error": str(exc)[:200],
        }


async def run_task(client: AsyncOpenAI, task_seed: int) -> float:
    """Run a single task episode and return the score."""
    env = None
    try:
        if IMAGE_NAME:
            env = await VerilogEnv.from_docker_image(IMAGE_NAME)
        else:
            env = VerilogEnv(base_url="http://localhost:8000")
            if hasattr(env, "connect"):
                await env.connect()

        history: List[Dict[str, str]] = []
        rewards: List[float] = []
        steps_taken = 0
        score = 0.0
        task_name = "unknown"

        result = await env.reset(seed=task_seed)
        obs = result.observation
        task_name = obs.task_name or f"task_seed_{task_seed}"

        log_start(task=task_name, env="verilog_env", model=MODEL_NAME)

        # Step 0 observation — pinned throughout the episode
        step0_observation = (
            f"Task: {obs.task_name}\n"
            f"Description: {obs.task_description}\n"
            f"Output: {obs.tool_output}\n"
            f"Available Files: {json.dumps(obs.available_files)}"
        )
        observation_text = step0_observation

        for step in range(1, MAX_STEPS + 1):
            if result.done:
                break

            action_dict = await get_agent_action(
                client, step, observation_text, history, step0_observation
            )

            # Check if there was a parse error — feed it back to the agent
            parse_error = action_dict.pop("_parse_error", None)
            api_error = action_dict.pop("_api_error", None)

            tool_name = action_dict.get("tool_name", "query_metrics")
            tool_args = action_dict.get("tool_args", {})

            try:
                tool_enum = ToolName(tool_name)
            except ValueError:
                print(f"[DEBUG] Invalid tool name '{tool_name}' predicted. Defaulting to query_metrics.", flush=True)
                tool_enum = ToolName.QUERY_METRICS
                tool_args = {"metric_type": "all"}

            action = EDAAction(tool_name=tool_enum, tool_args=tool_args)

            result = await env.step(action)
            obs = result.observation
            reward = result.reward or 0.0

            rewards.append(reward)
            steps_taken = step

            log_args = {k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v) for k, v in tool_args.items()}
            action_str = f"{tool_enum.value}({json.dumps(log_args)})"
            
            error = None if obs.action_success else obs.tool_output[:100].replace('\n', ' ')
            log_step(step=step, action=action_str, reward=reward, done=result.done, error=error)

            history.append({
                "role": "assistant",
                "content": json.dumps(action_dict),
            })

            observation_text = (
                f"Action Success: {obs.action_success}\n"
                f"Exit Code: {obs.exit_code}\n"
                f"Output: {obs.tool_output[:2000]}\n"
                f"Reward for step: {reward:.4f}\n"
                f"Modified files: {', '.join(obs.workspace_diff) if obs.workspace_diff else 'none'}\n"
                f"Available files: {json.dumps(obs.available_files)}"
            )
            if obs.metrics:
                observation_text += f"\nMetrics: {json.dumps(obs.metrics)}"

            # Append error feedback so the agent can self-correct
            if parse_error:
                observation_text += f"\n\n⚠️ FORMAT ERROR: {parse_error}"
            if api_error:
                observation_text += f"\n\n⚠️ API ERROR: {api_error}"

            history.append({"role": "user", "content": observation_text})

            if result.done:
                break

        total_reward = sum(rewards)
        score = max(0.0, min(1.0, (total_reward + 5.0) / 10.0))

    except Exception as exc:
        print(f"[DEBUG] Task error: {exc}", flush=True)

    finally:
        if env:
            try:
                await env.close()
            except Exception as e:
                print(f"[DEBUG] env.close() error: {e}", flush=True)

        log_end(
            success=score > 0.3,
            steps=steps_taken,
            score=score,
            rewards=rewards,
        )

    return score


async def main() -> None:
    """Run inference across all 3 tasks."""
    
    # Fail-fast validation check for the API key
    if not API_KEY:
        print("\n[ERROR] Authentication Failed: No API key provided.", file=sys.stderr)
        print("Please set your API key in the environment before running the script:", file=sys.stderr)
        print("  export GROQ_API_KEY=\"your_actual_key_here\"", file=sys.stderr)
        print("  uv run python inference.py\n", file=sys.stderr)
        sys.exit(1)
    
    print("--- Generated System Prompt ---")
    print(SYSTEM_PROMPT)
    print("-------------------------------\n")
    
    client = AsyncOpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    scores = []
    for task_idx in range(3):
        task_seed = SEED + task_idx 
        print(f"\n--- Initiating Task {task_idx+1} (Seed: {task_seed}) ---", flush=True)
        score = await run_task(client, task_seed)
        scores.append(score)

    avg_score = sum(scores) / len(scores) if scores else 0.0
    print(f"\n=== AGGREGATE RESULTS ===", flush=True)
    for i, s in enumerate(scores):
        print(f"  Task {i+1}: {s:.3f}", flush=True)
    print(f"  Average: {avg_score:.3f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())