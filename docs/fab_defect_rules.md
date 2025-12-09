# Defect & Drift Rules (Compact)

## 1. Time Window
- Use latest `inspection_runs.start_time` as `window_end`.
- `window_start = window_end - 24h` (or other configured window).
- All analysis only uses runs in `[window_start, window_end]`.

## 2. Run-Level Anomaly

### High Defect
A run is high-defect if:
- `defect_count_total > DEFECT_HIGH_THRESHOLD` (default 50), OR
- `run_result = 'HIGH_DEFECT'`.

### Alignment Failure
A run has align fail if:
- `run_time_align_fail > 0`, OR
- `run_result = 'ALIGN_FAIL'`.

## 3. Per (tool, recipe) Aggregation

For each `(tool_id, recipe_id)` in the window:

- `total_runs`
- `abnormal_defect_runs` = count of high-defect runs
- `abnormal_align_runs` = count of align-fail runs

Ratios:

- `defect_anomaly_ratio = abnormal_defect_runs / total_runs`
- `align_anomaly_ratio  = abnormal_align_runs / total_runs`
- If `total_runs = 0` → ratios = 0.

## 4. Status Threshold

Global ratio threshold:

- `ANOMALY_RATIO_THRESHOLD = 0.05` (5%)

Status:

- `DEFECT_STATUS = HIGH` if `defect_anomaly_ratio > threshold`, else `NORMAL`.
- `ALIGN_STATUS = HIGH` if `align_anomaly_ratio  > threshold`, else `NORMAL`.

A **problem pair** is any `(tool, recipe)` where
- `DEFECT_STATUS = HIGH` OR `ALIGN_STATUS = HIGH`.

If all pairs are NORMAL → system is overall healthy (in this dimension).

## 5. Drift Type (Tool vs Process)

For a problem pair `(tool = T*, recipe = R)`:

1. Compute status for all tools on recipe `R`.
2. Mark each tool abnormal on `R` if:
   - `DEFECT_STATUS = HIGH` OR `ALIGN_STATUS = HIGH`.

Let `current_tool = T*`, `other_tools = all tools ≠ T*`:

- If current is NOT abnormal → `drift_type = UNKNOWN`.
- If current is abnormal and:
  - `other_abnormal_count = 0` → `TOOL_DRIFT`.
  - `other_abnormal_count = len(other_tools)` → `PROCESS_DRIFT`.
  - else → `MIXED`.

This drift label is only about **pattern of anomalies across tools**,
not about root cause by itself.
