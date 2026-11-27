from serve.db import execute_query, connect

Q1a = """WITH clean_data AS (
    SELECT * FROM batch_clean
),
energy AS (
    SELECT
        SUM(global_active_power * 1000.0 / 60) AS total_wh,
        SUM(sub_metering_1) AS sub1_wh,
        SUM(sub_metering_2) AS sub2_wh,
        SUM(sub_metering_3) AS sub3_wh,
        SUM(
            global_active_power * 1000.0 / 60
            - sub_metering_1
            - sub_metering_2
            - sub_metering_3
        ) AS other_wh
    FROM clean_data
    WHERE global_active_power IS NOT NULL
      AND sub_metering_1 IS NOT NULL
      AND sub_metering_2 IS NOT NULL
      AND sub_metering_3 IS NOT NULL
),
categories AS (
    SELECT 'Kitchen (Sub-meter 1)' AS category, sub1_wh AS wh FROM energy
    UNION ALL
    SELECT 'Laundry (Sub-meter 2)', sub2_wh FROM energy
    UNION ALL
    SELECT 'Water heating / AC (Sub-meter 3)', sub3_wh FROM energy
    UNION ALL
    SELECT 'Other household usage', other_wh FROM energy
)
SELECT
    category,
    ROUND((wh / 1000.0)::numeric, 2) AS energy_kwh,
    ROUND((100.0 * wh / NULLIF(total_wh, 0))::numeric, 2) AS percentage
FROM categories
CROSS JOIN energy
ORDER BY energy_kwh DESC;"""

Q1b = """WITH clean_data AS (
    SELECT * FROM batch_clean
),
seasonal AS (
    SELECT
        CASE
            WHEN EXTRACT(MONTH FROM ts) IN (12, 1, 2) THEN 'Winter'
            WHEN EXTRACT(MONTH FROM ts) IN (3, 4, 5) THEN 'Spring'
            WHEN EXTRACT(MONTH FROM ts) IN (6, 7, 8) THEN 'Summer'
            ELSE 'Fall'
        END AS season,

        COUNT(*) AS minutes_observed,

        SUM(global_active_power * 1000.0 / 60) / 1000.0
            AS total_kwh,

        SUM(global_active_power * 1000.0 / 60)
            / 1000.0
            / (COUNT(*) / 1440.0)
            AS kwh_per_day

    FROM clean_data
    WHERE global_active_power IS NOT NULL
    GROUP BY season
)
SELECT
    season,
    minutes_observed,
    ROUND(total_kwh::numeric, 2) AS total_kwh,
    ROUND(kwh_per_day::numeric, 2) AS kwh_per_day
FROM seasonal
ORDER BY
    CASE season
        WHEN 'Winter' THEN 1
        WHEN 'Spring' THEN 2
        WHEN 'Summer' THEN 3
        WHEN 'Fall' THEN 4
    END;"""

Q1c = """WITH clean_data AS (
    SELECT * FROM batch_clean
)
SELECT
    TO_CHAR(DATE_TRUNC('month', ts), 'YYYY-MM') AS month,

    COUNT(*) AS minutes_observed,

    ROUND(
        (SUM(global_active_power) / 60.0)::numeric,
        2
    ) AS total_kwh,

    ROUND(
        (
            SUM(global_active_power) / 60.0
            / (COUNT(*) / 1440.0)
        )::numeric,
        2
    ) AS kwh_per_day

FROM clean_data
WHERE global_active_power IS NOT NULL
GROUP BY DATE_TRUNC('month', ts)
ORDER BY DATE_TRUNC('month', ts);"""

Q2 = """WITH clean_data AS (
    SELECT * FROM batch_clean
)
SELECT
    EXTRACT(HOUR FROM ts)::INTEGER AS hour,

    COUNT(*) AS minutes_observed,

    ROUND(AVG(global_active_power)::numeric, 3)
        AS avg_active_power_kw,

    ROUND(AVG(sub_metering_1)::numeric, 3)
        AS sub_meter_1_avg_wh_per_min,

    ROUND(AVG(sub_metering_2)::numeric, 3)
        AS sub_meter_2_avg_wh_per_min,

    ROUND(AVG(sub_metering_3)::numeric, 3)
        AS sub_meter_3_avg_wh_per_min

FROM clean_data
WHERE global_active_power IS NOT NULL
GROUP BY EXTRACT(HOUR FROM ts)
ORDER BY avg_active_power_kw DESC;"""

Q3a = """WITH clean_data AS (
    SELECT * FROM batch_clean
),
hourly AS (
    SELECT
        DATE_TRUNC('hour', ts) AS hour_start,

        SUM(global_active_power) AS p,
        SUM(global_reactive_power) AS q,

        AVG(global_active_power) AS avg_active_kw,

        COUNT(*) AS minutes_observed

    FROM clean_data
    WHERE global_active_power IS NOT NULL
      AND global_reactive_power IS NOT NULL
    GROUP BY DATE_TRUNC('hour', ts)
),
power_factor AS (
    SELECT
        hour_start,
        avg_active_kw,
        minutes_observed,

        p / NULLIF(
            SQRT(POWER(p, 2) + POWER(q, 2)),
            0
        ) AS pf

    FROM hourly
)
SELECT
    COUNT(*) AS hours_observed,

    ROUND(AVG(pf)::numeric, 4) AS avg_power_factor,

    ROUND(MIN(pf)::numeric, 4) AS min_power_factor,

    COUNT(*) FILTER (
        WHERE pf < 0.95
    ) AS hours_below_threshold,

    ROUND(
        (
            100.0 * COUNT(*) FILTER (WHERE pf < 0.95)
            / NULLIF(COUNT(*), 0)
        )::numeric,
        2
    ) AS percentage_hours_below_threshold

FROM power_factor;"""

