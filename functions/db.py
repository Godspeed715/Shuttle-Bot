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

def create_shuttle(conn, driver_id, name, vehicle_type='car'):
    """Create a shuttle record linked to a driver."""
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO shuttles (driver_id, name, vehicle_type) '
            'VALUES (%s, %s, %s) RETURNING *',
            (driver_id, name, vehicle_type),
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

def create_driver_request(conn, telegram_id, username, full_name,
                          shuttle_name, vehicle_type='car'):
    """Create a pending driver registration request awaiting admin approval."""
    with conn.cursor() as cur:
        cur.execute('''
            INSERT INTO driver_requests
                (telegram_id, username, full_name, shuttle_name, vehicle_type)
            VALUES (%s, %s, %s, %s, %s) RETURNING *
        ''', (telegram_id, username, full_name, shuttle_name, vehicle_type))
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


# ───────────────────────── Route Prices ─────────────────────────

def get_route_price(conn, pickup_id: int, dest_id: int):
    """
    Return the route_prices row for a route pair, or None.

    LEAST/GREATEST normalises direction so A->B and B->A always hit the
    same row. The table stores loc_a_id < loc_b_id by convention.

    Args:
        conn:       psycopg2 connection (RealDictCursor).
        pickup_id:  locations.id of one endpoint.
        dest_id:    locations.id of the other endpoint.

    Returns:
        RealDictRow or None.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT * FROM route_prices '
            'WHERE loc_a_id = LEAST(%s, %s) AND loc_b_id = GREATEST(%s, %s)',
            (pickup_id, dest_id, pickup_id, dest_id),
        )
        return cur.fetchone()


def get_all_route_prices(conn) -> list:
    """
    Return all route_prices rows joined with human-readable location names.

    Each returned row contains:
        id, loc_a_id, loc_b_id, loc_a_name, loc_b_name, price

    Returns:
        List of RealDictRows ordered by loc_a_name then loc_b_name.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT rp.id, rp.loc_a_id, rp.loc_b_id, '
            'la.name AS loc_a_name, lb.name AS loc_b_name, rp.price '
            'FROM route_prices rp '
            'JOIN locations la ON la.id = rp.loc_a_id '
            'JOIN locations lb ON lb.id = rp.loc_b_id '
            'ORDER BY la.name, lb.name'
        )
        return cur.fetchall()


def set_route_price(conn, pickup_id: int, dest_id: int, price: int):
    """
    Upsert the per-passenger price for a route.

    Always stores loc_a_id = LEAST(pickup_id, dest_id) and
    loc_b_id = GREATEST(pickup_id, dest_id) to keep the unique constraint
    (loc_a_id, loc_b_id) consistent regardless of call direction.

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        pickup_id: locations.id of one endpoint.
        dest_id:   locations.id of the other endpoint.
        price:     Per-passenger fare in Naira.

    Returns:
        The upserted RealDictRow.
    """
    # Compute outside the query to avoid embedding calls inside SQL strings
    loc_a = min(pickup_id, dest_id)
    loc_b = max(pickup_id, dest_id)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO route_prices (loc_a_id, loc_b_id, price) '
            'VALUES (%s, %s, %s) '
            'ON CONFLICT (loc_a_id, loc_b_id) '
            'DO UPDATE SET price = EXCLUDED.price, updated_at = NOW() '
            'RETURNING *',
            (loc_a, loc_b, price),
        )
        return cur.fetchone()


def delete_route_price(conn, price_id: int):
    """
    Delete a route_prices row by primary key.

    Args:
        conn:     psycopg2 connection (RealDictCursor).
        price_id: route_prices.id to remove.
    """
    with conn.cursor() as cur:
        cur.execute('DELETE FROM route_prices WHERE id = %s', (price_id,))


# ───────────────────────── Driver Wallets ─────────────────────────

def get_or_create_wallet(conn, driver_id: int):
    """
    Return the driver wallet row, creating it if it does not yet exist.

    The ON CONFLICT clause bumps updated_at so RETURNING * always returns
    a current snapshot even when the row already existed.

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        driver_id: users.id of the driver.

    Returns:
        RealDictRow for the driver_wallets row.
    """
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO driver_wallets (driver_id) VALUES (%s) '
            'ON CONFLICT (driver_id) DO UPDATE SET updated_at = NOW() '
            'RETURNING *',
            (driver_id,),
        )
        return cur.fetchone()


