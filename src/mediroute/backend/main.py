"""MediRoute FastAPI application.

This module only assembles the app. Endpoints live in the two pipeline modules:
  * Step 1 - mediroute.specialty_routing.api       (patient input -> specialty)
  * Step 2 - mediroute.hospital_recommendation.api (specialty -> ranked hospitals)
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from mediroute.utils.logging_config import configure_logger
from mediroute.utils.paths import LOG_DIR

logger = configure_logger()

from mediroute.hospital_recommendation.api import router as hospital_recommendation_router  # noqa: E402
from mediroute.specialty_routing.api import router as specialty_routing_router  # noqa: E402

logger.info("MediRoute backend logging initialized at %s", LOG_DIR / "mediroute.log")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Build the Step 1 router once and load the LLM in the background, so the first
    patient request is not slow and health checks answer immediately."""
    from mediroute.specialty_routing.service import get_service

    threading.Thread(target=get_service().warm_up, daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="MediRoute API",
    description="Backend API for the MediRoute hospital routing application",
    version="1.0.0",
)


def custom_openapi():
    """Render file-upload fields as binary so Swagger UI shows a file picker."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schemas = openapi_schema.get("components", {}).get("schemas", {})
    for schema in schemas.values():
        for prop in schema.get("properties", {}).values():
            # Single file
            if prop.get("contentMediaType") == "application/octet-stream":
                prop.pop("contentMediaType", None)
                prop["format"] = "binary"
            # Multiple files
            items = prop.get("items", {})
            if items.get("contentMediaType") == "application/octet-stream":
                items.pop("contentMediaType", None)
                items["format"] = "binary"

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(specialty_routing_router)
app.include_router(hospital_recommendation_router)


@app.get("/", tags=["Service"])
def root():
    return {"message": "Welcome to the MediRoute API!"}


@app.get("/api/health", tags=["Service"])
def health_check():
    return {"status": "healthy", "service": "MediRoute API"}


def run() -> None:
    """Entry point for the `mediroute-api` console script."""
    import os

    import uvicorn

    uvicorn.run(
        "mediroute.backend.main:app",
        host=os.getenv("MEDIROUTE_HOST", "127.0.0.1"),
        port=int(os.getenv("MEDIROUTE_PORT", "8000")),
    )


if __name__ == "__main__":
    run()
