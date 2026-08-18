import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_components, get_conversations
from ..schemas import ChatRequest, ChatResponse
from ...main import AppComponents

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    components: AppComponents = Depends(get_components),
    conversations: dict = Depends(get_conversations),
) -> ChatResponse:
    prior_history = conversations.get(body.conversation_id, [])
    try:
        result = await components.orchestrator.handle_query(body.message, history=prior_history)
    except (httpx.HTTPStatusError, httpx.RequestError):
        logger.exception("handle_query failed — LLM providers unavailable")
        raise HTTPException(status_code=503, detail="Answer generation is temporarily unavailable — try again.")

    assistant_content = result.clarification_question if result.needs_clarification else result.answer
    conversations[body.conversation_id] = prior_history + [
        {"role": "user", "content": body.message},
        {"role": "assistant", "content": assistant_content or ""},
    ]

    return ChatResponse(
        answer=result.answer,
        dropped_claims=result.dropped_claims,
        needs_clarification=result.needs_clarification,
        clarification_question=result.clarification_question,
    )
