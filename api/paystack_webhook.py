"""
api/paystack_webhook.py — Handles incoming Paystack webhook events.
Processes:
  - charge.success: student online payment completed, notifies student & driver
  - transfer.success: driver payout confirmed by bank
  - transfer.failed: driver payout failed, refunds wallet
"""
import logging
from functions import db, paystack
from bot.keyboards.driver import ride_response_keyboard

logger = logging.getLogger(__name__)


def confirm_paid_ride(bot, conn, ride_id, reference=None):
    """
    Mark a ride as paid, update paystack_ref, notify student, and dispatch to driver.
    Reusable by both the webhook handler and the student manual verification button.
    Returns (success: bool, message: str).
    """
    ride = db.get_ride(conn, ride_id)
    if not ride:
        return False, "Ride not found"

    if ride.get('payment_status') == 'paid':
        return True, "Ride already marked as paid"

    db.update_ride_payment_status(conn, ride['id'], 'paid', paystack_ref=reference)

    # 1. Tell student payment confirmed
    try:
        bot.send_message(
            ride['student_telegram_id'],
            f"✅ *Payment Received!*\n\n"
            f"🎫 Booking: `{ride['booking_id']}`\n"
            f"💰 Amount Paid: ₦{ride['fare_amount']:,}\n\n"
            f"Your ride request has been dispatched to {ride['driver_name']}.\n"
            "Waiting for driver confirmation...",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify student of paid ride {ride['id']}: {e}")

    # 2. Dispatch ride to driver
    try:
        pax = ride.get('passenger_count', 1)
        pax_label = f"{pax} passenger{'s' if pax > 1 else ''}"
        driver_msg = bot.send_message(
            ride['driver_telegram_id'],
            f"🔔 *New Paid Ride Request!*\n\n"
            f"👤 Passenger: {ride['student_name']}\n"
            f"📍 From: {ride['pickup_name']}\n"
            f"📍 To: {ride['dest_name']}\n"
            f"👥 Passengers: {pax_label}\n"
            f"💰 Fare: ₦{ride['fare_amount']:,} (Paid Online ✅)\n"
            f"💵 Your Earnings: ₦{ride['driver_earnings']:,}\n\n"
            f"⏱ You have 5 minutes to respond.",
            parse_mode='Markdown',
            reply_markup=ride_response_keyboard(ride['id'])
        )
        db.save_driver_msg_id(conn, ride['id'], driver_msg.message_id)
    except Exception as e:
        logger.error(f"Failed to notify driver of paid ride {ride['id']}: {e}")

    return True, "Ride confirmed"


def handle_paystack_webhook(bot, get_conn, request_obj):
    """
    Process incoming Paystack webhook request.
    Verifies HMAC-SHA512 signature and processes event.
    Returns (response_dict, status_code).
    """
    raw_payload = request_obj.get_data()
    signature = request_obj.headers.get('x-paystack-signature', '')

    # Validate HMAC signature
    if not paystack.validate_webhook_signature(raw_payload, signature):
        logger.warning("Invalid Paystack webhook signature")
        return {"status": "error", "message": "Invalid signature"}, 400

    payload = request_obj.get_json(silent=True) or {}
    event = payload.get('event')
    data = payload.get('data', {})

    logger.info(f"Received Paystack webhook event: {event}")

    conn = get_conn()

    # ── 1. Student payment received ───────────────────────────────────────────
    if event == 'charge.success':
        reference = data.get('reference')
        metadata = data.get('metadata', {})
        if isinstance(metadata, str):
            import json
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        ride_id = metadata.get('ride_id')

        ride = None
        if ride_id:
            ride = db.get_ride(conn, int(ride_id))
        elif reference:
            ride = db.get_ride_by_paystack_ref(conn, reference)

        if not ride:
            logger.warning(f"No ride found matching Paystack charge reference: {reference}")
            return {"status": "ok"}, 200

        confirm_paid_ride(bot, conn, ride['id'], reference=reference)

    # ── 2. Driver withdrawal succeeded ────────────────────────────────────────
    elif event == 'transfer.success':
        reference = data.get('reference')
        db.confirm_withdrawal(conn, reference, 'completed')
        logger.info(f"Paystack transfer {reference} succeeded.")

    # ── 3. Driver withdrawal failed — refund wallet ───────────────────────────
    elif event in ('transfer.failed', 'transfer.reversed'):
        reference = data.get('reference')
        db.confirm_withdrawal(conn, reference, 'failed')
        # Refund driver balance
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM wallet_transactions WHERE reference = %s',
                (reference,)
            )
            tx = cur.fetchone()
            if tx:
                refund_amount = abs(tx['amount'])
                cur.execute(
                    'UPDATE driver_wallets SET balance = balance + %s, updated_at = NOW() '
                    'WHERE driver_id = %s',
                    (refund_amount, tx['driver_id'])
                )
                # Notify driver
                try:
                    driver_user = db.get_user(conn, tx['driver_id'])
                    if driver_user:
                        bot.send_message(
                            driver_user['telegram_id'],
                            f"❌ *Withdrawal Failed*\n\n"
                            f"Your bank transfer of ₦{refund_amount:,} failed and was returned.\n"
                            "The funds have been credited back to your wallet balance.",
                            parse_mode='Markdown'
                        )
                except Exception as notify_err:
                    logger.error(f"Failed to notify driver of failed transfer: {notify_err}")
        logger.warning(f"Paystack transfer {reference} failed; refunded to driver wallet.")

    return {"status": "ok"}, 200
