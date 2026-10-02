import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import auth, jobs
from app.services.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(scheduler_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.include_router(auth.router)
app.include_router(jobs.router)