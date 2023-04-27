from app.models.users import UserInDB, User
db = {
    "users": {}
}

def insert_user(user: UserInDB) -> User:
    id_ = len(db["users"]) + 1
    user_dict = user.dict()
    user_dict['id'] = id_
    db["users"][user.username] = user_dict
    return User(**user_dict)

def get_user(username: str) -> UserInDB:
    if username not in db["users"]:
        return None
    return UserInDB(**db["users"][username])

