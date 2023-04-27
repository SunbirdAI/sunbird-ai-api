from app.database.db import get_user


def verify_password(plain_password, hashed_password):
    return f"hashed_{plain_password}" == hashed_password  # TODO: Implement actual hashing


def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user
