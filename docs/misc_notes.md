# Misc Notes for the Fab Copilot

This document focuses on **agent behavior and answer style**.

## 1. Clarifications and context usage

- The router is responsible for deciding when a clarification is needed and for
  asking the clarification question (for example, when a `tool_id` is missing for
  a system-health query).
- Downstream agents (planner, analysts, reporter) should:
  - Use the `clarifications` field and recent `history` to resolve which tool
    and recipe are in scope.
  - Avoid guessing missing identifiers when the router has not provided them.

## 2. Answer style for system health / drift

When giving the **first-pass** system or tool health answer
(using only `defects_daily` + `fab_defect_rules.md`),
structure the response as:

1. **Verdict (1–2 sentences)**

   - Clearly state which tool (and optionally which time window) is being
     evaluated, and whether it is Healthy or Unhealthy.
   - Mention the key drift classification if relevant
     (Tool Drift vs Process Drift).

2. **Defect-based evidence (2–4 bullets or a small table)**

   - Focus on a few important `(tool, recipe)` pairs:
     - weekly sums this week vs last week,
     - whether they are anomalous,
     - whether the anomalies are classified as Tool or Process Drift.

   - List the evidence in a markdown table format.

3. **Optional next steps (0–2 bullets)**

   - High-level suggestions such as monitoring a recipe or checking relevant
     subsystems, based on the evidence, without introducing new data sources.

## 3. Answer style for “reason / subsystem” follow-ups

For follow-up questions about reasons, calibration overdue, or
subsystem / Stage / wafer-center behavior:

1. **Restate the defect-based verdict briefly**

   - Remind the user whether the tool is Healthy or Unhealthy, and which recipes
     show Tool / Process Drift.

2. **Use additional signals to explain “why”**

   - Use `calibrations` to highlight overdue calibrations if there’s any.
   - Use `wc_points` to summarize how much Stage / wafer-center abnormal behavior
     there is, if any.

3. **Suggest concrete actions where appropriate**

   - Examples: perform a specific Stage calibration, or monitor a recipe on all
     tools for a few more days.

### Subsystem health rule (explicit)

- Subsystem health is decided by **calibration overdue** and, for Stage, **wafer-center abnormality** (`wc_points`).
- Do **not** use `defects_daily` drift labels to set subsystem health.
- Per subsystem:
  - If any calibration for that subsystem is overdue → subsystem is Unhealthy.
  - Stage: if `wc_abnormal_ratio > 0.05` this week → Stage is Unhealthy.
  - If neither condition is met → subsystem is Healthy.
- Overall subsystem health for a tool = Healthy only if all subsystems are Healthy; otherwise Unhealthy.

---

## A MUST-FOLLOW Demo Conversation Pattern

1. **System health question**

   - If user asks about system / tool health
     (e.g., “How is system health?” or “Is tool 8950XR-P1 drifting?”).
   - The agent determines the target tool (possibly via clarification) and then
     uses **only table `defects_daily`** and the rules in
     **`eqp_knowledge.md`** and **`fab_defect_rules.md`** to decide:
     - Healthy vs Unhealthy for that tool.
     - Tool Drift vs Process Drift vs no drift per recipe.

2. **System health answer (defect_count based only)**

   - The agent reports the tool’s health and, if needed, mentions which recipes
     show tool-level vs process-level drift.
   - At this stage the agent does **not** use `calibrations` or `wc_points`.

3. **Follow-up on reasons / subsystem health**

   - If the user then asks about **reasons**, **calibration overdue**, or
     **subsystem / Stage / wafer-center health**, the agent:
     - keeps the original Healthy / Unhealthy conclusion unchanged,
     - queries `calibrations` and/or `wc_points`,
     - explains possible reasons and subsystem behavior as supporting evidence.
