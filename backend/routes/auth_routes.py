from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from ..auth import create_token, verify_password, current_user
from ..database import get_session
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    user = session.exec(select(User).where(User.username == form.username)).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    token = create_token(user.username)
    return {"access_token": token, "token_type": "bearer", "role": user.role}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "office_id": user.office_id,
        "zone_id": user.zone_id,
        "department": user.department,
    }
