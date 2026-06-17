"""
Database helper — all SQL queries in one place.
Each function takes a psycopg2 connection (with autocommit + RealDictCursor).
"""
import json


# ───────────────────────── State Management ─────────────────────────

def get_state(conn, telegram_id):
    """Get a user's conversation state. Returns dict or None."""
    with conn.cursor() as cur:
        cur.execute('SELECT state, data FROM user_states WHERE telegram_id = %s', (telegram_id,))
        row = cur.fetchone()
    if row and isinstance(row['data'], str):
        row['data'] = json.loads(row['data'])
    return row


def set_state(conn, telegram_id, state, data=None):
    """Save or update a user's conversation state."""
    with conn.cursor() as cur:
        cur.execute('''
            INSERT INTO user_states (telegram_id, state, data)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data, updated_at = NOW()
        ''', (telegram_id, state, json.dumps(data or {})))


def clear_state(conn, telegram_id):
    """Remove a user's conversation state."""
    with conn.cursor() as cur:
        cur.execute('DELETE FROM user_states WHERE telegram_id = %s', (telegram_id,))


# ───────────────────────── Users ─────────────────────────

def get_user(conn, telegram_id):
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM users WHERE telegram_id = %s', (telegram_id,))
        return cur.fetchone()


def create_user(conn, telegram_id, username, full_name, role, is_approved=True):
    with conn.cursor() as cur:
        cur.execute('''
            INSERT INTO users (telegram_id, username, full_name, role, is_approved)
            VALUES (%s, %s, %s, %s, %s) RETURNING *
        ''', (telegram_id, username, full_name, role, is_approved))
        return cur.fetchone()


# ───────────────────────── Locations ─────────────────────────

def get_locations(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM locations WHERE is_active = TRUE ORDER BY name')
        return cur.fetchall()


def get_location(conn, location_id):
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM locations WHERE id = %s', (location_id,))
        return cur.fetchone()


# ───────────────────────── Shuttles ─────────────────────────

def create_shuttle(conn, driver_id, name):
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO shuttles (driver_id, name) VALUES (%s, %s) RETURNING *',
            (driver_id, name),
        )
        return cur.fetchone()


def get_shuttle_by_driver(conn, driver_id):
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM shuttles WHERE driver_id = %s', (driver_id,))
        return cur.fetchone()


def set_shuttle_availability(conn, shuttle_id, is_available):
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE shuttles SET is_available = %s WHERE id = %s',
            (is_available, shuttle_id),
        )


def set_shuttle_location(conn, shuttle_id, location_id):
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE shuttles SET current_location_id = %s WHERE id = %s',
            (location_id, shuttle_id),
        )


def get_available_shuttles(conn):
    """Shuttles that are online AND whose driver has no active ride."""
    with conn.cursor() as cur:
        cur.execute('''
            SELECT s.id, s.name, s.driver_id,
                   u.full_name AS driver_name, u.telegram_id AS driver_telegram_id
            FROM shuttles s
            JOIN users u ON u.id = s.driver_id
            WHERE s.is_available = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM ride_requests r
                  WHERE r.driver_id = s.driver_id AND r.status IN ('pending','accepted')
              )
            ORDER BY s.name
        ''')
        return cur.fetchall()


# ───────────────────────── Ride Requests ─────────────────────────

def create_ride(conn, booking_id, student_id, driver_id, shuttle_id,
                pickup_id, dest_id, expires_at):
    with conn.cursor() as cur:
        cur.execute('''
            INSERT INTO ride_requests
                (booking_id, student_id, driver_id, shuttle_id,
                 pickup_id, destination_id, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *
        ''', (booking_id, student_id, driver_id, shuttle_id,
              pickup_id, dest_id, expires_at))
        return cur.fetchone()


def get_active_ride_for_student(conn, student_id):
    """Student's current pending or accepted ride (with joined names)."""
    with conn.cursor() as cur:
        cur.execute('''
            SELECT r.*, pl.name AS pickup_name, dl.name AS dest_name,
                   u.full_name AS driver_name, s.name AS shuttle_name,
                   u.telegram_id AS driver_telegram_id
            FROM ride_requests r
            JOIN locations pl ON pl.id = r.pickup_id
            JOIN locations dl ON dl.id = r.destination_id
            JOIN users u      ON u.id  = r.driver_id
            JOIN shuttles s   ON s.id  = r.shuttle_id
            WHERE r.student_id = %s AND r.status IN ('pending','accepted')
        ''', (student_id,))
        return cur.fetchone()


