import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from controllers import AnalysisController
from core.config import get_settings
from database.connection import DatabaseConnectionManager
from database.repositories import ConversationRepository
from models.pydantic_schemas import AnalysisRequest, AnalysisResponse
from routes.dependencies import get_db_manager, get_internal_db

logger = logging.getLogger(__name__)

analysis_router = APIRouter(
    prefix="/api/v1/analysis",
    tags=["Analysis"],
)


@analysis_router.post("", response_model=AnalysisResponse)
async def analyze(payload: AnalysisRequest, request: Request, response: Response,
                manager: DatabaseConnectionManager = Depends(get_db_manager),  # noqa: B008
                db: AsyncSession = Depends(get_internal_db)):  # noqa: B008

    connection_id = request.app.state.connection_id
    if connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active database connection is not registered.",
        )

    conversations = ConversationRepository(db)

    try:
        if payload.conversation_id is None:
            conversation = await conversations.create(connection_id, payload.question)
        else:
            conversation = await conversations.get(payload.conversation_id)
            if conversation is None or conversation.connection_id != connection_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found.",
                )

        history = await conversations.build_agent_history(
            conversation.id,
            get_settings().CHAT_HISTORY_LIMIT,
        )
        conversation_id = conversation.id
        
        await db.commit()

        controller = AnalysisController(manager)
        
        result = await run_in_threadpool(
            controller.analyze,
            payload.question,
            history,
        )
        result = result.model_copy(update={"conversation_id": conversation_id})

        await conversations.save_turn(conversation_id, payload.question, result)
        await db.commit()
        
    except HTTPException:
        await db.rollback()
        raise
    
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("Failed to persist analysis conversation.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save conversation.",
        ) from None

    response.status_code = (
        status.HTTP_500_INTERNAL_SERVER_ERROR
        if result.status == "failed"
        else status.HTTP_200_OK
    )
    return result