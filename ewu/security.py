"""Reusable verifier for a future webhook adapter; polling remains the current transport."""
import hmac
from .domain import Denied


def verify_webhook(headers,expected_secret):
    supplied=next((v for k,v in headers.items() if k.lower()=='x-telegram-bot-api-secret-token'),'')
    if not expected_secret or len(expected_secret)<32 or not isinstance(supplied,str) or not hmac.compare_digest(supplied,expected_secret):
        raise Denied('Webhook authentication failed')
