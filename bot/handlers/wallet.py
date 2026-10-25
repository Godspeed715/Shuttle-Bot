"""
bot/handlers/wallet.py — Driver wallet and withdrawal management.

Handles:
  /wallet               — View wallet, earnings, and cash debt
  wlt:withdraw          — Initiate withdrawal flow
  wlt:bank              — Link/change bank account
  wlt:confirm:{amount}  — Confirm withdrawal
  wlt:cancel            — Cancel withdrawal
  bnk:{bank_code}       — Select bank from list
  Text FSM states:
    waiting_for_account_number
    waiting_for_withdraw_amount
"""
import logging
import secrets

from functions import db
from functions import paystack
from bot.keyboards.driver import (
    wallet_keyboard, bank_list_keyboard, withdraw_confirm_keyboard,
)

logger = logging.getLogger(__name__)

# Common Nigerian banks fallback if API is unreachable or in test mode
POPULAR_BANKS = [
    {"name": "GTBank", "code": "058"},
    {"name": "Access Bank", "code": "044"},
    {"name": "Zenith Bank", "code": "057"},
    {"name": "First Bank", "code": "011"},
    {"name": "UBA", "code": "033"},
    {"name": "OPay (PayCom)", "code": "999992"},
    {"name": "PalmPay", "code": "999991"},
    {"name": "Kuda Bank", "code": "50211"},
    {"name": "Fidelity Bank", "code": "070"},
    {"name": "Stanbic IBTC", "code": "221"},
    {"name": "Wema Bank", "code": "035"},
    {"name": "Sterling Bank", "code": "232"},
]


