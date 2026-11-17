"""Who the caller is: used by the sign-in screen to show the right pages for each role."""

from fastapi import APIRouter, Depends

from app.core.security import User, get_current_user
from app.schemas import Me

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=Me)
def me(user: User = Depends(get_current_user)):
    return Me(username=user.username, role=user.role)
