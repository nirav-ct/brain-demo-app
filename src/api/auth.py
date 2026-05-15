"""Authentication API endpoints.

Handles user registration, login, token refresh, and session management.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.models.user import User, get_db

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()


def _create_jwt(user_id: int, email: str) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.JWT_EXPIRES_MIN)
    exp = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    return token, int(expires_delta.total_seconds())


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    salt = os.urandom(16).hex()
    hashed = _hash_password(body.password, salt)

    user = User(
        email=body.email,
        password_hash=f"{salt}:{hashed}",
        full_name=body.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token, expires_in = _create_jwt(user.id, user.email)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    salt, stored_hash = user.password_hash.split(":")
    if _hash_password(body.password, salt) != stored_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token, expires_in = _create_jwt(user.id, user.email)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at.isoformat(),
    }
