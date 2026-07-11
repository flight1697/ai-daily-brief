from __future__ import annotations

import time

import httpx


def send_email(api_key: str, sender: str, recipient: str, subject: str, html: str) -> str:
    if not api_key:
        raise ValueError("RESEND_API_KEY is required to send email")
    if not recipient:
        raise ValueError("EMAIL_TO is required to send email")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": sender, "to": [recipient], "subject": subject, "html": html},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()["id"]
        except (httpx.HTTPError, KeyError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError("Resend failed after 3 attempts") from last_error
