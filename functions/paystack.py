"""
functions/paystack.py -- Paystack REST API wrapper.

All public functions accept/return amounts in Naira (integers).
Kobo conversion (x100) happens internally before any API call.

Environment / config values used:
    PAYSTACK_SECRET_KEY  -- sk_live_... or sk_test_...
    PAYSTACK_BASE_URL    -- https://api.paystack.co

Raises RuntimeError (with a descriptive message) on any non-2xx response
so callers can handle failures without parsing raw HTTP objects.
"""

import hashlib
import hmac

import requests

from config import PAYSTACK_BASE_URL, PAYSTACK_SECRET_KEY

# Every outbound HTTP request will time out after this many seconds
_TIMEOUT = 15


# ------------------------------------------------------------------ helpers ---

def _headers() -> dict:
    """Return the Authorization + Content-Type headers required by Paystack."""
    return {
        'Authorization': 'Bearer ' + PAYSTACK_SECRET_KEY,
        'Content-Type': 'application/json',
    }


def _raise_for_status(resp: requests.Response, context: str) -> dict:
    """
    Parse the JSON body and raise RuntimeError when the call failed.

    Paystack always returns {"status": true/false, "message": "...", "data": ...}.
    We raise on HTTP errors AND on status:false payloads.

    Args:
        resp:    The raw requests.Response object.
        context: Short label used in the error message (e.g. "initialize_payment").

    Returns:
        The 'data' key from the Paystack response body.
    """
    try:
        body = resp.json()
    except ValueError:
        status_code = resp.status_code
        preview = resp.text[:200]
        raise RuntimeError(
            f'[paystack.{context}] Non-JSON response ({status_code}): {preview}'
        )

    if not resp.ok or not body.get('status'):
        message = body.get('message', 'Unknown error')
        status_code = resp.status_code
        raise RuntimeError(f'[paystack.{context}] {status_code} -- {message}')

    return body.get('data', {})


# ------------------------------------------------------------------ payments --

