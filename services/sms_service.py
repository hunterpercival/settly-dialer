from __future__ import annotations

import logging
import time
import threading

from config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise RuntimeError("Twilio credentials not configured.")
        from twilio.rest import Client
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def send_sms(to: str, body: str) -> str:
    """Send an SMS via Twilio, splitting on newlines so each line is its own message.

    Returns the SID of the last message sent.
    """
    client = _get_client()
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    last_sid = None
    for i, line in enumerate(lines):
        message = client.messages.create(
            body=line,
            from_=settings.twilio_phone_number,
            to=to,
        )
        logger.info("SMS sent to %s (sid=%s): %s", to, message.sid, line)
        last_sid = message.sid
        if i < len(lines) - 1:
            time.sleep(2)
    return last_sid


def send_sms_lines(to: str, lines: list[str]):
    """Send each line as a separate SMS with delays."""
    client = _get_client()
    for i, line in enumerate(lines):
        client.messages.create(
            body=line,
            from_=settings.twilio_phone_number,
            to=to,
        )
        logger.info("SMS sent to %s: %s", to, line)
        if i < len(lines) - 1:
            time.sleep(2)


def send_sms_background(to: str, lines: list[str]):
    """Send SMS in a background thread so we don't block the webhook."""
    thread = threading.Thread(target=send_sms_lines, args=(to, lines))
    thread.start()