def get_active_ride_for_driver(conn, driver_id):
    """Driver's current pending or accepted ride (with joined names)."""
    with conn.cursor() as cur:
        cur.execute('''
            SELECT r.*, pl.name AS pickup_name, dl.name AS dest_name,
                   u.full_name AS student_name, u.telegram_id AS student_telegram_id
            FROM ride_requests r
            JOIN locations pl ON pl.id = r.pickup_id
            JOIN locations dl ON dl.id = r.destination_id
            JOIN users u      ON u.id  = r.student_id
            WHERE r.driver_id = %s AND r.status IN ('pending','accepted')
        ''', (driver_id,))
        return cur.fetchone()


def get_ride(conn, ride_id):
    """Full ride details with all joined names."""
    with conn.cursor() as cur:
        cur.execute('''
            SELECT r.*,
                   pl.name AS pickup_name, dl.name AS dest_name,
                   su.full_name AS student_name, su.telegram_id AS student_telegram_id,
                   du.full_name AS driver_name,  du.telegram_id AS driver_telegram_id,
                   sh.name AS shuttle_name
            FROM ride_requests r
            JOIN locations pl ON pl.id = r.pickup_id
            JOIN locations dl ON dl.id = r.destination_id
            JOIN users su    ON su.id = r.student_id
            JOIN users du    ON du.id = r.driver_id
            JOIN shuttles sh ON sh.id = r.shuttle_id
            WHERE r.id = %s
        ''', (ride_id,))
        return cur.fetchone()


def update_ride_status(conn, ride_id, status):
    with conn.cursor() as cur:
        if status in ('accepted', 'rejected'):
            cur.execute(
                "UPDATE ride_requests SET status=%s, responded_at=NOW() WHERE id=%s RETURNING *",
                (status, ride_id),
            )
        else:
            cur.execute(
                "UPDATE ride_requests SET status=%s WHERE id=%s RETURNING *",
                (status, ride_id),
            )
        return cur.fetchone()


def save_driver_msg_id(conn, ride_id, msg_id):
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE ride_requests SET driver_msg_id = %s WHERE id = %s',
            (msg_id, ride_id),
        )


def expire_old_requests(conn):
    """Atomically expire all overdue pending rides. Returns list with joined names."""
    with conn.cursor() as cur:
        cur.execute('''
            UPDATE ride_requests SET status='expired', responded_at=NOW()
            WHERE status='pending' AND expires_at <= NOW()
            RETURNING id
        ''')
        expired = cur.fetchall()
    if not expired:
        return []
    ids = [r['id'] for r in expired]
    with conn.cursor() as cur:
        cur.execute('''
            SELECT r.*, pl.name AS pickup_name, dl.name AS dest_name,
                   su.full_name AS student_name, su.telegram_id AS student_telegram_id,
                   du.full_name AS driver_name,  du.telegram_id AS driver_telegram_id
            FROM ride_requests r
            JOIN locations pl ON pl.id = r.pickup_id
            JOIN locations dl ON dl.id = r.destination_id
            JOIN users su    ON su.id = r.student_id
            JOIN users du    ON du.id = r.driver_id
            WHERE r.id = ANY(%s)
        ''', (ids,))
        return cur.fetchall()


# ───────────────────────── Driver Registration Requests ─────────────────────────

def create_driver_request(conn, telegram_id, username, full_name, shuttle_name):
    with conn.cursor() as cur:
        cur.execute('''
            INSERT INTO driver_requests (telegram_id, username, full_name, shuttle_name)
            VALUES (%s, %s, %s, %s) RETURNING *
        ''', (telegram_id, username, full_name, shuttle_name))
        return cur.fetchone()


def get_pending_driver_request(conn, telegram_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM driver_requests WHERE telegram_id=%s AND status='pending'",
            (telegram_id,),
        )
        return cur.fetchone()


def get_driver_request(conn, req_id):
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM driver_requests WHERE id = %s', (req_id,))
        return cur.fetchone()


def update_driver_request_status(conn, req_id, status):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE driver_requests SET status=%s, reviewed_at=NOW() WHERE id=%s RETURNING *",
            (status, req_id),
        )
        return cur.fetchone()