def initialize_payment(
    email: str,
    amount_naira: int,
    metadata: dict,
    channels: list = None,
    reference: str = None,
) -> dict:
    """
    Start a Paystack payment session.

    Calls POST /transaction/initialize.

    Args:
        email:        Customer's e-mail address (Paystack requirement).
        amount_naira: Gross fare in Naira (converted to kobo internally).
        metadata:     Arbitrary dict attached to the transaction (e.g. ride_id).
        channels:     Optional list of payment channels, e.g. ['card', 'bank'].
                      Defaults to Paystack's configured channel list when None.
        reference:    Optional unique transaction reference string.

    Returns:
        dict with keys:
            authorization_url -- URL to redirect/send to the customer
            access_code       -- short token for the Paystack inline widget
            reference         -- unique transaction reference
    """
    payload = {
        'email': email,
        'amount': amount_naira * 100,   # Paystack API expects kobo
        'metadata': metadata,
    }
    if reference:
        payload['reference'] = reference
    if channels:
        payload['channels'] = channels

    resp = requests.post(
        PAYSTACK_BASE_URL + '/transaction/initialize',
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _raise_for_status(resp, 'initialize_payment')

    return {
        'authorization_url': data['authorization_url'],
        'access_code':       data['access_code'],
        'reference':         data['reference'],
    }


def verify_payment(reference: str) -> dict:
    """
    Confirm a transaction's outcome.

    Calls GET /transaction/verify/{reference}.

    Args:
        reference: The transaction reference returned by initialize_payment().

    Returns:
        Full 'data' dict from the Paystack response (contains 'status',
        'amount', 'customer', 'metadata', etc.).
    """
    resp = requests.get(
        PAYSTACK_BASE_URL + '/transaction/verify/' + reference,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    return _raise_for_status(resp, 'verify_payment')


# -------------------------------------------------------------------- banks ---

def list_banks() -> list:
    """
    Fetch the list of Nigerian banks supported by Paystack.

    Calls GET /bank?country=nigeria&per_page=100.

    Returns:
        List of dicts sorted alphabetically by bank name:
            [{'name': 'Access Bank', 'code': '044'}, ...]
    """
    resp = requests.get(
        PAYSTACK_BASE_URL + '/bank',
        params={'country': 'nigeria', 'per_page': 100},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _raise_for_status(resp, 'list_banks')

    # Extract only the two fields the rest of the bot needs
    banks = [{'name': b['name'], 'code': b['code']} for b in data]
    return sorted(banks, key=lambda b: b['name'])


def resolve_account(account_number: str, bank_code: str) -> dict:
    """
    Look up the account name for a given account number and bank.

    Calls GET /bank/resolve.

    Args:
        account_number: 10-digit NUBAN account number.
        bank_code:      Bank code from list_banks().

    Returns:
        dict with keys:
            account_name   -- resolved account holder name
            account_number -- echoed account number (as returned by Paystack)
    """
    resp = requests.get(
        PAYSTACK_BASE_URL + '/bank/resolve',
        params={'account_number': account_number, 'bank_code': bank_code},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _raise_for_status(resp, 'resolve_account')

    return {
        'account_name':   data['account_name'],
        'account_number': data['account_number'],
    }


# --------------------------------------------------------------- transfers ---

def create_transfer_recipient(
    name: str,
    account_number: str,
    bank_code: str,
) -> str:
    """
    Register a transfer recipient on Paystack (required before sending money).

    Calls POST /transferrecipient.

    Args:
        name:           Account holder's name (used as the recipient display name).
        account_number: 10-digit NUBAN number.
        bank_code:      Bank code from list_banks().

    Returns:
        The Paystack recipient code string (e.g. 'RCP_xxxxxxxxxxxxxxxx').
        Store this in driver_wallets.recipient_code for future payouts.
    """
    payload = {
        'type':           'nuban',
        'name':           name,
        'account_number': account_number,
        'bank_code':      bank_code,
        'currency':       'NGN',
    }
    resp = requests.post(
        PAYSTACK_BASE_URL + '/transferrecipient',
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _raise_for_status(resp, 'create_transfer_recipient')
    return data['recipient_code']


def initiate_transfer(
    amount_naira: int,
    recipient_code: str,
    reason: str = 'Shuttle earnings',
) -> dict:
    """
    Send money to a previously registered transfer recipient.

    Calls POST /transfer.

    Note: Paystack may require OTP confirmation depending on account settings.

    Args:
        amount_naira:   Amount to transfer in Naira (converted to kobo internally).
        recipient_code: Recipient code from create_transfer_recipient().
        reason:         Human-readable transfer narration (max ~100 chars).

    Returns:
        dict with keys:
            transfer_code -- unique code for the transfer (use to track status)
            reference     -- transfer reference
            status        -- initial status string (e.g. 'pending')
    """
    payload = {
        'source':    'balance',
        'amount':    amount_naira * 100,   # kobo
        'recipient': recipient_code,
        'reason':    reason,
    }
    resp = requests.post(
        PAYSTACK_BASE_URL + '/transfer',
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _raise_for_status(resp, 'initiate_transfer')

    return {
        'transfer_code': data['transfer_code'],
        'reference':     data['reference'],
        'status':        data['status'],
    }


# --------------------------------------------------------------- webhooks ---

def validate_webhook_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Verify that a Paystack webhook request is authentic.

    Paystack signs the raw request body with HMAC-SHA512 using your secret key
    and sends the hex digest in the X-Paystack-Signature header.

    Args:
        payload_bytes:    Raw request body bytes (before any JSON parsing).
        signature_header: Value of the X-Paystack-Signature HTTP header.

    Returns:
        True if the signature is valid, False otherwise.
    """
    expected = hmac.new(
        PAYSTACK_SECRET_KEY.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha512,
    ).hexdigest()

    # compare_digest is constant-time; protects against timing attacks
    return hmac.compare_digest(expected, signature_header)
