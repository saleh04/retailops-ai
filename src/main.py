from contextlib import asynccontextmanager

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from routes import analysis, base, connections, schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    
    # Internal postgresql DB
    postgres_conn = f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DATABASE}"
    app.state.db_engine = create_async_engine(postgres_conn, pool_pre_ping=True)
    app.state.db_client = async_sessionmaker(
        bind=app.state.db_engine, class_=AsyncSession, expire_on_commit=False)
    
    # External BB manager
    app.state.db_manager = None

    try:
        yield
    finally:
        manager = app.state.db_manager
        app.state.db_manager = None
        if manager is not None:
            manager.close()
            
        await app.state.db_engine.dispose()


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