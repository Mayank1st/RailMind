# Admin AI Control → LLM Usage (Gemini/Replicate call telemetry).
#
# Read-side of the llm_usage_logs table, rolled up per hour. Calls are captured
# best-effort by the LLM clients (app.core.llm_usage_writer). Status values live
# in the writer module.

# Default rollup window + bounds (hours).
DEFAULT_USAGE_WINDOW_HOURS = 24
MAX_USAGE_WINDOW_HOURS = 168  # 7 days

# CSV export row cap.
LLM_USAGE_EXPORT_MAX_HOURS = MAX_USAGE_WINDOW_HOURS
