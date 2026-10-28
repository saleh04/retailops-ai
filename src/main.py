from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference

from routes import base

app = FastAPI()
@app.get("/scalar", include_in_schema=False)
def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title="Scalar API"
    )
    
app.include_router(base.base_router)