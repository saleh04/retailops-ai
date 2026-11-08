import logging

from fastapi import status

from database.connection import DatabaseConnectionManager
from models.pydantic_schemas.analysis import (
    AnalysisMetadata,
    AnalysisResponse,
)
from services.analysis_service import AnalysisService

logger = logging.getLogger(__name__)


class AnalysisController:

    def __init__(self, manager: DatabaseConnectionManager):
        self._manager = manager

    def analyze(self, question: str):
        try:
            result = AnalysisService(self._manager).analyze(question)

        except Exception:
            logger.exception("Unexpected error while processing analysis request.")

            result = AnalysisResponse(
                status="failed",
                answer=None,
                queries=[],
                schema_results=[],
                metadata=AnalysisMetadata(
                    dialect=self._manager.database,
                    tools_used=[],
                ),
                error="Analysis failed.",
            )
            
        response_status = (
            status.HTTP_500_INTERNAL_SERVER_ERROR
            if result.status == "failed"
            else status.HTTP_200_OK
        )
    
        return result, response_status