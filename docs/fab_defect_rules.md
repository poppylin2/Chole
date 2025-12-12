# System Health, Fab Defect & Drift Rules

This document is the **single source of truth** for:

- How to compute defect anomalies per (tool, recipe).
- How to classify **Tool Drift** vs **Process (Recipe) Drift**.
- How to decide whether a tool/system is **Healthy** or **Unhealthy**.
- How to interpret calibration overdue and wafer-center abnormal behavior.

All agents that reason about health or drift must follow these rules exactly.

---

## 1. Time Windows

When a user asks about “this week vs last week” or “the past week”:

- **This week**: the most recent 7 calendar days up to and including the current analysis date.
- **Last week**: the 7 days immediately preceding “this week”.

The exact date boundaries are implemented in SQL; this document only defines the logic.

---

## 2. `defects_daily`: the only source for system health classification

Each row represents defect count data for a specific tool, recipe, and date.  
It includes:

- `pre_defectwise_count`: the number of defects detected before processing.
- `post_defectwise_count`: the number of defects detected after processing.

For health monitoring and drift analysis, **only `pre_defectwise_count` is used**.

---

### 2.1 Weekly sums per (tool, recipe)

- `S_this_week(T, R)` = sum of `pre_defectwise_count` over **this week**.
- `S_last_week(T, R)` = sum of `pre_defectwise_count` over **last week**.

If `S_last_week(T, R) > 0`, define:
diff_pct(T, R) = abs(S_this_week(T, R) - S_last_week(T, R)) / S_last_week(T, R)
Interpretation for `(T, R)`:

- If `diff_pct(T, R) > 0.10` → `(T, R)` is **anomalous this week**.
- Otherwise → `(T, R)` is **not anomalous**.
- If `S_last_week(T, R) == 0` → baseline is insufficient; treat the drift state
  as **UNKNOWN** and explicitly mention this if relevant.

---

### 2.2 Recipe-level drift: Tool vs Process

For each recipe `R`, consider all tools `{T}` that run `R`.

Let `K` be the number of tools whose `(T, R)` is anomalous this week.

Rules:

- `K == 0`  
  → Recipe `R` is stable this week (no drift).

- `K == 1`  
  → The single anomalous `(T, R)` is classified as **Tool Drift** for that
    particular tool on recipe `R`.

- `K >= 2`  
  → Recipe `R` is classified as **Process Drift**; all anomalous `(T, R)` pairs
    on `R` are considered process-driven rather than tool-driven.

---

### 2.3 Tool / system health

For a given tool `T`, look at all recipes `R` that `T` runs:

- If **any** recipe `R` on tool `T` is classified as **Tool Drift**  
  → Tool `T` (the “system”) is **Unhealthy** and is said to have drifted as
    shown on recipe `R`.

- If **no** recipe on `T` is Tool Drift  
  (i.e., recipes are either Stable, Process Drift, or UNKNOWN)  
  → Tool `T` is considered **Healthy** from the tool perspective.

If some `(T, R)` are UNKNOWN (e.g., `S_last_week(T, R) == 0`), the tool can still
be Healthy, but the answer should mention that parts of the baseline are
insufficient.

> **Important**:
> - Only `defects_daily` and the rules above decide **Healthy vs Unhealthy** and
>   **Tool Drift vs Process Drift**.
> - Nothing from `calibrations` or `wc_points` is allowed to override this
>   classification.

---

## 3. `calibrations`: overdue checks (supporting evidence only)

Logical columns:

- `calibrations(tool, subsystem, cal_name, last_cal_date, freq_days)`

For each row `(T, SubS, Cal)`:
due_date = last_cal_date + freq_days (in days)
Let `D` be the analysis date (typically “today”).

- If `D > due_date` → that calibration for `(T, SubS, Cal)` is **overdue**.
- If `D <= due_date` → it is **not overdue yet**.

Usage:

- Overdue calibrations are treated as **possible reasons** for tool-level drift
  or subsystem problems.

---

## 4. `wc_points`: wafer-center abnormal behavior

Logical columns:

- `wc_points(tool, date, timestamp, x, y, recipe)`

Each row represents one inspection’s wafer-center coordinates for a given
(tool, recipe) and time.

---

### 4.1 Single-run Stage abnormality

For a single row `(x, y)`:

Wafer center coordinate is abnormal for this run if:


abs(x) > 150 OR abs(y) > 150

---

### 4.2 Weekly Stage abnormal counts and change

For each `(T, R)`:

- `ST_ab_this_week(T, R)` = number of rows in the time window where the run is abnormal.
- `ST_sum_this_week(T, R)` = total number of rows in the time window.
- `wc_abnormal_ratio(T, R)` =  
  `ST_ab_this_week(T, R) / ST_sum_this_week(T, R)`

Interpretation:

- If `wc_abnormal_ratio(T, R) > 0.05`  
  → wafer-center is considered **abnormal this week**.  
    This indicates the Stage subsystem is not healthy.
- Otherwise → Stage subsystem is considered stable.

Usage:

- Wafer-center abnormality is used to describe **subsystem health** and
  **possible reasons** behind tool-level drift, especially for the Stage
  subsystem.
