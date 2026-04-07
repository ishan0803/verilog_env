#!/usr/bin/env bash
#
# pre_validation_script.sh — EDA OpenEnv Submission Validator
#
# Validates: HF Space, Docker build, openenv validate, task checks,
# grader determinism, and resource usage.
#

set -uo pipefail

DOCKER_BUILD_TIMEOUT=600
if [ -t 1 ]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BOLD='\033[1m'
  NC='\033[0m'
else
  RED='' GREEN='' YELLOW='' BOLD='' NC=''
fi

run_with_timeout() {
  local secs="$1"; shift
  if command -v timeout &>/dev/null; then
    timeout "$secs" "$@"
  elif command -v gtimeout &>/dev/null; then
    gtimeout "$secs" "$@"
  else
    "$@" &
    local pid=$!
    ( sleep "$secs" && kill "$pid" 2>/dev/null ) &
    local watcher=$!
    wait "$pid" 2>/dev/null
    local rc=$?
    kill "$watcher" 2>/dev/null
    wait "$watcher" 2>/dev/null
    return $rc
  fi
}

CLEANUP_FILES=()
cleanup() { rm -f "${CLEANUP_FILES[@]+"${CLEANUP_FILES[@]}"}"; }
trap cleanup EXIT

PING_URL="${1:-}"
REPO_DIR="${2:-.}"

if [ -z "$PING_URL" ]; then
  printf "Usage: %s <ping_url> [repo_dir]\n" "$0"
  printf "\n"
  printf "  ping_url   Your HuggingFace Space URL (e.g. https://your-space.hf.space)\n"
  printf "  repo_dir   Path to your repo (default: current directory)\n"
  exit 1
fi

if ! REPO_DIR="$(cd "$REPO_DIR" 2>/dev/null && pwd)"; then
  printf "Error: directory '%s' not found\n" "${2:-.}"
  exit 1
fi
PING_URL="${PING_URL%/}"
export PING_URL
PASS=0
TOTAL=7

log()  { printf "[%s] %b\n" "$(date -u +%H:%M:%S)" "$*"; }
pass() { log "${GREEN}PASSED${NC} -- $1"; PASS=$((PASS + 1)); }
fail() { log "${RED}FAILED${NC} -- $1"; }
hint() { printf "  ${YELLOW}Hint:${NC} %b\n" "$1"; }
stop_at() {
  printf "\n"
  printf "${RED}${BOLD}Validation stopped at %s.${NC} Fix the above before continuing.\n" "$1"
  exit 1
}

printf "\n"
printf "${BOLD}========================================${NC}\n"
printf "${BOLD}  EDA OpenEnv Submission Validator${NC}\n"
printf "${BOLD}========================================${NC}\n"
log "Repo:     $REPO_DIR"
log "Ping URL: $PING_URL"
printf "\n"

# ============================================================
# Step 1/7: Ping HF Space
# ============================================================
log "${BOLD}Step 1/7: Pinging HF Space${NC} ($PING_URL/reset) ..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" -d '{}' \
  "$PING_URL/reset" --max-time 30 2>/dev/null || printf "000")

if [ "$HTTP_CODE" = "200" ]; then
  pass "HF Space is live and responds to /reset"
elif [ "$HTTP_CODE" = "000" ]; then
  fail "HF Space not reachable (connection failed or timed out)"
  hint "Check your network connection and that the Space is running."
  stop_at "Step 1"
else
  fail "HF Space /reset returned HTTP $HTTP_CODE (expected 200)"
  hint "Make sure your Space is running and the URL is correct."
  stop_at "Step 1"
fi

# ============================================================
# Step 2/7: Docker Build
# ============================================================
log "${BOLD}Step 2/7: Running docker build${NC} ..."

if ! command -v docker &>/dev/null; then
  fail "docker command not found"
  hint "Install Docker: https://docs.docker.com/get-docker/"
  stop_at "Step 2"
fi

if [ -f "$REPO_DIR/Dockerfile" ]; then
  DOCKER_CONTEXT="$REPO_DIR"
elif [ -f "$REPO_DIR/server/Dockerfile" ]; then
  DOCKER_CONTEXT="$REPO_DIR/server"
else
  fail "No Dockerfile found in repo root or server/ directory"
  stop_at "Step 2"
fi

BUILD_OK=false
BUILD_OUTPUT=$(run_with_timeout "$DOCKER_BUILD_TIMEOUT" docker build "$DOCKER_CONTEXT" -t eda-openenv-test 2>&1) && BUILD_OK=true

if [ "$BUILD_OK" = true ]; then
  pass "Docker build succeeded"
else
  fail "Docker build failed (timeout=${DOCKER_BUILD_TIMEOUT}s)"
  printf "%s\n" "$BUILD_OUTPUT" | tail -20
  stop_at "Step 2"
fi

# ============================================================
# Step 3/7: OpenEnv Validate
# ============================================================
log "${BOLD}Step 3/7: Running openenv validate${NC} ..."

if ! command -v openenv &>/dev/null; then
  fail "openenv command not found"
  hint "Install it: pip install openenv-core"
  stop_at "Step 3"
fi

