"""
functions/pricing.py — Fare calculation utilities.

Provides three thin helpers used by booking handlers and the admin panel:
  - get_unit_price      : look up a route's per-passenger price from the DB
  - calculate_fare      : produce a full fare breakdown dict (all ints, Naira)
  - format_fare_summary : render that dict as a human-readable Markdown string
"""

from config import DEFAULT_FARE_NAIRA, PLATFORM_CUT_PCT


# ──────────────────────────── DB Lookup ───────────────────────────────────────

def get_unit_price(conn, pickup_id: int, dest_id: int) -> int:
    """
    Return the per-passenger price (Naira) for a route.

    Uses LEAST/GREATEST so the A->B and B->A directions map to the same row;
    route_prices stores (loc_a_id, loc_b_id) with loc_a_id < loc_b_id always.

    Falls back to DEFAULT_FARE_NAIRA (500 by default) when no custom row exists.

    Args:
        conn:       psycopg2 connection (RealDictCursor factory assumed).
        pickup_id:  locations.id of the pickup point.
        dest_id:    locations.id of the destination.

    Returns:
        Integer Naira price for one passenger.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT price FROM route_prices '
            'WHERE loc_a_id = LEAST(%s, %s) AND loc_b_id = GREATEST(%s, %s)',
            (pickup_id, dest_id, pickup_id, dest_id),
        )
        row = cur.fetchone()

    # row is a RealDictRow (dict-like); fall back when no custom price exists
    return row['price'] if row else DEFAULT_FARE_NAIRA


# ──────────────────────────── Fare Calculation ────────────────────────────────

def calculate_fare(unit_price: int, passengers: int) -> dict:
    """
    Build a complete fare breakdown dict from a unit price and passenger count.

    Platform cut is floored (int()) so the driver never receives a fraction.
    All amounts are integer Naira — no floats, no kobo.

    Args:
        unit_price:  Per-passenger price in Naira.
        passengers:  Number of passengers booked.

    Returns:
        dict with keys:
            unit_price      - price per passenger (Naira)
            passengers      - number of passengers
            total           - gross fare (Naira)
            platform_cut    - platform's share, floored (Naira)
            driver_earnings - what the driver takes home (Naira)
    """
    total = unit_price * passengers
    # Floor the cut so we never credit fractional Naira to the platform
    platform_cut = int(total * PLATFORM_CUT_PCT)
    driver_earnings = total - platform_cut

    return {
        'unit_price': unit_price,
        'passengers': passengers,
        'total': total,
        'platform_cut': platform_cut,
        'driver_earnings': driver_earnings,
    }


# ──────────────────────────── Formatting ──────────────────────────────────────

def format_fare_summary(fare: dict) -> str:
    """
    Render a fare breakdown dict as a Telegram-safe Markdown string.

    Example output:
        Fare Breakdown
        Passengers: 2
        Unit Price: N500
        -----------------
        Total: N1,000

    Args:
        fare: dict returned by calculate_fare().

    Returns:
        Multi-line Markdown string (no trailing newline).
    """
    pax = fare['passengers']
    unit = fare['unit_price']
    total = fare['total']

    naira_sign = '\u20a6'         # Unicode Naira sign: N
    divider    = '\u2500' * 17    # Unicode horizontal bar repeated 17 times

    lines = [
        '\U0001f4b0 *Fare Breakdown*',
        f'Passengers: {pax}',
        f'Unit Price: {naira_sign}{unit:,}',
        divider,
        f'*Total: {naira_sign}{total:,}*',
    ]
    return '\n'.join(lines)
