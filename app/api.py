from fastapi import FastAPI
from app.routers.tasks import router as tasks_router
from app.routers.auth import router as auth_router


app = FastAPI()

app.include_router(tasks_router, prefix="/tasks", tags=["AI Tasks"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication Endpoints"])
