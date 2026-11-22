"""Server-side YooKassa transport. Credentials never enter public responses."""
import os
from urllib.parse import urlparse

import requests
from fastapi import HTTPException


def configured():
    return bool(os.getenv("YOOKASSA_SHOP_ID") and os.getenv("YOOKASSA_SECRET_KEY"))


def request(method, path, payload=None, key=None):
    if not configured():
        raise HTTPException(503, "Оплата через ЮKassa ещё не настроена")
    try:
        response = requests.request(
            method, f"https://api.yookassa.ru/v3/{path}",
            auth=(os.environ["YOOKASSA_SHOP_ID"], os.environ["YOOKASSA_SECRET_KEY"]),
            headers={"Idempotence-Key": key} if key else {},
            json=payload, timeout=(5, 20), allow_redirects=False,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(502, "ЮKassa временно недоступна. Повторите проверку платежа") from exc


def return_url(order_id):
    base = os.getenv("PAYMENT_RETURN_URL", "")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise HTTPException(503, "Адрес возврата после оплаты ещё не настроен")
    return f"{base}?order={order_id}"


def confirmation_url(payment):
    url = payment.get("confirmation", {}).get("confirmation_url")
    if url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise HTTPException(502, "Некорректный адрес страницы оплаты")
    return url
