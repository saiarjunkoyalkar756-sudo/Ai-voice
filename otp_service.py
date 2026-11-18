"""
Voicely OTP Service.
Handles cryptographically secure OTP generation, database storage, rate-limiting, and verification.
"""
from __future__ import annotations

import os
import sqlite3
import secrets
import time
import logging
from datetime import datetime, timezone
from email_service import send_otp_email

logger = logging.getLogger("otp_service")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "auth_otps.db")

EXPIRY_SECONDS = 10 * 60  # 10 minutes
RATE_LIMIT_SECONDS = 45   # Minimum 45 seconds between requests
MAX_ATTEMPTS = 5


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_otp_db() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE,
                otp_code TEXT NOT NULL,
                purpose TEXT NOT NULL,
                expires_at REAL NOT NULL,
                attempts INTEGER DEFAULT 0,
                used INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_otps_lookup ON auth_otps (email, purpose, used);")


# Initialize on import
init_otp_db()


def create_and_send_otp(email: str, purpose: str = "Password Reset") -> tuple[bool, str]:
    """Generate a 6-digit OTP, store in database, and dispatch via email."""
    email = email.strip().lower()
    now = time.time()

    init_otp_db()
    with _get_conn() as conn:
        # Check rate-limit: has an OTP been issued in the last 45s?
        recent = conn.execute(
            "SELECT created_at FROM auth_otps WHERE email = ? AND purpose = ? AND created_at > ? ORDER BY created_at DESC LIMIT 1",
            (email, purpose, now - RATE_LIMIT_SECONDS),
        ).fetchone()

        if recent:
            wait_seconds = int(RATE_LIMIT_SECONDS - (now - recent["created_at"]))
            return False, f"Please wait {wait_seconds} seconds before requesting another code."

        # Generate 6-digit numeric OTP
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = now + EXPIRY_SECONDS

        # Invalidate any older unused codes for this email and purpose
        conn.execute(
            "UPDATE auth_otps SET used = 1 WHERE email = ? AND purpose = ? AND used = 0",
            (email, purpose),
        )

        conn.execute(
            "INSERT INTO auth_otps (email, otp_code, purpose, expires_at, attempts, used, created_at) VALUES (?, ?, ?, ?, 0, 0, ?)",
            (email, code, purpose, expires_at, now),
        )

    # Dispatch email
    sent = send_otp_email(email, code, purpose)
    if not sent:
        return False, "Failed to dispatch email. Please check server mail configuration."

    return True, "Verification code sent successfully to your email."


def verify_otp(email: str, code: str, purpose: str = "Password Reset", mark_used: bool = True) -> tuple[bool, str]:
    """Verify submitted OTP code against active unexpired entries."""
    email = email.strip().lower()
    code = code.strip()
    now = time.time()

    init_otp_db()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, otp_code, expires_at, attempts FROM auth_otps WHERE email = ? AND purpose = ? AND used = 0 ORDER BY created_at DESC LIMIT 1",
            (email, purpose),
        ).fetchone()

        if not row:
            return False, "No active verification code found. Please request a new one."

        otp_id = row["id"]
        attempts = row["attempts"] + 1

        if now > row["expires_at"]:
            conn.execute("UPDATE auth_otps SET used = 1 WHERE id = ?", (otp_id,))
            return False, "Verification code has expired. Please request a new code."

        if attempts > MAX_ATTEMPTS:
            conn.execute("UPDATE auth_otps SET used = 1 WHERE id = ?", (otp_id,))
            return False, "Too many failed attempts. Code has been invalidated."

        conn.execute("UPDATE auth_otps SET attempts = ? WHERE id = ?", (attempts, otp_id))

        if secrets.compare_digest(code, row["otp_code"]):
            if mark_used:
                conn.execute("UPDATE auth_otps SET used = 1 WHERE id = ?", (otp_id,))
            return True, "Code verified successfully."
        else:
            remaining = MAX_ATTEMPTS - attempts
            return False, f"Invalid code. {remaining} attempt(s) remaining."
