import time
from fastapi import Request, Depends, Response
from app.routers.auth import get_current_user
from app.deps import get_db


async def log_request(request: Request, call_next):
    if request.url.path.startswith('/tasks'):
        token = request.headers['Authorization'].replace('Bearer ', '')
        user = get_current_user(token, next(get_db()))
        print(user.username)
        start = time.time()
        response: Response = await call_next(request)
        print(response.headers)
        end = time.time()
        # print(current_user.username)
        print(f"Time taken: {end - start}s")
    else:
        response = await call_next(request)
    return response
