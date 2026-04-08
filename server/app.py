"""
FastAPI application for the EDA Hardware Optimization Environment.

Adds Gradio Playground UI on top of OpenEnv environment.
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:
    raise ImportError(
        "openenv is required. Install with: uv sync"
    ) from e

try:
    from ..models import EDAAction, EDAObservation
    from .environment import VerilogEnvironment
except (ImportError, ModuleNotFoundError):
    from models import EDAAction, EDAObservation
    from server.environment import VerilogEnvironment

import gradio as gr
import json

# Create the FastAPI backend
app = create_app(
    VerilogEnvironment,
    EDAAction,
    EDAObservation,
    env_name="verilog_env",
    max_concurrent_envs=1,
)

# Create environment instance
env = VerilogEnvironment()


# -----------------------------
# Gradio Functions
# -----------------------------

def reset_env():
    state = env.reset()
    return json.dumps(state, indent=2)


def step_env(message):
    action = EDAAction(message=message)
    obs = env.step(action)
    return json.dumps(obs, indent=2)


def get_state():
    state = env.get_state()
    return json.dumps(state, indent=2)


# -----------------------------
# Gradio UI
# -----------------------------

with gr.Blocks(title="OpenEnv Verilog Playground") as demo:
    gr.Markdown("# OpenEnv Agentic Environment: verilog_env")

    with gr.Row():
        message = gr.Textbox(
            label="Message",
            placeholder="Enter message..."
        )

    with gr.Row():
        step_btn = gr.Button("Step")
        reset_btn = gr.Button("Reset")
        state_btn = gr.Button("Get State")

    output = gr.Code(label="Raw JSON response")

    step_btn.click(step_env, inputs=message, outputs=output)
    reset_btn.click(reset_env, outputs=output)
    state_btn.click(get_state, outputs=output)


# Mount Gradio into FastAPI
app = gr.mount_gradio_app(app, demo, path="/")


def main(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()