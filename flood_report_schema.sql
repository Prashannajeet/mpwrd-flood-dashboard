-- MP WRD Flood Season report database schema
-- Designed for 08:00, 12:00, 16:00, and 20:00 daily reports.

CREATE TABLE flood_reports (
    report_id BIGSERIAL PRIMARY KEY,
    report_date DATE NOT NULL,
    report_time TIME NOT NULL,
    season_year INTEGER NOT NULL,
    department TEXT DEFAULT 'Water Resources Department, Govt. of Madhya Pradesh',
    letter_no TEXT,
    source_filename TEXT NOT NULL,
    source_file_hash TEXT,
    extraction_method TEXT NOT NULL CHECK (extraction_method IN ('embedded_text', 'ocr', 'manual')),
    extraction_status TEXT NOT NULL DEFAULT 'parsed'
        CHECK (extraction_status IN ('uploaded', 'parsed', 'review_required', 'approved', 'rejected')),
    uploaded_by TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT now(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    UNIQUE (report_date, report_time)
);

CREATE TABLE river_gauge_stations (
    river_station_id BIGSERIAL PRIMARY KEY,
    river_name TEXT NOT NULL,
    gauge_station TEXT NOT NULL,
    district TEXT NOT NULL,
    danger_or_max_water_level_m NUMERIC(10,3),
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE (river_name, gauge_station, district)
);

CREATE TABLE river_water_level_observations (
    river_observation_id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES flood_reports(report_id) ON DELETE CASCADE,
    river_station_id BIGINT NOT NULL REFERENCES river_gauge_stations(river_station_id),
    observed_at TIMESTAMPTZ NOT NULL,
    water_level_m NUMERIC(10,3),
    level_status TEXT,
    source_row_no INTEGER,
    confidence NUMERIC(5,2),
    UNIQUE (river_station_id, observed_at)
);

CREATE TABLE reservoirs (
    reservoir_id BIGSERIAL PRIMARY KEY,
    reservoir_name TEXT NOT NULL,
    district TEXT NOT NULL,
    lsl_m NUMERIC(10,3),
    frl_m NUMERIC(10,3),
    live_capacity_frl_mcm NUMERIC(14,3),
    total_no_of_gates INTEGER,
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    dam_registry_code TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE (reservoir_name, district)
);

CREATE TABLE reservoir_status_observations (
    reservoir_status_id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES flood_reports(report_id) ON DELETE CASCADE,
    reservoir_id BIGINT NOT NULL REFERENCES reservoirs(reservoir_id),
    observed_at TIMESTAMPTZ NOT NULL,
    water_level_m NUMERIC(10,3),
    current_live_capacity_mcm NUMERIC(14,3),
    filling_percent NUMERIC(8,3),
    rainfall_daily_mm NUMERIC(10,2),
    rainfall_total_mm NUMERIC(10,2),
    source_row_no INTEGER,
    confidence NUMERIC(5,2),
    UNIQUE (reservoir_id, observed_at)
);

CREATE TABLE reservoir_gate_observations (
    gate_observation_id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES flood_reports(report_id) ON DELETE CASCADE,
    reservoir_id BIGINT NOT NULL REFERENCES reservoirs(reservoir_id),
    gate_opened_count INTEGER,
    opening_m NUMERIC(10,3),
    gate_opening_date DATE,
    gate_opening_time TIME,
    discharge_cumecs NUMERIC(14,3),
    discharge_cusec NUMERIC(14,3),
    source_row_no INTEGER,
    confidence NUMERIC(5,2),
    UNIQUE (report_id, reservoir_id)
);

CREATE TABLE flood_report_extraction_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    report_id BIGINT REFERENCES flood_reports(report_id) ON DELETE CASCADE,
    table_name TEXT NOT NULL,
    source_page INTEGER,
    raw_row_text TEXT,
    parsed_json JSONB,
    warnings TEXT[],
    confidence NUMERIC(5,2),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ai_river_flow_forecasts (
    forecast_id TEXT PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    river_name TEXT,
    gauge_station TEXT,
    district TEXT,
    basin TEXT,
    observed_at TIMESTAMPTZ,
    forecast_time TIMESTAMPTZ,
    lead_day INTEGER,
    water_level_m NUMERIC(10,3),
    danger_gap_m NUMERIC(10,3),
    wl_delta_m NUMERIC(10,3),
    glofas_flow_cms NUMERIC(14,3),
    grrr_flow_cms NUMERIC(14,3),
    predicted_discharge_cumecs NUMERIC(14,3),
    watch_cms NUMERIC(14,3),
    flood_cms NUMERIC(14,3),
    danger_cms NUMERIC(14,3),
    risk_band TEXT,
    source_model TEXT,
    prediction_confidence NUMERIC(6,3),
    model_status TEXT,
    synced_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_river_obs_observed_at ON river_water_level_observations(observed_at);
CREATE INDEX idx_reservoir_status_observed_at ON reservoir_status_observations(observed_at);
CREATE INDEX idx_reservoir_status_reservoir_time ON reservoir_status_observations(reservoir_id, observed_at);
CREATE INDEX idx_gate_obs_report ON reservoir_gate_observations(report_id);
CREATE INDEX idx_ai_river_flow_gauge_time ON ai_river_flow_forecasts(gauge_station, forecast_time);
CREATE INDEX idx_ai_river_flow_risk ON ai_river_flow_forecasts(risk_band, forecast_time);
