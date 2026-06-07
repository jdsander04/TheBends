import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import roads, routes

app = FastAPI(title="TheBends API", version="0.1.0")

# CORS so the Flutter *web* build can call the API from another origin
# (e.g. Cloudflare Pages). Same-origin deploys behind Caddy don't need it, but
# it's harmless there. Set ALLOWED_ORIGINS="https://a.com,https://b.com" to lock
# it down; defaults to "*" (fine — the API is read-only and uses no credentials).
_origins_env = os.getenv("ALLOWED_ORIGINS", "*").strip()
_origins = ["*"] if _origins_env == "*" else [
    o.strip() for o in _origins_env.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(roads.router, prefix="/api/v1")
app.include_router(routes.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
