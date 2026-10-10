from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app.database import get_session
from app.schemas import AuthUserResponse, LoginRequest, RegisterRequest
from app.services.auth_service import (
    SESSION_COOKIE,
    AccountExistsError,
    AccountSaveError,
    AuthenticatedUser,
    authenticate_account,
    cookie_secure,
    create_session_token,
    get_current_user,
    register_account,
    token_minutes,
)


router = APIRouter(prefix="/api/auth", tags=["authentication"])


def user_response(user: AuthenticatedUser) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.account.id,
        patient_id=user.patient.id,
        name=user.patient.demo_name,
        email=user.account.email,
    )


def set_session_cookie(response: Response, account_id: int) -> None:
    max_age = token_minutes() * 60
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(account_id),
        max_age=max_age,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthUserResponse, status_code=201)
def register(
    payload: RegisterRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthUserResponse:
    try:
        user = register_account(session, payload)
    except AccountExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AccountSaveError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    set_session_cookie(response, user.account.id)
    return user_response(user)


@router.post("/login", response_model=AuthUserResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthUserResponse:
    user = authenticate_account(session, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    set_session_cookie(response, user.account.id)
    return user_response(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=cookie_secure(),
        httponly=True,
        samesite="lax",
    )


@router.get("/me", response_model=AuthUserResponse)
def me(user: AuthenticatedUser = Depends(get_current_user)) -> AuthUserResponse:
    return user_response(user)
