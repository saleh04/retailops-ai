from fastapi import APIRouter, Depends, Response

from controllers.analysis_controller import AnalysisController
from database.connection import DatabaseConnectionManager
from models.pydantic_schemas.analysis import AnalysisResponse
from models.pydantic_schemas.requests import AnalysisRequest
from routes.dependencies import get_db_manager

analysis_router = APIRouter(
    prefix="/api/v1/analysis",
    tags=["Analysis"],
)


@analysis_router.post("", response_model=AnalysisResponse)
def analyze(payload: AnalysisRequest, response: Response,
            manager: DatabaseConnectionManager = Depends(get_db_manager)):  # noqa: B008
    
    result, response_status = AnalysisController(manager).analyze(payload.question)
     
    response.status_code = response_status
    
    return result 
    