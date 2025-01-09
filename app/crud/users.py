from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import users as models
from app.models.users import User
from app.schemas import users as schema


async def create_user(db: AsyncSession, user: schema.UserInDB) -> schema.User:
    db_user = models.User(
        email=user.email,
        username=user.username,
        organization=user.organization,
        hashed_password=user.hashed_password,
        oauth_type=user.oauth_type,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def get_user_by_username(db: AsyncSession, username: str):
    result = await db.execute(
        select(models.User).filter(models.User.username == username)
    )
    return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(models.User).filter(models.User.email == email))
    return result.scalars().first()


async def update_user_password_reset_token(
    db: AsyncSession, user_id: int, reset_token: str
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalars().first()
    if user and user.oauth_type == "Credentials":
        user.password_reset_token = reset_token
        await db.commit()
        await db.refresh(user)

    return user


async def update_user_organization(
    db: AsyncSession, username: str, organization_name: str
) -> User:
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()
    if user:
        user.organization = organization_name
        await db.commit()
        await db.refresh(user)
    return user
