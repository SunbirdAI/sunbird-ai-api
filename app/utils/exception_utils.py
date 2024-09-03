from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.schemas.errors import ValidationErrorDetail, ValidationErrorResponse

app = FastAPI()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()

    # Format the errors to match your custom model
    formatted_errors = [
        ValidationErrorDetail(
            loc=error["loc"], msg=error["msg"], input=error.get("input")
        )
        for error in errors
    ]

    error_response = ValidationErrorResponse(errors=formatted_errors)

    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY, content=error_response.model_dump()
    )
