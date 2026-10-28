from fastapi import APIRouter, Depends

from core.config import Settings, get_settings

base_router = APIRouter(
    prefix="/api/v1",
    tags=["Health-Check"]
)

@base_router.get("/")
async def read_root(app_settings: Settings = Depends(get_settings)):    # noqa: B008
    
    app_name = app_settings.APP_NAME
    app_version = app_settings.APP_VERSION
    
    return {"message": f"Welcome to {app_name} version {app_version}!"}