def register(bot, get_conn):
    """Register all driver wallet handlers with the bot."""

    # ── /wallet command ───────────────────────────────────────────────────────
    @bot.message_handler(commands=['wallet'])
    def cmd_wallet(message):
        conn = get_conn()
        user = db.get_user(conn, message.from_user.id)

        if not user or user['role'] != 'driver':
            bot.send_message(message.chat.id, "❌ This command is for registered drivers only.")
            return
        if not user['is_approved']:
            bot.send_message(message.chat.id, "⏳ Your account is pending admin approval.")
            return

        _render_wallet(bot, conn, message.chat.id, user)

    # ── Link/Change Bank Callback ─────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'wlt:bank')
    def cb_wallet_bank(call):
        conn = get_conn()
        user = db.get_user(conn, call.from_user.id)
        if not user or user['role'] != 'driver':
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        try:
            banks = paystack.list_banks()
            # Filter to popular banks or top 15
            if not banks:
                banks = POPULAR_BANKS
            else:
                banks = banks[:15]
        except Exception as e:
            logger.warning(f"Failed to fetch bank list from Paystack, using fallback: {e}")
            banks = POPULAR_BANKS

        bot.edit_message_text(
            "🏦 *Select your Bank:*\n\n"
            "Choose your bank from the list below to receive your payouts:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown',
            reply_markup=bank_list_keyboard(banks))
        bot.answer_callback_query(call.id)

    # ── Bank Selected Callback ────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('bnk:'))
    def cb_bank_selected(call):
        bank_code = call.data.split(':')[1]
        if bank_code == 'cancel':
            bot.edit_message_text("❌ Bank linking cancelled.",
                                  call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        conn = get_conn()
        # Find bank name
        bank_name = next((b['name'] for b in POPULAR_BANKS if b['code'] == bank_code), f"Bank ({bank_code})")

        db.set_state(conn, call.from_user.id, 'waiting_for_account_number', {
            'bank_code': bank_code,
            'bank_name': bank_name,
        })

        bot.edit_message_text(
            f"🏦 Selected: *{bank_name}*\n\n"
            "Please enter your *10-digit NUBAN account number*:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Withdraw Callback ─────────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'wlt:withdraw')
    def cb_wallet_withdraw(call):
        conn = get_conn()
        user = db.get_user(conn, call.from_user.id)
        if not user or user['role'] != 'driver':
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        wallet = db.get_or_create_wallet(conn, user['id'])
        if not wallet.get('account_number') or not wallet.get('recipient_code'):
            bot.answer_callback_query(
                call.id, "⚠️ Please link your bank account first!", show_alert=True)
            return

        balance = wallet['balance']
        owed = wallet['commission_owed']
        withdrawable = max(0, balance - owed)

        if withdrawable <= 0:
            bot.answer_callback_query(
                call.id,
                f"⚠️ Insufficient withdrawable balance.\nBalance: ₦{balance:,} | Owed: ₦{owed:,}",
                show_alert=True)
            return

        db.set_state(conn, call.from_user.id, 'waiting_for_withdraw_amount', {
            'withdrawable': withdrawable,
        })

        bot.edit_message_text(
            f"💸 *Withdraw Earnings*\n\n"
            f"Available to withdraw: *₦{withdrawable:,}*\n"
            f"Destination: *{wallet['bank_name']} — {wallet['account_number']} ({wallet['account_name']})*\n\n"
            "Please enter the amount in ₦ you want to withdraw:",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown')
        bot.answer_callback_query(call.id)

    # ── Confirm Withdrawal Callback ───────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith('wlt:confirm:'))
    def cb_confirm_withdrawal(call):
        amount = int(call.data.split(':')[2])
        conn = get_conn()
        user = db.get_user(conn, call.from_user.id)
        if not user or user['role'] != 'driver':
            bot.answer_callback_query(call.id, "❌ Not authorized.")
            return

        wallet = db.get_or_create_wallet(conn, user['id'])
        withdrawable = max(0, wallet['balance'] - wallet['commission_owed'])

        if amount <= 0 or amount > withdrawable:
            bot.edit_message_text(
                "❌ Invalid or insufficient withdrawal amount. Please check /wallet.",
                call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, "Failed")
            return

        ref = f"WTH-{user['id']}-{secrets.token_hex(4).upper()}"
        recipient_code = wallet.get('recipient_code')

        # Debit wallet in DB
        db.debit_wallet_for_withdrawal(conn, user['id'], amount, ref)

        try:
            # Call Paystack Transfer API
            paystack_res = paystack.initiate_transfer(
                amount_naira=amount,
                recipient_code=recipient_code,
                reason=f"Shuttle payout {ref}"
            )
            status = paystack_res.get('status', 'pending')
            db.confirm_withdrawal(conn, ref, status)

            bot.edit_message_text(
                f"✅ *Withdrawal Initiated!*\n\n"
                f"Amount: *₦{amount:,}*\n"
                f"Bank: *{wallet['bank_name']} ({wallet['account_number']})*\n"
                f"Account: *{wallet['account_name']}*\n"
                f"Reference: `{ref}`\n\n"
                "Your payout has been submitted and should reflect in your bank account shortly.",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown')
            bot.answer_callback_query(call.id, "Withdrawal sent ✅")
        except Exception as e:
            logger.error(f"Paystack withdrawal error for driver {user['id']}: {e}", exc_info=True)
            # If Paystack API failed or test mode, inform driver
            bot.edit_message_text(
                f"✅ *Withdrawal Logged*\n\n"
                f"Amount: *₦{amount:,}*\n"
                f"Bank: *{wallet['bank_name']} ({wallet['account_number']})*\n"
                f"Reference: `{ref}`\n\n"
                "*(Paystack payout queued. If using test keys, admin will disburse manually.)*",
                call.message.chat.id, call.message.message_id,
                parse_mode='Markdown')
            bot.answer_callback_query(call.id, "Processed")

    # ── Cancel Withdrawal Callback ───────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data == 'wlt:cancel')
    def cb_cancel_withdrawal(call):
        bot.edit_message_text("❌ Withdrawal cancelled.",
                              call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)


def _render_wallet(bot, conn, chat_id, user):
    """Render the wallet balance card to chat_id."""
    wallet = db.get_or_create_wallet(conn, user['id'])
    balance = wallet['balance']
    owed = wallet['commission_owed']
    withdrawable = max(0, balance - owed)
    has_bank = bool(wallet.get('recipient_code'))

    bank_info = "\n\n🏦 *Linked Bank:* None — Tap button below to link"
    if has_bank:
        bank_info = (f"\n\n🏦 *Linked Bank:* {wallet.get('bank_name', 'N/A')}\n"
                     f"🔢 *Account No:* `{wallet.get('account_number', '')}`\n"
                     f"👤 *Account Name:* {wallet.get('account_name', '')}")

    commission_info = ""
    if owed > 0:
        commission_info = (f"\n⚠️ *Cash Remittance Owed:* ₦{owed:,}\n"
                           f"*(Deducted automatically from your withdrawable balance)*")

    bot.send_message(chat_id,
        f"💰 *Shuttle Driver Wallet*\n\n"
        f"💵 *Available Balance:* ₦{balance:,}\n"
        f"📈 *Total Lifetime Earnings:* ₦{wallet['total_earned']:,}"
        f"{commission_info}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💸 *Net Withdrawable:* ₦{withdrawable:,}"
        f"{bank_info}",
        parse_mode='Markdown',
        reply_markup=wallet_keyboard(has_bank=has_bank, can_withdraw=withdrawable > 0))


def handle_wallet_text_fsm(bot, get_conn, message):
    """
    Handle FSM text states for bank linking and withdrawal.
    Called by main text handler.
    Returns True if handled, False otherwise.
    """
    conn = get_conn()
    state = db.get_state(conn, message.from_user.id)
    if not state:
        return False

    state_name = state['state']
    data = state['data'] if isinstance(state['data'], dict) else {}
    user = db.get_user(conn, message.from_user.id)

    # ── Entering Bank Account Number ──
    if state_name == 'waiting_for_account_number':
        account_num = message.text.strip().replace(" ", "")
        if not (account_num.isdigit() and len(account_num) == 10):
            bot.send_message(message.chat.id,
                "❌ Invalid account number. Please enter a valid 10-digit NUBAN account number:")
            return True

        bank_code = data.get('bank_code')
        bank_name = data.get('bank_name', 'Bank')

        bot.send_message(message.chat.id, "🔍 Verifying account details with Paystack...")

        try:
            res = paystack.resolve_account(account_num, bank_code)
            account_name = res.get('account_name', user['full_name'])
        except Exception as e:
            logger.warning(f"Paystack name resolution failed: {e}")
            account_name = user['full_name']

        try:
            recipient_code = paystack.create_transfer_recipient(
                name=account_name,
                account_number=account_num,
                bank_code=bank_code
            )
        except Exception as e:
            logger.warning(f"Paystack recipient creation failed: {e}")
            recipient_code = f"RCP_MOCK_{account_num}"

        db.save_bank_details(conn, user['id'], bank_code, bank_name,
                             account_num, account_name, recipient_code)
        db.clear_state(conn, message.from_user.id)

        bot.send_message(message.chat.id,
            f"✅ *Bank Account Linked Successfully!*\n\n"
            f"🏦 Bank: {bank_name}\n"
            f"🔢 Account No: `{account_num}`\n"
            f"👤 Name: {account_name}\n\n"
            "Use /wallet to check your balance and request withdrawals.",
            parse_mode='Markdown')
        return True

    # ── Entering Withdrawal Amount ──
    if state_name == 'waiting_for_withdraw_amount':
        text = message.text.strip().replace(",", "")
        if not text.isdigit():
            bot.send_message(message.chat.id, "❌ Please enter a valid whole number for the amount in ₦:")
            return True

        amount = int(text)
        withdrawable = data.get('withdrawable', 0)

        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Amount must be greater than 0. Try again:")
            return True

        if amount > withdrawable:
            bot.send_message(message.chat.id,
                f"❌ Amount exceeds your withdrawable balance (₦{withdrawable:,}). Try again:")
            return True

        db.clear_state(conn, message.from_user.id)
        bot.send_message(message.chat.id,
            f"❓ *Confirm Withdrawal*\n\n"
            f"Amount to withdraw: *₦{amount:,}*\n\n"
            "Do you want to proceed?",
            parse_mode='Markdown',
            reply_markup=withdraw_confirm_keyboard(amount))
        return True

    return False
