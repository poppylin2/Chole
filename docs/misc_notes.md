# Misc Notes (Compact)

## 1. Time & Window

- Default analysis window: last 24h of `inspection_runs.start_time`.
- Derived as:
  - `window_end = max(start_time)`
  - `window_start = window_end - 24h`

Can be tuned (e.g., 8h / 72h) depending on use case.

## 2. Thresholds

- `DEFECT_HIGH_THRESHOLD = 50` for high-defect runs.
- `ANOMALY_RATIO_THRESHOLD = 0.05` for status HIGH vs NORMAL.

In a real fab, thresholds may:
- Differ per recipe/tool.
- Be based on historical statistics.

## 3. Status Fields

### `inspection_runs.run_result`
- Convenience label like `NORMAL`, `HIGH_DEFECT`, `ALIGN_FAIL`.
- Numeric fields (`defect_count_total`, `run_time_align_fail`) are primary.

### `calibration_runs.status`
- `PASSED` / `FAILED`.  
- Overdue is inferred via `next_due_time < now`, not via status string.

### `subsystem_health_metrics.status`
- `OK` / `WARN` / `ALERT`.  
- `WARN`/`ALERT` treated as problematic even if numeric value is near spec.

## 4. Interpretation Pattern

When investigating a (tool, recipe) problem:

1. Check outcome anomalies:
   - defect / align anomaly ratios.
2. Check calibration:
   - overdue or FAILED?
3. Check subsystem metrics:
   - STAGE_POS_X/Y out-of-spec, `WARN`/`ALERT`?
4. Compare tools:
   - Only one tool abnormal → likely **TOOL_DRIFT**.
   - Many tools on same recipe abnormal → likely **PROCESS_DRIFT**.
   - Mixed → **MIXED**; need deeper investigation.

## 5. Synthetic Data Reminder

- `data.sqlite` is synthetic.
- Encodes:
  - One clear tool drift example: `P2` + `S13Layer`.
  - One clear process drift example: `WadiLayer` across tools.
- Intended for agent reasoning / demo, not real fab production data.

## 6. System Health Questions

- Treat each tool as a separate "system".
- If no tool_id is provided, ask the user to choose one.
