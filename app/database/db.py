from app.models.users import UserInDB, User
db = {
    "users": []
}

def insert_user(user: UserInDB) -> User:
    id_ = len(db["users"]) + 1
    user_dict = user.dict()
    user_dict['id'] = id_
    db["users"].append(user_dict)
    return User(**user_dict)
