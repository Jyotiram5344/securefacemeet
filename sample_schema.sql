-- SecureFaceMeet — PostgreSQL sample schema (SQLAlchemy can also create tables via init_db)
-- Run: psql -U secureface -d securefacemeet -f sample_schema.sql

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255),
    full_name VARCHAR(255) NOT NULL,
    face_embedding_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS meetings (
    id SERIAL PRIMARY KEY,
    room_id VARCHAR(128) NOT NULL UNIQUE,
    title VARCHAR(512) NOT NULL DEFAULT '',
    host_user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_meetings_room_id ON meetings (room_id);

CREATE TABLE IF NOT EXISTS presence_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    meeting_id VARCHAR(128) NOT NULL,
    verification_type VARCHAR(32) NOT NULL,
    result VARCHAR(16) NOT NULL,
    similarity_score FLOAT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_presence_logs_user_id ON presence_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_presence_logs_meeting_id ON presence_logs (meeting_id);

CREATE TABLE IF NOT EXISTS attendance_states (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    meeting_id VARCHAR(128) NOT NULL,
    attendance_score INTEGER NOT NULL DEFAULT 100,
    warning_count INTEGER NOT NULL DEFAULT 0,
    final_status VARCHAR(32) NOT NULL DEFAULT 'good',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_attendance_user_meeting UNIQUE (user_id, meeting_id)
);

CREATE INDEX IF NOT EXISTS ix_attendance_states_user_id ON attendance_states (user_id);
CREATE INDEX IF NOT EXISTS ix_attendance_states_meeting_id ON attendance_states (meeting_id);
