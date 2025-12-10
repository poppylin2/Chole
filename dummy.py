#!/usr/bin/env python
"""
Generate a fake data.sqlite for fab inspection / equipment health demo.

Tables:
- tools
- subsystems
- recipes
- inspection_runs
- calibration_runs
- subsystem_health_metrics

Scenarios encoded in fake data:
- TOOL_DRIFT:
    8950XR-P2 on S13Layer has high defect_count_total anomaly ratio.
    Other tools on S13Layer mostly normal.
- PROCESS_DRIFT:
    WadiLayer shows elevated align_fail ratio across all tools.
- NORMAL:
    Other tool+recipe combinations mostly healthy.

Calibration & metrics:
- 8950XR-P2 STAGE has an overdue PrealignerToStage calibration
  and some STAGE_POS_X values out of spec with ALERT.
- Other tools/subsystems are mostly well calibrated and in-spec.
"""

import os
import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "data.sqlite"
RANDOM_SEED = 42


def reset_db(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Drop old tables if they exist
    cur.executescript(
        """
        DROP TABLE IF EXISTS subsystem_health_metrics;
        DROP TABLE IF EXISTS calibration_runs;
        DROP TABLE IF EXISTS inspection_runs;
        DROP TABLE IF EXISTS subsystems;
        DROP TABLE IF EXISTS recipes;
        DROP TABLE IF EXISTS tools;
        """
    )

    # Create tables
    cur.executescript(
        """
        CREATE TABLE tools (
            tool_id TEXT PRIMARY KEY
        );

        CREATE TABLE subsystems (
            subsystem_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id TEXT NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (tool_id) REFERENCES tools(tool_id)
        );

        CREATE TABLE recipes (
            recipe_id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE inspection_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id TEXT NOT NULL,
            recipe_id INTEGER NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            defect_count_total INTEGER NOT NULL,
            run_time_align_fail INTEGER NOT NULL,
            run_result TEXT NOT NULL,
            FOREIGN KEY (tool_id) REFERENCES tools(tool_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id)
        );

        CREATE TABLE calibration_runs (
            calib_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id TEXT NOT NULL,
            subsystem_id INTEGER NOT NULL,
            calib_type TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            next_due_time DATETIME NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (tool_id) REFERENCES tools(tool_id),
            FOREIGN KEY (subsystem_id) REFERENCES subsystems(subsystem_id)
        );

        CREATE TABLE subsystem_health_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subsystem_id INTEGER NOT NULL,
            ts DATETIME NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            spec_low REAL NOT NULL,
            spec_high REAL NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (subsystem_id) REFERENCES subsystems(subsystem_id)
        );

        -- Helpful indexes
        CREATE INDEX idx_inspection_runs_tool_recipe_time
            ON inspection_runs (tool_id, recipe_id, start_time);

        CREATE INDEX idx_calibration_runs_tool_subsystem
            ON calibration_runs (tool_id, subsystem_id, next_due_time);

        CREATE INDEX idx_subsys_metrics_subsystem_ts
            ON subsystem_health_metrics (subsystem_id, ts);
        """
    )

    conn.commit()


def seed_dimension_tables(conn: sqlite3.Connection):
    cur = conn.cursor()

    tools = ["8950XR-P1", "8950XR-P2", "8950XR-P3", "8950XR-P4"]
    recipes = ["SIPLayer", "S13Layer", "S14Layer", "S15Layer", "WadiLayer"]
    subsys_names = ["STAGE", "CAMERA", "FOCUS", "ILLUMINATION"]

    # tools
    cur.executemany("INSERT INTO tools(tool_id) VALUES (?)", [(t,) for t in tools])

    # recipes
    cur.executemany(
        "INSERT INTO recipes(recipe_name) VALUES (?)", [(r,) for r in recipes]
    )

    # subsystems
    for tool_id in tools:
        for name in subsys_names:
            cur.execute(
                "INSERT INTO subsystems(tool_id, name) VALUES (?, ?)",
                (tool_id, name),
            )

    conn.commit()

    # Build helper dicts for later use
    cur.execute("SELECT recipe_id, recipe_name FROM recipes")
    recipe_map = {name: rid for rid, name in cur.fetchall()}

    cur.execute("SELECT subsystem_id, tool_id, name FROM subsystems")
    subsystems = cur.fetchall()
    # (tool_id, name) -> subsystem_id
    subsys_map = {(tool_id, name): sid for (sid, tool_id, name) in subsystems}

    return {
        "tools": tools,
        "recipes": recipes,
        "recipe_map": recipe_map,
        "subsys_map": subsys_map,
    }


def seed_inspection_runs(conn: sqlite3.Connection, dim: dict):
    """
    Generate inspection_runs data with:
    - TOOL_DRIFT on (P2, S13Layer): high defect_count_total anomaly ratio.
    - PROCESS_DRIFT on WadiLayer: align_fail elevated for all tools.
    - Everything else mostly normal.
    """
    cur = conn.cursor()

    tools = dim["tools"]
    recipe_map = dim["recipe_map"]

    now = datetime.now()
    base_start = now - timedelta(days=3)

    # Config
    days = 3
    runs_per_day_per_combo = 20
    defect_threshold = 50  # used implicitly in data generation
    process_drift_recipe = "WadiLayer"
    tool_drift_tool = "8950XR-P2"
    tool_drift_recipe = "S13Layer"

    for day_offset in range(days):
        day_start = base_start + timedelta(days=day_offset)

        for tool_id in tools:
            for recipe_name, recipe_id in recipe_map.items():
                for i in range(runs_per_day_per_combo):
                    # Each run ~5 minutes apart random-ish
                    start_time = day_start + timedelta(
                        minutes=5 * i + random.randint(0, 3)
                    )
                    end_time = start_time + timedelta(minutes=5)

                    # Default "normal" behavior
                    defect_count = max(
                        0, int(random.gauss(mu=10, sigma=5))
                    )  # small defect
                    run_time_align_fail = 0
                    run_result = "NORMAL"

                    # TOOL_DRIFT scenario:
                    # 8950XR-P2 + S13Layer has many high-defect runs
                    if tool_id == tool_drift_tool and recipe_name == tool_drift_recipe:
                        # Make ~40% of runs high defect
                        if random.random() < 0.4:
                            defect_count = int(random.gauss(mu=80, sigma=15))
                            run_result = "HIGH_DEFECT"
                        else:
                            defect_count = max(
                                0, int(random.gauss(mu=15, sigma=5))
                            )

                    # PROCESS_DRIFT scenario:
                    # WadiLayer has higher align_fail across all tools
                    if recipe_name == process_drift_recipe:
                        # ~25% runs have align_fail
                        if random.random() < 0.25:
                            run_time_align_fail = 1
                            # some of them also have small defects, but not huge
                            defect_count = max(
                                defect_count, int(random.gauss(mu=20, sigma=10))
                            )
                            if run_result == "NORMAL":
                                run_result = "ALIGN_FAIL"

                    # small random noise: tiny probability of random issues
                    if run_result == "NORMAL" and random.random() < 0.02:
                        # occasional random align fail or slightly higher defect
                        if random.random() < 0.5:
                            run_time_align_fail = 1
                            run_result = "ALIGN_FAIL"
                        else:
                            defect_count = max(defect_count, 30)

                    cur.execute(
                        """
                        INSERT INTO inspection_runs(
                            tool_id, recipe_id, start_time, end_time,
                            defect_count_total, run_time_align_fail, run_result
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tool_id,
                            recipe_id,
                            start_time.isoformat(timespec="seconds"),
                            end_time.isoformat(timespec="seconds"),
                            defect_count,
                            run_time_align_fail,
                            run_result,
                        ),
                    )

    conn.commit()


def seed_calibration_runs(conn: sqlite3.Connection, dim: dict):
    """
    Generate calibration_runs:
    - For all tools/subsystems: mostly up-to-date PASSED calibrations.
    - For 8950XR-P2 STAGE:
        One PrealignerToStage calibration overdue (next_due_time in the past).
    """
    cur = conn.cursor()

    subsys_map = dim["subsys_map"]
    tools = dim["tools"]

    now = datetime.now()
    calib_types = ["PrealignerToStage", "GantryOffset", "ChuckCenterTheta", "Illumination"]

    for tool_id in tools:
        for name in ["STAGE", "CAMERA", "FOCUS", "ILLUMINATION"]:
            subsystem_id = subsys_map[(tool_id, name)]

            for calib_type in calib_types:
                # Map calib_type to a "likely" subsystem, but we keep it simple:
                # - PrealignerToStage, GantryOffset, ChuckCenterTheta -> STAGE
                # - Illumination -> ILLUMINATION
                if calib_type == "Illumination" and name != "ILLUMINATION":
                    continue
                if calib_type != "Illumination" and name != "STAGE":
                    continue

                # Default: recent calibration, next_due_time in future
                end_time = now - timedelta(days=random.randint(1, 5))
                start_time = end_time - timedelta(hours=1)
                next_due_time = end_time + timedelta(days=7)
                status = "PASSED"

                # Special case: 8950XR-P2 STAGE PrealignerToStage is overdue
                if (
                    tool_id == "8950XR-P2"
                    and name == "STAGE"
                    and calib_type == "PrealignerToStage"
                ):
                    end_time = now - timedelta(days=10)
                    start_time = end_time - timedelta(hours=1)
                    next_due_time = now - timedelta(days=2)  # in the past → overdue
                    status = "PASSED"

                cur.execute(
                    """
                    INSERT INTO calibration_runs(
                        tool_id, subsystem_id, calib_type,
                        start_time, end_time, next_due_time, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tool_id,
                        subsystem_id,
                        calib_type,
                        start_time.isoformat(timespec="seconds"),
                        end_time.isoformat(timespec="seconds"),
                        next_due_time.isoformat(timespec="seconds"),
                        status,
                    ),
                )

    conn.commit()


def seed_subsystem_health_metrics(conn: sqlite3.Connection, dim: dict):
    """
    Generate subsystem_health_metrics:
    - For each tool's STAGE:
        - Mostly values within [-150, 150], status OK.
    - For 8950XR-P2 STAGE:
        - Some STAGE_POS_X metrics out of spec (>150) with ALERT.
    """
    cur = conn.cursor()

    subsys_map = dim["subsys_map"]
    tools = dim["tools"]

    now = datetime.now()
    base_start = now - timedelta(days=3)
    days = 3
    measurements_per_day = 5

    spec_low = -150
    spec_high = 150

    for tool_id in tools:
        stage_subsys_id = subsys_map[(tool_id, "STAGE")]

        for day_offset in range(days):
            day_start = base_start + timedelta(days=day_offset)

            for i in range(measurements_per_day):
                ts = day_start + timedelta(hours=i * 4)  # every ~4 hours

                # Default: in-spec values for X & Y
                x_value = random.uniform(-120, 120)
                y_value = random.uniform(-120, 120)
                x_status = "OK"
                y_status = "OK"

                # Special: P2 STAGE has some out-of-spec X with ALERT
                if tool_id == "8950XR-P2":
                    # ~30% chance this X measurement is out-of-spec
                    if random.random() < 0.3:
                        x_value = random.uniform(160, 190)
                        x_status = "ALERT"

                # Insert STAGE_POS_X
                cur.execute(
                    """
                    INSERT INTO subsystem_health_metrics(
                        subsystem_id, ts, metric_name, metric_value,
                        spec_low, spec_high, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stage_subsys_id,
                        ts.isoformat(timespec="seconds"),
                        "STAGE_POS_X",
                        x_value,
                        spec_low,
                        spec_high,
                        x_status,
                    ),
                )

                # Insert STAGE_POS_Y
                cur.execute(
                    """
                    INSERT INTO subsystem_health_metrics(
                        subsystem_id, ts, metric_name, metric_value,
                        spec_low, spec_high, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stage_subsys_id,
                        ts.isoformat(timespec="seconds"),
                        "STAGE_POS_Y",
                        y_value,
                        spec_low,
                        spec_high,
                        y_status,
                    ),
                )

    conn.commit()


def main():
    random.seed(RANDOM_SEED)

    # Remove old file to guarantee a clean DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)

    try:
        reset_db(conn)
        dim = seed_dimension_tables(conn)
        seed_inspection_runs(conn, dim)
        seed_calibration_runs(conn, dim)
        seed_subsystem_health_metrics(conn, dim)
    finally:
        conn.close()

    print(f"Fake SQLite database generated at: {DB_PATH}")


if __name__ == "__main__":
    main()