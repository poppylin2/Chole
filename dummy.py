import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# =====================
# 0. Random seed (for reproducibility)
# =====================
SEED = 42
random.seed(SEED)

# =====================
# 1. Basic config
# =====================
TOOLS = ["8950XR-P1", "8950XR-P2", "8950XR-P3", "8950XR-P4"]
RECIPES = ["SIPLayer", "S13Layer", "S14Layer", "S15Layer", "WadiLayer"]

# Align data generation window with fab_defect_rules.md's "this week/last week":
# - This week: today (or provided anchor date) minus 7 days, inclusive
# - Last week: the 7 days immediately before this week
ANCHOR_END_DATE = date.fromisoformat(
    os.getenv("DUMMY_ANCHOR_DATE", date.today().isoformat())
)
THIS_WEEK_END = ANCHOR_END_DATE
THIS_WEEK_START = THIS_WEEK_END - timedelta(days=6)
LAST_WEEK_END = THIS_WEEK_START - timedelta(days=1)
LAST_WEEK_START = LAST_WEEK_END - timedelta(days=6)

# Week 1 (last week) dates in ascending order
week1_dates = [LAST_WEEK_START + timedelta(days=i) for i in range(7)]
# Week 2 (this week) dates in ascending order
week2_dates = [THIS_WEEK_START + timedelta(days=i) for i in range(7)]

# Generated records will be stored here
records = []

# key: (tool, recipe) -> week 1 pre sum
week1_sums = {}


# =====================
# 2. Define Healthy / Unhealthy pattern
# =====================
UNHEALTHY_COMBOS = {
    # Only make P2's S13/S14/S15 abnormal -> these recipes trigger Tool Drift at k=1
    "8950XR-P2": {"S13Layer", "S14Layer", "S15Layer"},
    # Only make P1 and P3's WadiLayer abnormal
    "8950XR-P3": {"WadiLayer"},
    "8950XR-P1": {"WadiLayer"},
}


def is_combo_healthy(tool: str, recipe: str) -> bool:
    """
    Return whether a (tool, recipe) pair should be considered "healthy".
    Design goals:
    - P1/P4: all recipes healthy
    - P2: S13/S14/S15 are unhealthy
    - P3: WadiLayer is unhealthy
    """
    return recipe not in UNHEALTHY_COMBOS.get(tool, set())


# =====================
# 3. Generate week 1 (last week) data
# =====================
for tool in TOOLS:
    for recipe in RECIPES:
        key = (tool, recipe)
        sum_week1 = 0

        for d in week1_dates:
            pre = random.randint(800, 1200)
            post = random.randint(250, 350)

            sum_week1 += pre

            records.append(
                {
                    "date": d.isoformat(),  # store as 'YYYY-MM-DD'
                    "tool": tool,
                    "recipe": recipe,
                    "pre_defectwise_count": pre,
                    "post_defectwise_count": post,
                }
            )

        week1_sums[key] = sum_week1

# =====================
# 4. Generate week 2 (this week) data while enforcing healthy/unhealthy targets
# =====================
MAX_ATTEMPTS = 10000  # Shouldn't be needed; prevents infinite loops in extreme cases

for tool in TOOLS:
    for recipe in RECIPES:
        key = (tool, recipe)
        sum_week1 = week1_sums[key]
        target_healthy = is_combo_healthy(tool, recipe)

        # Sample until the difference constraint is satisfied
        for attempt in range(MAX_ATTEMPTS):
            pre_list = [random.randint(800, 1200) for _ in week2_dates]
            sum_week2 = sum(pre_list)
            diff_ratio = (sum_week2 - sum_week1) / sum_week1

            if target_healthy and 0 <= diff_ratio <= 0.10:
                # healthy: diff <= 10%
                break
            if (not target_healthy) and diff_ratio > 0.10:
                # unhealthy: diff > 10%
                break
        else:
            # Only fires in very extreme cases
            raise RuntimeError(
                f"Cannot find suitable week2 data for ({tool}, {recipe}) after {MAX_ATTEMPTS} attempts"
            )

        # Write week 2 data into records
        for d, pre in zip(week2_dates, pre_list):
            post = random.randint(250, 350)
            records.append(
                {
                    "date": d.isoformat(),
                    "tool": tool,
                    "recipe": recipe,
                    "pre_defectwise_count": pre,
                    "post_defectwise_count": post,
                }
            )

# =====================
# 5. Convert to DataFrame and self-check
# =====================
df = pd.DataFrame(records)

print("=== DataFrame Head ===")
print(df.head(), "\n")

# Use groupby to verify weekly totals and health status for each combination
df_check = df.copy()
df_check["date"] = pd.to_datetime(df_check["date"])


def label_week(dt):
    if pd.Timestamp(LAST_WEEK_START) <= dt <= pd.Timestamp(LAST_WEEK_END):
        return "week1"
    if pd.Timestamp(THIS_WEEK_START) <= dt <= pd.Timestamp(THIS_WEEK_END):
        return "week2"
    return "out_of_range"


df_check["week"] = df_check["date"].apply(label_week)

summary = (
    df_check.groupby(["tool", "recipe", "week"])["pre_defectwise_count"]
    .sum()
    .unstack("week")
    .reset_index()
)

summary["diff_ratio"] = (summary["week2"] - summary["week1"]).abs() / summary["week1"]
summary["is_healthy_by_data"] = summary["diff_ratio"] <= 0.10
summary["should_be_healthy"] = summary.apply(
    lambda row: is_combo_healthy(row["tool"], row["recipe"]), axis=1
)

print("=== Weekly Summary (pre_defectwise_count) ===")
print(
    summary[
        [
            "tool",
            "recipe",
            "week1",
            "week2",
            "diff_ratio",
            "is_healthy_by_data",
            "should_be_healthy",
        ]
    ]
    .sort_values(["tool", "recipe"])
    .to_string(index=False)
)

# Simple sanity check: does the intended healthy/unhealthy status match the data?
mismatch = summary[summary["is_healthy_by_data"] != summary["should_be_healthy"]]
if not mismatch.empty:
    print("\n!!! WARNING: There are mismatched health statuses !!!")
    print(mismatch.to_string(index=False))
else:
    print("\nAll health statuses match the design ✅")

# =====================
# 6. Write to SQLite, replacing the defects_daily table
# =====================
# Adjust this path based on your project structure:
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).resolve().parent / "data.sqlite"))
TABLE_NAME = "defects_daily"  # Align with your code if you use a different name (e.g., defects_daliy)

# Ensure date is stored as 'YYYY-MM-DD' string
df_to_db = df.copy()
# If datetime was already converted above this is a no-op; kept for safety
df_to_db["date"] = pd.to_datetime(df_to_db["date"]).dt.strftime("%Y-%m-%d")

conn = sqlite3.connect(str(DB_PATH))
try:
    # Using if_exists='replace' drops and recreates the table
    df_to_db.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
    print(f"\nWrote {len(df_to_db)} rows into {DB_PATH} table '{TABLE_NAME}'.")
finally:
    conn.close()
