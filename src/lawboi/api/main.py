from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from lawboi.api.errors import register_exception_handlers
from lawboi.api.limiter import limiter
from lawboi.config.settings import load_settings

_settings = load_settings()

app = FastAPI(title="Eesti Õigusabi API", version="0.2.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if _settings.trusted_proxies:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=_settings.trusted_proxies)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

from lawboi.api.routes import acts, answer, search  # noqa: E402

app.include_router(answer.router)
app.include_router(search.router)
app.include_router(acts.router)


@app.get("/health")
def health():
    return {"status": "ok"}
