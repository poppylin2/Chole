import pandas as pd
import numpy as np

# from caas_jupyter_tools import display_dataframe_to_user

CSV_PATH = "defects_daily_export.csv"

df = pd.read_csv(CSV_PATH)
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df = df.dropna(subset=["date"])

end = df["date"].max().normalize()
this_start = end - pd.Timedelta(days=6)
this_end = end
last_start = end - pd.Timedelta(days=13)
last_end = end - pd.Timedelta(days=7)

this_week = (
    df[(df["date"] >= this_start) & (df["date"] <= this_end)]
    .groupby(["tool", "recipe"], as_index=False)["pre_defectwise_count"]
    .sum()
    .rename(columns={"pre_defectwise_count": "this_week_pre"})
)

last_week = (
    df[(df["date"] >= last_start) & (df["date"] <= last_end)]
    .groupby(["tool", "recipe"], as_index=False)["pre_defectwise_count"]
    .sum()
    .rename(columns={"pre_defectwise_count": "last_week_pre"})
)

merged = this_week.merge(last_week, on=["tool", "recipe"], how="outer")

merged["diff_rate"] = np.where(
    merged["last_week_pre"].fillna(0) == 0,
    np.nan,
    (merged["this_week_pre"].fillna(0) - merged["last_week_pre"])
    / merged["last_week_pre"],
)

matrix = merged.pivot(index="recipe", columns="tool", values="diff_rate").sort_index()

# For display: round and keep as float
matrix_display = matrix.round(4)

meta = pd.DataFrame(
    {
        "end_date_used": [end.date()],
        "this_week_range": [f"{this_start.date()} ~ {this_end.date()}"],
        "last_week_range": [f"{last_start.date()} ~ {last_end.date()}"],
        "rows(recipes)": [matrix_display.shape[0]],
        "cols(tools)": [matrix_display.shape[1]],
    }
)

# display_dataframe_to_user("Week ranges used", meta)
# display_dataframe_to_user("Tool x Recipe diff_rate matrix", matrix_display)

# meta, matrix_display.head()


print(meta)

print("=====================================================================")

print(matrix_display)