def get_wallet(conn, driver_id: int):
    """
    Fetch the driver wallet row without creating one.

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        driver_id: users.id of the driver.

    Returns:
        RealDictRow or None if the wallet does not exist.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT * FROM driver_wallets WHERE driver_id = %s',
            (driver_id,),
        )
        return cur.fetchone()


def credit_wallet(conn, driver_id: int, amount: int,
                  ride_id: int = None, reference: str = None, note: str = None):
    """
    Credit the driver wallet for a completed ride payout.

    Steps performed in the same cursor context:
      1. Increase balance and total_earned on driver_wallets.
      2. Insert a wallet_transactions row of type 'ride_payout'.

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        driver_id: users.id of the driver.
        amount:    Positive Naira integer to add.
        ride_id:   Optional ride_requests.id this payout relates to.
        reference: Optional Paystack or internal reference string.
        note:      Optional human-readable note stored on the transaction.
    """
    with conn.cursor() as cur:
        # Update the running balances
        cur.execute(
            'UPDATE driver_wallets '
            'SET balance = balance + %s, total_earned = total_earned + %s, updated_at = NOW() '
            'WHERE driver_id = %s',
            (amount, amount, driver_id),
        )
        # Record the credit transaction
        cur.execute(
            'INSERT INTO wallet_transactions '
            '(driver_id, type, amount, ride_id, reference, note) '
            'VALUES (%s, %s, %s, %s, %s, %s)',
            (driver_id, 'ride_payout', amount, ride_id, reference, note),
        )


def add_commission_debt(conn, driver_id: int, amount: int, ride_id: int = None):
    """
    Record that the driver owes the platform a commission amount.

    Steps:
      1. Increase commission_owed on driver_wallets.
      2. Insert a wallet_transactions row of type 'commission_deduction'
         with a NEGATIVE amount (money owed, not received).

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        driver_id: users.id of the driver.
        amount:    Positive Naira integer representing the new debt.
        ride_id:   Optional ride_requests.id this debt relates to.
    """
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE driver_wallets '
            'SET commission_owed = commission_owed + %s, updated_at = NOW() '
            'WHERE driver_id = %s',
            (amount, driver_id),
        )
        # Store as negative: signals money flowing away from driver
        cur.execute(
            'INSERT INTO wallet_transactions (driver_id, type, amount, ride_id) '
            'VALUES (%s, %s, %s, %s)',
            (driver_id, 'commission_deduction', -amount, ride_id),
        )


def settle_commission_debt(conn, driver_id: int, amount_collected: int):
    """
    Reduce the driver commission_owed after the platform collects cash.

    GREATEST(..., 0) prevents the column from going negative due to any
    rounding differences.

    Args:
        conn:             psycopg2 connection (RealDictCursor).
        driver_id:        users.id of the driver.
        amount_collected: Naira amount the driver physically remitted.
    """
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE driver_wallets '
            'SET commission_owed = GREATEST(commission_owed - %s, 0), updated_at = NOW() '
            'WHERE driver_id = %s',
            (amount_collected, driver_id),
        )
        cur.execute(
            'INSERT INTO wallet_transactions (driver_id, type, amount) '
            'VALUES (%s, %s, %s)',
            (driver_id, 'remittance_settlement', amount_collected),
        )


def debit_wallet_for_withdrawal(conn, driver_id: int, amount: int, reference: str):
    """
    Reduce the wallet balance and log a pending withdrawal transaction.

    Call confirm_withdrawal() once Paystack confirms the transfer outcome.

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        driver_id: users.id of the driver.
        amount:    Positive Naira integer to deduct from balance.
        reference: Unique Paystack transfer reference for this withdrawal.
    """
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE driver_wallets SET balance = balance - %s, updated_at = NOW() '
            'WHERE driver_id = %s',
            (amount, driver_id),
        )
        # Negative amount — money leaving the wallet
        cur.execute(
            'INSERT INTO wallet_transactions (driver_id, type, amount, reference, status) '
            'VALUES (%s, %s, %s, %s, %s)',
            (driver_id, 'withdrawal', -amount, reference, 'pending'),
        )


def confirm_withdrawal(conn, reference: str, status: str):
    """
    Update the status of a withdrawal transaction once Paystack responds.

    Typically called from the Paystack transfer webhook with status
    'success' or 'failed'.

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        reference: Paystack transfer reference
                   (matches wallet_transactions.reference).
        status:    New status string, e.g. 'success' or 'failed'.
    """
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE wallet_transactions '
            'SET status = %s, updated_at = NOW() '
            'WHERE reference = %s',
            (status, reference),
        )


def get_wallet_transactions(conn, driver_id: int, limit: int = 10) -> list:
    """
    Return the most recent wallet_transactions rows for a driver.

    Args:
        conn:      psycopg2 connection (RealDictCursor).
        driver_id: users.id of the driver.
        limit:     Maximum number of rows to return (default 10).

    Returns:
        List of RealDictRows ordered newest-first.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT * FROM wallet_transactions '
            'WHERE driver_id = %s ORDER BY created_at DESC LIMIT %s',
            (driver_id, limit),
        )
        return cur.fetchall()


