import logging
import time

from fastapi import Request
from fastapi.exceptions import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.crud.monitoring import create_endpoint_log
from app.crud.users import get_user_by_username
from app.deps import get_db
from app.schemas.monitoring import EndpointLog
from app.utils.auth import ALGORITHM, SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def log_request(request: Request, call_next):
    if request.url.path.startswith("/tasks"):
        try:
            # Get the token from the authorization header
            header = request.headers.get("Authorization")
            if header:
                bearer, _, token = header.partition(" ")
                if bearer.lower() != "bearer":
                    raise HTTPException(status_code=401, detail="Invalid token header")

                # Decode the JWT token to get the username
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username: str = payload.get("sub")
                if username is None:
                    raise HTTPException(status_code=401, detail="Invalid token payload")

                # Create a db session and fetch the user
                db: Session = next(get_db())
                user = get_user_by_username(db, username)
                if user is None:
                    raise HTTPException(status_code=401, detail="User not found")
            else:
                raise HTTPException(
                    status_code=401, detail="Missing authorization header"
                )

            start = time.time()
            response = await call_next(request)
            end = time.time()

            # Log the endpoint access details
            endpoint_log = EndpointLog(
                username=username,
                endpoint=request.url.path,
                organization=user.organization,
                time_taken=(end - start),
            )
            create_endpoint_log(endpoint_log)
        except HTTPException as e:
            logger.error(f"Error: {str(e)}")
            response = await call_next(request)
        except KeyError as e:
            logger.error(f"Error: {str(e)}")
            response = await call_next(request)
        except JWTError as e:
            logger.error(f"Error: {str(e)}")
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            response = await call_next(request)
    else:
        response = await call_next(request)
    return response
