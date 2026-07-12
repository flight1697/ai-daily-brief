from __future__ import annotations

import hashlib
import time

import httpx


def send_email(api_key: str, sender: str, recipient: str, subject: str, html: str,
               idempotency_key: str | None = None) -> str:
    if not api_key:
        raise ValueError("RESEND_API_KEY is required to send email")
    if not recipient:
        raise ValueError("EMAIL_TO is required to send email")
    key = idempotency_key or hashlib.sha256(
        f"{recipient}\n{subject}\n{html}".encode("utf-8")
    ).hexdigest()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"ai-daily-brief/{key}",
    }
    last_error: Exception | None = None
    for attempt in range(3):
        response: httpx.Response | None = None
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers=headers,
                json={"from": sender, "to": [recipient], "subject": subject, "html": html},
                timeout=30,
            )
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response.json()["id"]
            last_error = httpx.HTTPStatusError(
                f"Retryable Resend status {response.status_code}",
                request=response.request, response=response,
            )
        except (httpx.TransportError, KeyError) as exc:
            last_error = exc
        if attempt < 2:
            retry_after = response.headers.get("Retry-After") if response is not None else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            time.sleep(delay)
    raise RuntimeError("Resend failed after 3 attempts") from last_error
