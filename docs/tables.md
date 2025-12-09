# Data Dictionary: Fab Inspection Demo Database

This document describes the schema of the `data.sqlite` database used for fab
inspection and equipment health analysis. It focuses on tables, columns, and
logical relationships rather than any specific agent implementation.

---

## Overview

The database models a simplified fab inspection environment with:

- Four inspection tools (8950XR-P1, P2, P3, P4)
- Four subsystems per tool (STAGE, CAMERA, FOCUS, ILLUMINATION)
- Five inspection recipes (SIPLayer, S13Layer, S14Layer, S15Layer, WadiLayer)
- Run-level inspection data (defects, alignment failures)
- Calibration history per subsystem
- Stage-position health metrics (X/Y position vs spec)

Core tables:

1. `tools`
2. `subsystems`
3. `recipes`
4. `inspection_runs`
5. `calibration_runs`
6. `subsystem_health_metrics`

---

## Table: `tools`

**Purpose:** Master list of inspection tools.

| Column   | Type | Description                          |
|----------|------|--------------------------------------|
| tool_id  | TEXT | Primary key. Identifier for a tool. |

**Notes:**

- Example values: `8950XR-P1`, `8950XR-P2`, `8950XR-P3`, `8950XR-P4`.
- Referenced by multiple tables (`subsystems`, `inspection_runs`, `calibration_runs`).

---

## Table: `subsystems`

**Purpose:** Enumerates subsystems for each tool.

| Column       | Type    | Description                                             |
|--------------|---------|---------------------------------------------------------|
| subsystem_id | INTEGER | Primary key (AUTOINCREMENT).                            |
| tool_id      | TEXT    | FK → `tools.tool_id`.                                   |
| name         | TEXT    | Subsystem name: `STAGE`, `CAMERA`, `FOCUS`, `ILLUMINATION`. |

**Logical relations:**

- Each tool has four subsystems (one per name).
- `subsystem_id` is used by:
  - `calibration_runs` to store calibration history.
  - `subsystem_health_metrics` to store health metrics.

---

## Table: `recipes`

**Purpose:** Master list of inspection recipes.

| Column      | Type    | Description                           |
|-------------|---------|---------------------------------------|
| recipe_id   | INTEGER | Primary key (AUTOINCREMENT).          |
| recipe_name | TEXT    | Unique recipe name (e.g., `S13Layer`). |

**Notes:**

- Example values: `SIPLayer`, `S13Layer`, `S14Layer`, `S15Layer`, `WadiLayer`.
- `recipe_id` is referenced by `inspection_runs`.

---

## Table: `inspection_runs`

**Purpose:** Run-level inspection data. This is the primary source for “system
health” from the product/inspection outcome perspective.

| Column             | Type    | Description                                                                 |
|--------------------|---------|-----------------------------------------------------------------------------|
| run_id             | INTEGER | Primary key (AUTOINCREMENT).                                               |
| tool_id            | TEXT    | FK → `tools.tool_id`.                                                       |
| recipe_id          | INTEGER | FK → `recipes.recipe_id`.                                                   |
| start_time         | DATETIME| Run start timestamp (ISO-8601 string).                                     |
| end_time           | DATETIME| Run end timestamp (ISO-8601 string).                                       |
| defect_count_total | INTEGER | Total defect count observed in this run.                                   |
| run_time_align_fail| INTEGER | Alignment failure flag/count (0 = no align fail, >0 = alignment issue).    |
| run_result         | TEXT    | Categorical summary: `NORMAL`, `HIGH_DEFECT`, `ALIGN_FAIL`, etc.           |

**Typical usage:**

- Grouped by `(tool_id, recipe_id)` over a time window to compute:
  - `total_runs`
  - `abnormal_defect_runs`
  - `abnormal_align_runs`
- Used to derive:
  - `defect_anomaly_ratio`
  - `align_anomaly_ratio`
- Serves as the first-layer health filter.

**Index:**

- `idx_inspection_runs_tool_recipe_time` on `(tool_id, recipe_id, start_time)`
  for efficient time-window queries.

---

## Table: `calibration_runs`

**Purpose:** Records calibration history per tool and subsystem, for different
calibration types.

| Column       | Type    | Description                                                       |
|--------------|---------|-------------------------------------------------------------------|
| calib_id     | INTEGER | Primary key (AUTOINCREMENT).                                      |
| tool_id      | TEXT    | FK → `tools.tool_id`.                                             |
| subsystem_id | INTEGER | FK → `subsystems.subsystem_id`.                                   |
| calib_type   | TEXT    | Calibration type (e.g., `PrealignerToStage`, `GantryOffset`).     |
| start_time   | DATETIME| Calibration start time.                                           |
| end_time     | DATETIME| Calibration end time.                                             |
| next_due_time| DATETIME| Next due time; if in the past, the calibration is considered overdue. |
| status       | TEXT    | Calibration result, typically `PASSED` or `FAILED`.              |

**Typical calibration types:**

- `PrealignerToStage`
- `GantryOffset`
- `ChuckCenterTheta`
- `Illumination`

**Logical usage:**

- For each `(tool, subsystem, calib_type)`, the most recent calibration record
  (by `end_time`) is used to determine:
  - Whether the calibration is **overdue** (`next_due_time` < reference time).
  - Whether the last calibration **failed** (`status = 'FAILED'`).

**Index:**

- `idx_calibration_runs_tool_subsystem` on `(tool_id, subsystem_id, next_due_time)`.

---

## Table: `subsystem_health_metrics`

**Purpose:** Numeric health metrics per subsystem over time. In this demo, it
captures STAGE X/Y position values for each tool.

| Column       | Type    | Description                                                           |
|--------------|---------|-----------------------------------------------------------------------|
| metric_id    | INTEGER | Primary key (AUTOINCREMENT).                                          |
| subsystem_id | INTEGER | FK → `subsystems.subsystem_id`.                                       |
| ts           | DATETIME| Timestamp of the measurement.                                         |
| metric_name  | TEXT    | Metric name, e.g.: `STAGE_POS_X`, `STAGE_POS_Y`.                      |
| metric_value | REAL    | Numeric value of the metric (e.g., position in µm or equivalent units). |
| spec_low     | REAL    | Lower spec limit for the metric (e.g., -150).                         |
| spec_high    | REAL    | Upper spec limit for the metric (e.g., 150).                          |
| status       | TEXT    | Health status: `OK`, `WARN`, or `ALERT`.                              |

**Typical usage:**

- For STAGE subsystem of each tool:
  - Check if any `metric_value` is outside `[spec_low, spec_high]`.
  - Check if any `status` is `WARN` or `ALERT`.
- Used as evidence for mechanical / positional issues contributing to tool drift.

**Index:**

- `idx_subsys_metrics_subsystem_ts` on `(subsystem_id, ts)`.

---

## Key Relationships Summary

- `tools (1) — (N) subsystems`
- `tools (1) — (N) inspection_runs`
- `recipes (1) — (N) inspection_runs`
- `subsystems (1) — (N) calibration_runs`
- `subsystems (1) — (N) subsystem_health_metrics`

These relationships enable multi-layer reasoning:

1. **Outcome-level**: `inspection_runs` → detect abnormal defect / alignment behavior.
2. **Maintenance-level**: `calibration_runs` → detect overdue or failed calibrations.
3. **Hardware-level**: `subsystem_health_metrics` → detect out-of-spec or ALERT metrics.