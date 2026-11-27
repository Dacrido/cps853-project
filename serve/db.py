"""Parts 3: 
PostgreSQL database for batch loader, stream consumer, queries and reports

Connection settings come from the standard libpq environment variables (PGHOST, PGPORT,
PGDATABASE, PGUSER, PGPASSWORD), which docker-compose.yml sets for each service.
The tables are created by serve/schema.sql when the database is first started.
"""

import os
import json
import time

import psycopg
from psycopg.types.json import Jsonb # Needed for PostgreSQL

# Connection to PostgreSQL database
def connect():
    """Connect to PostgreSQL"""

    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "power_consumption"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        options="-c TimeZone=UTC"
    )

# Initialize the databse (schema)
def initialize_db(conn):
    """Create tables using schema.sql"""

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    with conn.transaction():
        conn.execute(schema)
    print("Database schema initialized.")

# Sets up measurements for database input
MEASUREMENT_COLUMNS = (
    "ts",
    "global_active_power",           # kW (minute average)
    "global_reactive_power",         # kW (minute average)
    "voltage",                       # V
    "global_intensity",              # A
    "sub_metering_1",                # Wh in the minute (kitchen)
    "sub_metering_2",                # Wh in the minute (laundry)
    "sub_metering_3",                # Wh in the minute (water heater + A/C)
)

MEASUREMENT_VALUES = ", ".join( # %(ts)s, %(voltage)s, %(global_active_power)s ...
    f"%({column})s" for column in MEASUREMENT_COLUMNS # For inserting values
)

MEASUREMENT_INSERT = ", ".join(MEASUREMENT_COLUMNS) # ts, voltage, global_active_power

# Insert rows into clean tables
def insert_clean(conn, table, rows):
    allowed = {"batch_clean", "stream_clean"}

    if table not in allowed:
        raise ValueError("Invalid clean table")
    if not rows:
        return

    sql = f"""
        INSERT INTO {table} ({MEASUREMENT_INSERT})
        VALUES ({MEASUREMENT_VALUES})
    """

    with conn.transaction():
        conn.executemany(sql, rows)

# Insert rejected batch rows
def insert_batch_quarantine(conn, rows):
    if not rows:
        return

    with conn.transaction():
        conn.executemany(
            """
            INSERT INTO batch_quarantine (ts, row_data)
            VALUES (%s, %s)
            """,
            rows
        )

# Insert rejected stream rows
def insert_stream_quarantine(conn, rows):

    if not rows:
        return

    with conn.transaction():
        conn.executemany(
            """
            INSERT INTO stream_quarantine
                (ts, row_data, duplicate, late, missing)
            VALUES (%s, %s, %s, %s, %s)
            """,
            rows
        )

# Execute queries (SELECT)
def execute_query(conn, sql, params=None):
    start = time.perf_counter()
    result = conn.execute(sql, params or ()).fetchall()
    elapsed = time.perf_counter() - start
    return result, elapsed
