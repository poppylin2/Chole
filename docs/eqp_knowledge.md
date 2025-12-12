# Equipment Knowledge

## 1. Tools

- Four tools: `8950XR-P1`, `8950XR-P2`, `8950XR-P3`, `8950XR-P4`.
- Health can differ per tool.

### System vs Tool

- In this agent, **one physical tool = one "system"**.
- When a user asks "How's the system health?", it should be interpreted as:
  > "How is the health of a specific tool (e.g. `8950XR-P2`)?"
- If the user does **not** specify which tool (`tool_id`) they mean, the agent
  should first ask:
  > Which tool do you want me to check? (`8950XR-P1`, `8950XR-P2`, `8950XR-P3`, `8950XR-P4`)

## 2. Subsystems

Each tool has 4 subsystems:

1. `Stage`
   - Wafer handling & positioning (X/Y).
   - Metrics: wafer center points (x, y) in table `wc_points`.
   - Spec: wafer center points (x, y) should range from `[-150, 150]`.
   - This subsystem is degraded if wafer center out-of-spec ratio is more than 5%.

2. `Canera`
   - Image acquisition.

3. `Focus`
   - Controls focal plane.

4. `Illumination`
   - Light source / illumination control.
   - Calibrated via `Illumination` calibration type.

## 3. Calibration Types

From `calibrations.cal_name`:

- `PrealignerToStage`
  - Aligns prealigner to stage coordinates.
  - Overdue + tool anomalies → strong tool-drift evidence.

- `GantryOffset`
  - Aligns optics / gantry to stage.

- `ChuckCenterTheta`
  - Calibrates chuck center and rotation.

- `Illumination`
  - Calibrates illumination system.

Each record has:
- Next due date = `last_cal_date + freq_days`;
- It is overdue if `< now`.

## 4. Linking Behavior to Drift

**Tool Drift pattern**:
- One tool shows high anomaly ratio on recipe R.
- All other tools on R look normal.
- Often combined with overdue calibration and/or STAGE subsystem metrics
  (wafer center) out-of-spec.

**Process Drift pattern**:
- More than one tool shows anomalies on the same recipe R.
- Calibrations and wafer center points mostly healthy.
- Suggests recipe / process-level issue.
