from sqlalchemy.orm import Session

from app.models import users as models
from app.schemas import users as schema


def create_user(db: Session, user: schema.UserInDB) -> schema.User:
    db_user = models.User(
        email=user.email,
        username=user.username,
        organization=user.organization,
        hashed_password=user.hashed_password,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()
