from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analysis, documents, exams, llm
from app.core import config
from app.core.errors import ApiException

app = FastAPI(title="AI 学习助手 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiException)
async def api_exception_handler(request: Request, exc: ApiException):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


app.include_router(documents.router)
app.include_router(analysis.router)
app.include_router(exams.router)
app.include_router(llm.router)


@app.get("/api/healthz")
def healthz():
    from app.core.providers import get_provider

    try:
        provider_info = get_provider().health_check()
    except ApiException as exc:
        provider_info = {"provider": "invalid", "configured": False, "detail": exc.message}
    return {
        "status": "ok",
        "llm_configured": provider_info.get("configured", False),
        "provider": provider_info,
    }
