import time
from fastapi import Request
from fastapi.exceptions import HTTPException
from app.routers.auth import get_current_user
from app.deps import get_db
from app.schemas.monitoring import EndpointLog
from app.crud.monitoring import create_endpoint_log


async def log_request(request: Request, call_next):
    if request.url.path.startswith('/tasks'):
        try:
            token = request.headers['Authorization'].replace('Bearer ', '')
            db_session = next(get_db())
            user = get_current_user(token, db_session)
            start = time.time()
            response = await call_next(request)
            end = time.time()
            # print(current_user.username)
            endpoint_log = EndpointLog(username=user.username, endpoint=request.url.path, time_taken=(end - start))
            create_endpoint_log(db_session, endpoint_log)
        except HTTPException:
            response = await call_next(request)
    else:
        response = await call_next(request)
    return response
