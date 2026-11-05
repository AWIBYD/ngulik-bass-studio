from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from . import migrate
from .routers import auth, misc, projects, stems
from .security import CSRF_HEADER, limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    migrate.run()
    yield


app = FastAPI(title="NGULIK BASS STUDIO API", version="0.2.0-phase2", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    # Cookie auth + SameSite=Lax, plus a custom header requirement on every state-changing call.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
        if request.headers.get(CSRF_HEADER) != "1":
            return JSONResponse({"detail": "Missing request header"}, status_code=403)
    return await call_next(request)


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(misc.router)
app.include_router(stems.router)
