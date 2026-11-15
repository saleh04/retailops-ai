import logging

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

    def analyze(self, question: str, history: list[dict] | None = None):
        try:
            result = AnalysisService(self._manager).analyze(
                question,
                history=history,
            )

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
    
        return result