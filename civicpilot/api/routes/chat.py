import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

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


@router.post("/chat/stream")
async def post_chat_stream(
    body: ChatRequest,
    components: AppComponents = Depends(get_components),
    conversations: dict = Depends(get_conversations),
) -> StreamingResponse:
    prior_history = conversations.get(body.conversation_id, [])

    async def event_source():
        try:
            async for event in components.orchestrator.handle_query_stream(body.message, history=prior_history):
                if event["type"] == "answer":
                    assistant_content = event["clarification_question"] if event["needs_clarification"] else event["answer"]
                    conversations[body.conversation_id] = prior_history + [
                        {"role": "user", "content": body.message},
                        {"role": "assistant", "content": assistant_content or ""},
                    ]
                yield f"data: {json.dumps(event)}\n\n"
        except (httpx.HTTPStatusError, httpx.RequestError):
            # A StreamingResponse has already sent its 200 status and headers
            # by the time an LLM provider fails mid-loop, so there's no HTTP
            # status code left to change — the client learns about the
            # failure through an error event instead.
            logger.exception("handle_query_stream failed — LLM providers unavailable")
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Answer generation is temporarily unavailable — try again.'})}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
