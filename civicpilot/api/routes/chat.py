from fastapi import APIRouter, Depends

from ..deps import get_components, get_conversations
from ..schemas import ChatRequest, ChatResponse
from ...main import AppComponents

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    components: AppComponents = Depends(get_components),
    conversations: dict = Depends(get_conversations),
) -> ChatResponse:
    prior_history = conversations.get(body.conversation_id, [])
    result = await components.orchestrator.handle_query(body.message, history=prior_history)

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
