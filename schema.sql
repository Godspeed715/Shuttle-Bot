-- ============================================================
-- Campus Shuttle Management System — Database Schema
-- Target: Neon PostgreSQL (serverless free tier)
-- ============================================================

-- 1. USERS
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL          PRIMARY KEY,
    telegram_id     BIGINT          UNIQUE NOT NULL,
    username        VARCHAR(255),
    full_name       VARCHAR(255)    NOT NULL,
    role            VARCHAR(20)     NOT NULL CHECK (role IN ('student', 'driver')),
    is_approved     BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- 2. USER STATES (replaces in-memory FSM — survives serverless restarts)
CREATE TABLE IF NOT EXISTS user_states (
    telegram_id     BIGINT          PRIMARY KEY,
    state           VARCHAR(100)    NOT NULL,
    data            JSONB           NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- 3. LOCATIONS
CREATE TABLE IF NOT EXISTS locations (
    id              SERIAL          PRIMARY KEY,
    name            VARCHAR(255)    NOT NULL,
    code            VARCHAR(50)     UNIQUE NOT NULL,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE
);

-- 4. SHUTTLES
CREATE TABLE IF NOT EXISTS shuttles (
    id                  SERIAL          PRIMARY KEY,
    driver_id           INTEGER         NOT NULL UNIQUE
                                        REFERENCES users(id) ON DELETE CASCADE,
    name                VARCHAR(255)    NOT NULL,
    is_available        BOOLEAN         NOT NULL DEFAULT FALSE,
    current_location_id INTEGER         REFERENCES locations(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shuttles_available
    ON shuttles (is_available) WHERE is_available = TRUE;

-- 5. RIDE REQUESTS
CREATE TABLE IF NOT EXISTS ride_requests (
    id              SERIAL          PRIMARY KEY,
    booking_id      VARCHAR(20)     UNIQUE NOT NULL,
    student_id      INTEGER         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    driver_id       INTEGER         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shuttle_id      INTEGER         NOT NULL REFERENCES shuttles(id) ON DELETE CASCADE,
    pickup_id       INTEGER         NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_id  INTEGER         NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','accepted','rejected','expired','cancelled','completed')),
    driver_msg_id   BIGINT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ     NOT NULL,
    responded_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ride_active_student
    ON ride_requests (student_id) WHERE status IN ('pending','accepted');
CREATE INDEX IF NOT EXISTS idx_ride_active_driver
    ON ride_requests (driver_id) WHERE status IN ('pending','accepted');
CREATE INDEX IF NOT EXISTS idx_ride_expiry
    ON ride_requests (expires_at) WHERE status = 'pending';

-- 6. DRIVER REQUESTS (pending admin approval)
CREATE TABLE IF NOT EXISTS driver_requests (
    id              SERIAL          PRIMARY KEY,
    telegram_id     BIGINT          NOT NULL,
    username        VARCHAR(255),
    full_name       VARCHAR(255)    NOT NULL,
    shuttle_name    VARCHAR(255)    NOT NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected')),
    admin_msg_id    BIGINT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ
);

-- ============================================================
-- SEED DATA — Campus Locations
-- ============================================================
INSERT INTO locations (code, name) VALUES
    ('daniel',  'Daniel Hall'),
    ('joseph',  'Joseph Hall'),
    ('john',    'John Hall'),
    ('peter',   'Peter Hall'),
    ('paul',    'Paul Hall'),
    ('esther',  'Esther Hall'),
    ('mary',    'Mary Hall'),
    ('deborah', 'Deborah Hall'),
    ('lydia',   'Lydia Hall'),
    ('dorcas',  'Dorcas Hall'),
    ('cst',     'CST'),
    ('cmss',    'CMSS'),
    ('lt',      'Lecture Theatre (LT)'),
    ('eng',     'Engineering Block')
ON CONFLICT (code) DO NOTHING;
