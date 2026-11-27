-- Part 3: PostgreSQL schema.
-- Creates 4 tables (clean/quarantine for batch/stream)

-- Clean Batch 
CREATE TABLE batch_clean (
    ts TIMESTAMP PRIMARY KEY,
    global_active_power DOUBLE PRECISION,
    global_reactive_power DOUBLE PRECISION,
    voltage DOUBLE PRECISION,
    global_intensity DOUBLE PRECISION,
    sub_metering_1 DOUBLE PRECISION,
    sub_metering_2 DOUBLE PRECISION,
    sub_metering_3 DOUBLE PRECISION
);

-- Quarantine Batch
CREATE TABLE batch_quarantine ( -- If in quarantine, missing measurements
    ts TIMESTAMP PRIMARY KEY,
    row_data TEXT 
);

-- Clean Stream
CREATE TABLE stream_clean (
    ts TIMESTAMP PRIMARY KEY,
    global_active_power DOUBLE PRECISION,
    global_reactive_power DOUBLE PRECISION,
    voltage DOUBLE PRECISION,
    global_intensity DOUBLE PRECISION,
    sub_metering_1 DOUBLE PRECISION,
    sub_metering_2 DOUBLE PRECISION,
    sub_metering_3 DOUBLE PRECISION
);

-- Quarantine Stream
CREATE TABLE stream_quarantine (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- Needed as duplicates can cause problems
    ts TIMESTAMP,
    row_data TEXT, 
    duplicate BOOLEAN NOT NULL,
    late BOOLEAN NOT NULL,
    missing BOOLEAN NOT NULL
);