# ───────────────────────── Bank Details ─────────────────────────

def save_bank_details(conn, driver_id: int, bank_code: str, bank_name: str,
                      account_number: str, account_name: str, recipient_code: str):
    """
    Persist a driver's verified bank account details in the wallet row.

    All five bank fields are updated atomically so the row is never in a
    partially-written state.

    Args:
        conn:           psycopg2 connection (RealDictCursor).
        driver_id:      users.id of the driver.
        bank_code:      Paystack bank code (e.g. '044').
        bank_name:      Human-readable bank name (e.g. 'Access Bank').
        account_number: 10-digit NUBAN number.
        account_name:   Account holder name as returned by Paystack resolve.
        recipient_code: Paystack recipient code from create_transfer_recipient().

    Returns:
        Updated RealDictRow for the driver_wallets row.
    """
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE driver_wallets '
            'SET bank_code = %s, bank_name = %s, account_number = %s, '
            'account_name = %s, recipient_code = %s, updated_at = NOW() '
            'WHERE driver_id = %s RETURNING *',
            (bank_code, bank_name, account_number,
             account_name, recipient_code, driver_id),
        )
        return cur.fetchone()


# ───────────────────────── Remittances ─────────────────────────

def get_drivers_with_debt(conn) -> list:
    """
    Return all drivers who currently have an outstanding commission debt.

    Joins driver_wallets with users to surface name and telegram_id for
    easy admin notification. Ordered by largest debt first.

    Returns:
        List of RealDictRows with all wallet columns plus
        full_name and telegram_id from users.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT dw.*, u.full_name, u.telegram_id '
            'FROM driver_wallets dw '
            'JOIN users u ON u.id = dw.driver_id '
            'WHERE dw.commission_owed > 0 '
            'ORDER BY dw.commission_owed DESC'
        )
        return cur.fetchall()


# ───────────────────────── Ride Payments ─────────────────────────

def update_ride_fare(conn, ride_id: int, passenger_count: int,
                     fare_amount: int, platform_cut: int,
                     driver_earnings: int, payment_method: str):
    """
    Persist the calculated fare details on a ride_requests row.

    Called immediately after the driver confirms the passenger count and
    the fare is computed by pricing.calculate_fare().

    Args:
        conn:            psycopg2 connection (RealDictCursor).
        ride_id:         ride_requests.id to update.
        passenger_count: Number of passengers confirmed by the driver.
        fare_amount:     Total gross fare in Naira.
        platform_cut:    Platform share in Naira.
        driver_earnings: Driver net earnings in Naira.
        payment_method:  'cash' or 'online'.

    Returns:
        Updated RealDictRow.
    """
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE ride_requests '
            'SET passenger_count = %s, fare_amount = %s, platform_cut = %s, '
            'driver_earnings = %s, payment_method = %s, updated_at = NOW() '
            'WHERE id = %s RETURNING *',
            (passenger_count, fare_amount, platform_cut,
             driver_earnings, payment_method, ride_id),
        )
        return cur.fetchone()


def update_ride_payment_status(conn, ride_id: int, status: str,
                                paystack_ref: str = None):
    """
    Update the payment_status of a ride, optionally storing the Paystack ref.

    When paystack_ref is supplied it is persisted alongside the status so
    the webhook handler can later look the ride up by reference alone.

    Args:
        conn:         psycopg2 connection (RealDictCursor).
        ride_id:      ride_requests.id to update.
        status:       New payment status, e.g. 'pending', 'paid', 'failed'.
        paystack_ref: Paystack transaction reference (optional).

    Returns:
        Updated RealDictRow.
    """
    with conn.cursor() as cur:
        if paystack_ref is not None:
            cur.execute(
                'UPDATE ride_requests '
                'SET payment_status = %s, paystack_ref = %s, updated_at = NOW() '
                'WHERE id = %s RETURNING *',
                (status, paystack_ref, ride_id),
            )
        else:
            cur.execute(
                'UPDATE ride_requests '
                'SET payment_status = %s, updated_at = NOW() '
                'WHERE id = %s RETURNING *',
                (status, ride_id),
            )
        return cur.fetchone()


def get_ride_by_paystack_ref(conn, ref: str):
    """
    Look up a ride_requests row by its Paystack transaction reference.

    Used in the Paystack webhook handler to match an incoming payment event
    to the correct ride without needing its internal primary key.

    Args:
        conn: psycopg2 connection (RealDictCursor).
        ref:  Paystack transaction reference string.

    Returns:
        RealDictRow or None.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT * FROM ride_requests WHERE paystack_ref = %s',
            (ref,),
        )
        return cur.fetchone()
