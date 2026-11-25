"""Custom LLM endpoint for the ElevenLabs agent (ADR 0002).

ElevenLabs calls it on every turn of a voice interview with the conversation so far. We
find the interview plan for that conversation, build our own interviewer prompt and stream
DeepSeek's reply back in the OpenAI Chat Completions streaming format (SSE).
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_conversation_store, get_llm
from app.api.security import require_agent_llm_secret
from app.llm.base import LLMClient, LLMProviderError
from app.schemas.agent_llm import ChatCompletionRequest
from app.services.conversations import ConversationStore
from app.services.interviewer import build_interviewer_messages, conversation_id_from

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-llm"], dependencies=[Depends(require_agent_llm_secret)])


@router.post("/v1/chat/completions")
async def agent_chat_completions(
    request: ChatCompletionRequest,
    llm: Annotated[LLMClient, Depends(get_llm)],
    conversations: Annotated[ConversationStore, Depends(get_conversation_store)],
) -> StreamingResponse:
    """Next interviewer turn for a conversation started with POST /voice-session."""
    conversation_id = conversation_id_from(request.messages)
    session = conversations.get(conversation_id) if conversation_id else None
    if session is None:
        # Fail closed: no plan, no interviewer.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown or expired conversation.")

    elapsed_minutes = int((conversations.now() - session.started_at).total_seconds() // 60)
    messages = build_interviewer_messages(
        session.plan, request.messages, elapsed_minutes=elapsed_minutes
    )
    chunks = llm.stream(messages=messages)

    # Wait for the first piece of text BEFORE answering, so that a provider that is down
    # still gets a proper 503. Once the 200 and the headers are sent, it is too late.
    try:
        first = await anext(chunks)
    except StopAsyncIteration:
        first = ""

    return StreamingResponse(
        _sse(first, chunks, model=request.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


async def _sse(first: str, rest: AsyncIterator[str], *, model: str) -> AsyncIterator[str]:
    """Format the reply as OpenAI chat.completion.chunk events, ending with [DONE]."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    def event(delta: dict[str, str], finish_reason: str | None = None) -> str:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    try:
        yield event({"role": "assistant", "content": first})
        async for text in rest:
            yield event({"content": text})
    except LLMProviderError as error:
        # Mid-reply failure: the status is already sent. End the turn cleanly so the agent
        # can carry on; never log the conversation itself.
        logger.warning("LLM stream failed mid-reply: %s", type(error).__name__)
    finally:
        # If ElevenLabs hangs up (the candidate interrupted), stop paying for tokens.
        if isinstance(rest, AsyncGenerator):
            await rest.aclose()
    yield event({}, finish_reason="stop")
    yield "data: [DONE]\n\n"
