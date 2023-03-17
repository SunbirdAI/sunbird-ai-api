from fastapi import FastAPI
from app.routers.tasks import router as tasks_router


app = FastAPI()

app.include_router(tasks_router, prefix="/tasks", tags=["AI Tasks"])
