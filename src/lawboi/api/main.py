from dotenv import load_dotenv

load_dotenv()  # must run before settings imports so env vars are available

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from uvicorn.middleware.proxy_headers import (  # noqa: E402
    ProxyHeadersMiddleware,  # starlette doesn't ship this middleware
)

from lawboi.api.errors import register_exception_handlers  # noqa: E402
from lawboi.api.limiter import limiter  # noqa: E402
from lawboi.config.settings import load_settings  # noqa: E402

_settings = load_settings()

app = FastAPI(title="ParagrahvAI API", version="0.2.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]  # slowapi types handler as (Request, RateLimitExceeded) but FastAPI expects (Request, Exception)

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
