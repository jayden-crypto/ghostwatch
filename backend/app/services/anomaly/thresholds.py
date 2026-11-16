"""Every threshold the anomaly rules use (contract §8), in one place so they are easy to show and tune.

The rules quote these values in their explanations, so changing a number here changes the text too.
"""

# Baseline: the agent's most recent completed, non-replay executions before the one being evaluated.
BASELINE_SIZE = 20
MIN_BASELINE_RUNS = 5  # rules that need a baseline are skipped below this

# duration_spike: duration_ms > max(3 x median, 1.5 x p95); high above 5 x median.
DURATION_SPIKE_MEDIAN_FACTOR = 3
DURATION_SPIKE_P95_FACTOR = 1.5
DURATION_SPIKE_HIGH_MEDIAN_FACTOR = 5

# token_spike: tokens_total > max(2 x median, p95); high above 4 x median.
TOKEN_SPIKE_MEDIAN_FACTOR = 2
TOKEN_SPIKE_P95_FACTOR = 1
TOKEN_SPIKE_HIGH_MEDIAN_FACTOR = 4

# repeated_tool_failure: >= 3 failed steps of one tool in an execution, or the agent's last 3
# executions each failed on a step of the same tool.
TOOL_FAILURES_IN_ONE_EXECUTION = 3
TOOL_FAILURE_CONSECUTIVE_EXECUTIONS = 3

# excessive_retries: any step with attempt >= 3, or sum of (attempt - 1) >= 5.
RETRY_ATTEMPT_LIMIT = 3
RETRY_TOTAL_LIMIT = 5

# repeated_timeouts: >= 3 of the agent's last 10 executions timed out.
TIMEOUTS_LIMIT = 3
TIMEOUTS_WINDOW = 10

# stale_execution: running with no event for config.timeout_ms; this default applies when it is null.
DEFAULT_TIMEOUT_MS = 300_000

# unexpected_pattern: step_count > 2 x the largest baseline step_count (or a tool never seen before).
STEP_COUNT_FACTOR = 2

# How many evidence items one anomaly lists at most.
MAX_EVIDENCE_ITEMS = 10

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
