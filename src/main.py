from contextlib import asynccontextmanager

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference

from routes import analysis, base, connections, schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_manager = None

    try:
        yield
    finally:
        manager = app.state.db_manager
        app.state.db_manager = None

        if manager is not None:
            manager.close()


app = FastAPI(lifespan=lifespan)

@app.get("/scalar", include_in_schema=False)
def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title="Scalar API"
    )
    
app.include_router(base.base_router)
app.include_router(connections.connections_router)
app.include_router(schema.schema_router)
app.include_router(analysis.analysis_router)