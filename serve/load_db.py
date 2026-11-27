"""Part 3a:

 load the Spark batch results and the ingest quarantine into PostgreSQL.

"""
import json
import pyarrow.dataset as ds
from psycopg import sql

from serve.db import connect

CLEAN = "data/parquet/power"
QUARANTINE = "data/quarantine/ingest"

def load_batch_clean(conn):
    data = ds.dataset(CLEAN, format="parquet").to_table()

    columns = [
        "ts",
        "global_active_power",
        "global_reactive_power",
        "voltage",
        "global_intensity",
        "sub_metering_1",
        "sub_metering_2",
        "sub_metering_3",
    ]

    copy_sql = sql.SQL(
        "COPY batch_clean ({}) FROM STDIN"
    ).format(
        sql.SQL(", ").join(map(sql.Identifier, columns))
    )

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE batch_clean") # Empties table

        with cur.copy(copy_sql) as copy:
            for batch in data.select(columns).to_batches():
                for row in zip(*(col.to_pylist() for col in batch.columns)):
                    copy.write_row(row)

        rows_out = cur.execute(
            "SELECT COUNT(*) FROM batch_clean"
        ).fetchone()[0]

    return data.num_rows, rows_out # Number of rows in parquet, number of rows in DB


def load_batch_quarantine(conn):
    data = ds.dataset(QUARANTINE, format="parquet").to_table()

    # Keep the original rejected row as JSON text.
    rows = [
        (
            str(row.get("ts")) if row.get("ts") is not None else None,
            json.dumps(row, default=str),
        )
        for row in data.to_pylist()
    ]

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE batch_quarantine")

        cur.executemany(
            """
            INSERT INTO batch_quarantine (ts, row_data)
            VALUES (%s, %s)
            """,
            rows,
        )

        rows_out = cur.execute(
            "SELECT COUNT(*) FROM batch_quarantine"
        ).fetchone()[0]

    return data.num_rows, rows_out


def load_stream(conn, clean_rows=None, quarantine_rows=None):
    """Insert new clean and quarantined stream messages into PostgreSQL."""

    clean_rows = clean_rows or []
    quarantine_rows = quarantine_rows or []

    with conn.transaction(), conn.cursor() as cur:

        # Insert clean measurements
        if clean_rows:
            cur.executemany(
                """
                INSERT INTO stream_clean (
                    ts,
                    global_active_power,
                    global_reactive_power,
                    voltage,
                    global_intensity,
                    sub_metering_1,
                    sub_metering_2,
                    sub_metering_3
                )
                VALUES (
                    %(ts)s,
                    %(global_active_power)s,
                    %(global_reactive_power)s,
                    %(voltage)s,
                    %(global_intensity)s,
                    %(sub_metering_1)s,
                    %(sub_metering_2)s,
                    %(sub_metering_3)s
                )
                """,
                clean_rows
            )

        # Insert quarantined measurements
        if quarantine_rows:
            cur.executemany(
                """
                INSERT INTO stream_quarantine (
                    ts,
                    row_data,
                    duplicate,
                    late,
                    missing
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                quarantine_rows
            )

    return len(clean_rows), len(quarantine_rows)



def main():
    print("\n=== Loading batch data into PostgreSQL ===")

    with connect() as conn:
        for name, load_function in [
            ("Clean", load_batch_clean),
            ("Quarantine", load_batch_quarantine),
        ]:
            rows_in, rows_out = load_function(conn)

            print(f"\n{name}:")
            print(f"Rows in:  {rows_in:,}")
            print(f"Rows out: {rows_out:,}")
            print(f"Match:    {rows_in == rows_out}")

            if rows_in != rows_out:
                raise RuntimeError(f"{name} row count mismatch!")


if __name__ == "__main__":
    main()