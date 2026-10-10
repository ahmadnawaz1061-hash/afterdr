"""Account registration, password verification, and signed sessions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, Depends, HTTPException
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlmodel import Session, select

from app.database import get_session
from app.models import Account, Patient
from app.schemas import RegisterRequest


SESSION_COOKIE = "medcare_session"
ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()


class AccountExistsError(ValueError):
    pass


class AccountSaveError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    account: Account
    patient: Patient


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def token_minutes() -> int:
    try:
        minutes = int(os.getenv("AUTH_TOKEN_MINUTES", "480"))
    except ValueError as exc:
        raise RuntimeError("AUTH_TOKEN_MINUTES must be an integer") from exc
    if not 5 <= minutes <= 10080:
        raise RuntimeError("AUTH_TOKEN_MINUTES must be between 5 and 10080")
    return minutes


def auth_secret() -> str:
    secret = os.getenv("AUTH_SECRET_KEY", "").strip()
    if len(secret) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must contain at least 32 characters")
    return secret


def cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "false").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def create_session_token(account_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(account_id),
            "iat": now,
            "exp": now + timedelta(minutes=token_minutes()),
        },
        auth_secret(),
        algorithm=ALGORITHM,
    )


def decode_session_token(token: str) -> int:
    try:
        payload = jwt.decode(token, auth_secret(), algorithms=[ALGORITHM])
        account_id = int(payload.get("sub", ""))
    except (InvalidTokenError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc
    if account_id < 1:
        raise HTTPException(status_code=401, detail="Authentication required")
    return account_id


def register_account(session: Session, payload: RegisterRequest) -> AuthenticatedUser:
    email = normalize_email(payload.email)
    if session.exec(select(Account).where(Account.email == email)).first() is not None:
        raise AccountExistsError("An account with this email already exists")
    try:
        patient = Patient(demo_name=payload.name)
        session.add(patient)
        session.flush()
        account = Account(
            patient_id=patient.id,
            email=email,
            password_hash=password_hash.hash(payload.password),
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        session.refresh(patient)
        return AuthenticatedUser(account=account, patient=patient)
    except Exception as exc:
        session.rollback()
        raise AccountSaveError("The account could not be created") from exc


def authenticate_account(
    session: Session,
    email: str,
    password: str,
) -> AuthenticatedUser | None:
    account = session.exec(
        select(Account).where(Account.email == normalize_email(email))
    ).first()
    if account is None or not password_hash.verify(password, account.password_hash):
        return None
    patient = session.get(Patient, account.patient_id)
    if patient is None:
        return None
    return AuthenticatedUser(account=account, patient=patient)


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_session),
) -> AuthenticatedUser:
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    account = session.get(Account, decode_session_token(session_token))
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    patient = session.get(Patient, account.patient_id)
    if patient is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return AuthenticatedUser(account=account, patient=patient)