VALIDATE_OK=false
VALIDATE_OUTPUT=$(cd "$REPO_DIR" && openenv validate 2>&1) && VALIDATE_OK=true

if [ "$VALIDATE_OK" = true ]; then
  pass "openenv validate passed"
  [ -n "$VALIDATE_OUTPUT" ] && log "  $VALIDATE_OUTPUT"
else
  fail "openenv validate failed"
  printf "%s\n" "$VALIDATE_OUTPUT"
  stop_at "Step 3"
fi

# ============================================================
# Step 4/7: Task Checks (hit reset + step via HTTP)
# ============================================================
log "${BOLD}Step 4/7: Task API checks${NC} ..."

TASKS_OK=true
for SEED in 0 1 2; do
  # Reset with seed
  RESET_RESP=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{\"seed\": $SEED}" \
    "$PING_URL/reset" --max-time 15 2>/dev/null)

  if echo "$RESET_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'observation' in d or 'tool_output' in str(d)" 2>/dev/null; then
    log "  Task seed=$SEED: reset OK"
  else
    log "  Task seed=$SEED: reset response unexpected"
    TASKS_OK=false
  fi

  # Step with compile action
  STEP_RESP=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"tool_name": "query_metrics", "tool_args": {"metric_type": "all"}}' \
    "$PING_URL/step" --max-time 15 2>/dev/null)

  if echo "$STEP_RESP" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    log "  Task seed=$SEED: step OK"
  else
    log "  Task seed=$SEED: step response invalid"
    TASKS_OK=false
  fi
done

if [ "$TASKS_OK" = true ]; then
  pass "All 3 tasks respond to reset + step"
else
  fail "Some task API calls failed"
fi

# ============================================================
# Step 5/7: Grader Determinism
# ============================================================
log "${BOLD}Step 5/7: Grader determinism check${NC} ..."

GRADER_OK=true
GRADER_OUTPUT=$(cd "$REPO_DIR" && python3 -c "
from graders.grader_base import BaseGrader
import os

task_dir = os.path.join('tasks', 'task_1')
grader = BaseGrader(task_dir)

# Run trajectory stability twice
score1 = grader._evaluate_trajectory_stability([])
score2 = grader._evaluate_trajectory_stability([])
assert score1 == score2, f'Non-deterministic: {score1} != {score2}'

print(f'Grader determinism: PASS (score={score1})')
" 2>&1) && true

if echo "$GRADER_OUTPUT" | grep -q "PASS"; then
  pass "Grader determinism verified"
else
  fail "Grader determinism check failed"
  printf "%s\n" "$GRADER_OUTPUT"
fi

# ============================================================
# Step 6/7: Model Tests
# ============================================================
log "${BOLD}Step 6/7: Pydantic model tests${NC} ..."

MODEL_OK=false
MODEL_OUTPUT=$(cd "$REPO_DIR" && python3 -c "
from models import EDAAction, EDAObservation, ToolName

# Test action schema generation
schema = EDAAction.model_json_schema()
assert 'properties' in schema, 'No properties in schema'

# Test all tool names
for t in ToolName:
    a = EDAAction(tool_name=t, tool_args={})
    assert a.tool_name == t

# Test observation
obs = EDAObservation(action_success=True, step_number=1, task_name='test')
assert obs.done is False
assert obs.reward is None

print('Model validation: PASS')
" 2>&1) && MODEL_OK=true

if [ "$MODEL_OK" = true ] && echo "$MODEL_OUTPUT" | grep -q "PASS"; then
  pass "Pydantic models validate correctly"
else
  fail "Model validation failed"
  printf "%s\n" "$MODEL_OUTPUT"
fi

# ============================================================
# Step 7/7: Resource Check
# ============================================================
log "${BOLD}Step 7/7: Resource check${NC} ..."

# Check image size
IMAGE_SIZE=$(docker image inspect eda-openenv-test --format='{{.Size}}' 2>/dev/null || echo "0")
IMAGE_SIZE_GB=$(echo "scale=2; $IMAGE_SIZE / 1073741824" | bc 2>/dev/null || echo "unknown")
log "  Docker image size: ${IMAGE_SIZE_GB} GB"

if [ "$IMAGE_SIZE" -lt 8589934592 ] 2>/dev/null; then
  pass "Docker image under 8GB (${IMAGE_SIZE_GB} GB)"
else
  fail "Docker image exceeds 8GB (${IMAGE_SIZE_GB} GB)"
fi

# ============================================================
# Summary
# ============================================================
printf "\n"
printf "${BOLD}========================================${NC}\n"
if [ "$PASS" -ge "$TOTAL" ]; then
  printf "${GREEN}${BOLD}  All %d/%d checks passed!${NC}\n" "$PASS" "$TOTAL"
  printf "${GREEN}${BOLD}  Your submission is ready.${NC}\n"
else
  printf "${YELLOW}${BOLD}  %d/%d checks passed.${NC}\n" "$PASS" "$TOTAL"
  printf "${YELLOW}${BOLD}  Fix failing checks before submitting.${NC}\n"
fi
printf "${BOLD}========================================${NC}\n"
printf "\n"

[ "$PASS" -ge "$TOTAL" ] && exit 0 || exit 1