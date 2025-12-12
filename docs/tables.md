# Table Glossary

## defects_daily

Logical columns:
- `date` – calendar date.
- `tool` – tool identifier (e.g., 8950XR-P1).
- `recipe` – recipe name.
- `pre_defectwise_count` – defect count used for health/drift rules.
- `post_defectwise_count` – not used by current use case.

## wc_points

Logical columns:
- `tool`
- `date`
- `timestamp` – e.g., "2025-12-09 02:37:33 +08:00"
- `x`, `y` – wafer-center coordinates
- `recipe`

## calibrations

Logical columns:
- `tool`
- `subsystem`
- `cal_name`
- `last_cal_date`
- `freq_days` – due date = `last_cal_date + freq_days`
