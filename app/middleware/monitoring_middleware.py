import time

from fastapi import Request
from fastapi.exceptions import HTTPException
from jose import jwt

from app.crud.monitoring import create_endpoint_log
from app.schemas.monitoring import EndpointLog
from app.utils.auth_utils import ALGORITHM, SECRET_KEY


async def log_request(request: Request, call_next):
    if request.url.path.startswith("/tasks"):
        try:
            header = request.headers["Authorization"]
            bearer, _, token = header.partition(" ")
            # token = request.headers['Authorization'].replace('Bearer ', '')

            # TODO: Find another way of getting the current user.
            # This is inefficient as it makes 2 similar database calls which causes
            # problems with the DB pool size
            # user = get_current_user(token, db_session)
            # TODO: This is a hacky workaround for the hackathon to prevent multiple DB calls.
            username = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
            organization = "PLACEHOLDER_TO_FIX"
            start = time.time()
            response = await call_next(request)
            end = time.time()
            # print(current_user.username)
            endpoint_log = EndpointLog(
                username=username,
                endpoint=request.url.path,
                organization=organization,
                time_taken=(end - start),
            )
            create_endpoint_log(endpoint_log)
        except HTTPException:
            response = await call_next(request)
        except KeyError:
            response = await call_next(request)
        except jwt.JWTError:
            response = await call_next(request)
    else:
        response = await call_next(request)
    return response
