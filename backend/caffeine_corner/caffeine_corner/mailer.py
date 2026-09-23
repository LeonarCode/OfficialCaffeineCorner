"""
Everything the shop emails to customers and suppliers goes out through here:
one place that knows the shop's identity, how to render an email (HTML with a
plain-text copy), and how to send it without ever getting in the way of an order.

Two ways to send, for two different needs:

    send_html_email()       sends now and RAISES if it fails. For a staff member
                            clicking "Email to supplier": they wait a moment and
                            must be told if it didn't go.
    run_in_background()     for a customer's order: the order is already saved and
                            the customer is waiting for the page, so the email goes
                            out from a background thread and a failure is only
                            logged — a mail-server hiccup must never lose or delay
                            an order.
"""
import logging
import threading
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger('caffeine_corner.mail')

# These deliver instantly, so a thread would only add a race (the test runner uses locmem).
INSTANT_BACKENDS = ('locmem', 'console', 'dummy', 'filebased')


def peso(value):
    """₱1,250.00 — every amount in an email is formatted here, so they all look alike."""
    return f'₱{Decimal(value or 0):,.2f}'


def shop_time(moment):
    """An aware datetime, in the shop's timezone (the site's TIME_ZONE is UTC)."""
    return timezone.localtime(moment, ZoneInfo(settings.SHOP_TIMEZONE))


def shop_context():
    return {
        'shop_name': settings.SHOP_NAME,
        'shop_address': settings.SHOP_ADDRESS,
        'shop_phone': settings.SHOP_PHONE,
        'shop_email': settings.SHOP_REPLY_TO,
    }


def send_html_email(*, subject, to, template, context, reply_to=None):
    """
    Renders emails/<template>.html and .txt and sends them now. Raises whatever
    the mail backend raises (SMTP refused, timed out, ...).
    """
    subject = ' '.join(str(subject).split())                # one line, whatever went into it
    context = {**shop_context(), **context, 'subject': subject}
    message = EmailMultiAlternatives(
        subject,
        render_to_string(f'emails/{template}.txt', context),
        settings.DEFAULT_FROM_EMAIL,
        [to],
        reply_to=[reply_to or settings.SHOP_REPLY_TO] if (reply_to or settings.SHOP_REPLY_TO) else None,
    )
    message.attach_alternative(render_to_string(f'emails/{template}.html', context), 'text/html')
    message.send(fail_silently=False)


def _runs_in_background():
    backend = settings.EMAIL_BACKEND.lower()
    return getattr(settings, 'EMAIL_SEND_IN_BACKGROUND', True) and not any(name in backend for name in INSTANT_BACKENDS)


def run_in_background(func, *args, **kwargs):
    """
    Runs func(*args, **kwargs) so that it can't slow down or break the request.
    On a real mail server that is a background thread; with an instant backend
    (tests, console) it simply runs here. Returns the thread, or None.
    """
    if not _runs_in_background():
        _log_failures(func, *args, **kwargs)
        return None

    def target():
        try:
            _log_failures(func, *args, **kwargs)
        finally:
            connection.close()                              # a thread has its own database connection; don't leak it

    thread = threading.Thread(target=target, name='caffeine-mail', daemon=True)
    thread.start()
    return thread


def _log_failures(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:                                       # noqa: BLE001 — by design: never let an email break the caller
        logger.exception('Email %s failed', getattr(func, '__name__', func))
        return None
