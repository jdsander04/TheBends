from fastapi import FastAPI

from .routers import roads, routes

app = FastAPI(title="TheBends API", version="0.1.0")

app.include_router(roads.router, prefix="/api/v1")
app.include_router(routes.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
