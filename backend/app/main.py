from fastapi import FastAPI

from app.ingestion.router import router as ingestion_router


app = FastAPI(title="AI Clipper")
app.include_router(ingestion_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