Q3b = """WITH clean_data AS (
    SELECT * FROM batch_clean
),
hourly AS (
    SELECT
        DATE_TRUNC('hour', ts) AS hour_start,

        SUM(global_active_power) AS p,
        SUM(global_reactive_power) AS q,

        AVG(global_active_power) AS avg_active_kw,

        COUNT(*) AS minutes_observed

    FROM clean_data
    WHERE global_active_power IS NOT NULL
      AND global_reactive_power IS NOT NULL
    GROUP BY DATE_TRUNC('hour', ts)
),
power_factor AS (
    SELECT
        hour_start,
        avg_active_kw,
        minutes_observed,

        p / NULLIF(
            SQRT(POWER(p, 2) + POWER(q, 2)),
            0
        ) AS pf

    FROM hourly
),
flagged AS (
    SELECT
        hour_start,
        avg_active_kw,
        minutes_observed,
        pf,

        EXTRACT(EPOCH FROM hour_start) / 3600 AS hour_index

    FROM power_factor
    WHERE pf < 0.95
),
numbered AS (
    SELECT
        *,

        hour_index - ROW_NUMBER() OVER (
            ORDER BY hour_index
        ) AS grp

    FROM flagged
),
runs AS (
    SELECT
        MIN(hour_start) AS run_start,

        MAX(hour_start) AS run_last_hour,

        COUNT(*) AS consecutive_hours,

        AVG(pf) AS avg_power_factor,

        MIN(pf) AS min_power_factor,

        AVG(avg_active_kw) AS avg_active_kw

    FROM numbered
    GROUP BY grp
    HAVING COUNT(*) >= 2
)
SELECT
    run_start,
    run_last_hour,
    consecutive_hours,

    ROUND(avg_power_factor::numeric, 4)
        AS avg_power_factor,

    ROUND(min_power_factor::numeric, 4)
        AS min_power_factor,

    ROUND(avg_active_kw::numeric, 3)
        AS avg_active_power_kw

FROM runs
ORDER BY consecutive_hours DESC, run_start
LIMIT 20;"""

from decimal import Decimal
from datetime import datetime

def run_analysis_queries(conn):
    queries = {
        "Q1a": {
            "sql": Q1a,
            "headers": ["Category", "Energy (kWh)", "Percentage (%)"],
            "formats": ["text", "2f", "2f"]
        },
        "Q1b": {
            "sql": Q1b,
            "headers": ["Season", "Minutes Observed", "Total (kWh)", "Daily Average (kWh)"],
            "formats": ["text", "int", "2f", "2f"]
        },
        "Q1c": {
            "sql": Q1c,
            "headers": ["Month", "Minutes Observed", "Total (kWh)", "Daily Average (kWh)"],
            "formats": ["text", "int", "2f", "2f"]
        },
        "Q2": {
            "sql": Q2,
            "headers": [
                "Hour",
                "Minutes Observed",
                "Active Power (kW)",
                "Sub-meter 1 (Wh/min)",
                "Sub-meter 2 (Wh/min)",
                "Sub-meter 3 (Wh/min)"
            ],
            "formats": ["int", "int", "3f", "3f", "3f", "3f"]
        },
        "Q3a": {
            "sql": Q3a,
            "headers": [
                "Hours Observed",
                "Average PF",
                "Minimum PF",
                "Hours Below 0.95",
                "Percentage Below (%)"
            ],
            "formats": ["int", "4f", "4f", "int", "2f"]
        },
        "Q3b": {
            "sql": Q3b,
            "headers": [
                "Start",
                "End",
                "Duration (hours)",
                "Average PF",
                "Minimum PF",
                "Average Power (kW)"
            ],
            "formats": ["datetime", "datetime", "int", "4f", "4f", "3f"]
        }
    }

    def format_value(value, fmt):
        if value is None:
            return "N/A"

        if fmt == "text":
            return str(value)

        if fmt == "datetime":
            return value.strftime("%Y-%m-%d %H:%M")

        if fmt == "int":
            return str(int(value))

        if fmt == "2f":
            return f"{float(value):.2f}"

        if fmt == "3f":
            return f"{float(value):.3f}"

        if fmt == "4f":
            return f"{float(value):.4f}"

        return str(value)

    for name, config in queries.items():
        print(f"\n{'=' * 100}")
        print(f"{name}")
        print("=" * 100)

        results, elapsed = execute_query(conn, config["sql"])

        headers = config["headers"]
        formats = config["formats"]

        rows = [
            [
                format_value(value, fmt)
                for value, fmt in zip(row, formats)
            ]
            for row in results
        ]

        # Calculate column widths
        widths = [
            max(
                len(header),
                max((len(row[i]) for row in rows), default=0)
            )
            for i, header in enumerate(headers)
        ]

        # Print headers
        header_line = " | ".join(
            header.ljust(widths[i])
            for i, header in enumerate(headers)
        )

        print(header_line)
        print("-" * len(header_line))

        # Print results
        for row in rows:
            print(
                " | ".join(
                    value.ljust(widths[i])
                    for i, value in enumerate(row)
                )
            )

        print(f"\nRows returned: {len(results)}")
        print(f"Execution time: {elapsed:.4f} seconds")

conn = connect()

try:
    run_analysis_queries(conn)
finally:
    conn.close()
