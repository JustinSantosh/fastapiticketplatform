from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services as service
from app.auth import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import ErrorResponse, UserBrief

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get(
    "/agents",
    response_model=list[UserBrief],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_agents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Agents only: options for the "assign to" dropdown."""
    return service.list_agents(db, user)
