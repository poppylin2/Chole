# Equipment Knowledge (Compact)

## 1. Tools

- Four tools: `8950XR-P1`, `8950XR-P2`, `8950XR-P3`, `8950XR-P4`.
- Same platform, same recipes; health can differ per tool.

### System vs Tool

- In this agent, **one physical tool = one "system"**.
- When a user asks "How's the system health?", it should be interpreted as
  "How is the health of a specific tool (e.g. `8950XR-P2`)?"
- The agent **must not** silently aggregate across all tools when answering
  a "system health" question.
- If the user does **not** specify which tool (tool_id) they mean, the agent
  should first ask:
  > Which tool do you want me to check? (8950XR-P1, 8950XR-P2, 8950XR-P3, 8950XR-P4)

## 2. Subsystems

Each tool has 4 subsystems:

1. `STAGE`  
   - Wafer handling & positioning (X/Y, rotation).
   - Metrics: `STAGE_POS_X`, `STAGE_POS_Y` in `subsystem_health_metrics`.
   - Spec: `spec_low`, `spec_high` (e.g. [-150, 150]).
   - Status: `OK` / `WARN` / `ALERT`.
   - Out-of-spec values or `WARN/ALERT` = sign of mechanical/position issues.

2. `CAMERA`  
   - Image acquisition.
   - Issues → false defects, missed defects (conceptual, not explicitly modeled).

3. `FOCUS`  
   - Controls focal plane.
   - Poor focus → blur → defect misclassification (conceptual).

4. `ILLUMINATION`  
   - Light source / illumination control.
   - Calibrated via `Illumination` calibration type.

## 3. Calibration Types

From `calibration_runs.calib_type`:

- `PrealignerToStage`  
  - Aligns prealigner to stage coordinates.  
  - Overdue + tool anomalies → strong tool-drift evidence.

- `GantryOffset`  
  - Aligns optics/gantry to stage.

- `ChuckCenterTheta`  
  - Calibrates chuck center and rotation.

- `Illumination`  
  - Calibrates illumination system.

Each record has:
- `next_due_time`: overdue if `< now`.
- `status`: `PASSED` / `FAILED`.

## 4. Linking Behavior to Drift

- **Tool Drift pattern**:
  - One tool shows high anomaly ratio on recipe R.
  - Other tools on R look normal.
  - Often combined with overdue calibration and/or STAGE metrics out-of-spec.

- **Process Drift pattern**:
  - Many tools show anomalies on the same recipe R.
  - Calibrations and STAGE metrics mostly healthy.
  - Suggests recipe/process-level issue.

The dataset is synthetic but encodes:
- Tool drift: `8950XR-P2` on `S13Layer` (high defect, STAGE issues).
- Process drift: `WadiLayer` across multiple tools (align issues).
