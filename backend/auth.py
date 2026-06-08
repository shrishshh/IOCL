import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from .database import get_session
from .models import User

SECRET_KEY = os.getenv("SECRET_KEY", "iocl-dev-secret-key-change-in-production")
ALGORITHM = "HS256"
_TOKEN_HOURS = 8

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(pw: str) -> str:
    return _pwd_ctx.hash(pw)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def create_token(username: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=_TOKEN_HOURS)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


async def current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise exc
    except JWTError:
        raise exc
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise exc
    return user


def require_role(*roles: str):
    """Returns a FastAPI dependency that enforces one of the given roles."""
    async def _check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return _check
