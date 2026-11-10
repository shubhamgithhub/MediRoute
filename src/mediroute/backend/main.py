"""MediRoute FastAPI application.

This module only assembles the app. Endpoints live in:
  * Step 1   - mediroute.specialty_routing.api       (patient input -> suggested speciality)
  * Step 2   - mediroute.hospital_recommendation.api (speciality -> ranked hospitals)
  * Workflow - mediroute.backend.workflow.api        (/api/patient-routing: Step 1 + Step 2, LangGraph)
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from mediroute.utils.logging_config import configure_logger
from mediroute.utils.paths import LOG_DIR

logger = configure_logger()

from mediroute.backend.workflow.api import router as workflow_router  # noqa: E402
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


def _mark_file_schema(prop: dict) -> None:
    """Make an upload field `format: binary`, including inside nullable anyOf/oneOf."""
    for union_name in ("anyOf", "oneOf"):
        if union_name in prop:
            for variant in prop[union_name]:
                if isinstance(variant, dict):
                    _mark_file_schema(variant)
            return
    if prop.get("type") == "array":
        items = prop.setdefault("items", {})
        if isinstance(items, dict):
            items["type"] = "string"
            items["format"] = "binary"
            items.pop("contentEncoding", None)
            items.pop("contentMediaType", None)
    elif prop.get("type") == "string":
        prop["format"] = "binary"
        prop.pop("contentEncoding", None)
        prop.pop("contentMediaType", None)


def custom_openapi():
    """Show multipart `files` fields as file pickers in Swagger UI.

    From Shubham's Step 12 main.py: FastAPI/Pydantic may emit contentEncoding/contentMediaType
    instead of format=binary, also inside nullable anyOf (optional uploads)."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    components = schema.get("components", {}).get("schemas", {})
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            multipart = operation.get("requestBody", {}).get("content", {}).get("multipart/form-data")
            if not multipart:
                continue
            body = multipart.get("schema", {})
            ref = body.get("$ref")
            target = components.get(ref.rsplit("/", 1)[-1], {}) if ref else body
            file_prop = target.get("properties", {}).get("files")
            if isinstance(file_prop, dict):
                _mark_file_schema(file_prop)
    app.openapi_schema = schema
    return schema


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
app.include_router(workflow_router)


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
