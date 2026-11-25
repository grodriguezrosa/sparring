from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_conversation_store, get_voice_provider, get_voice_quota
from app.api.security import require_access_code
from app.schemas.voice import SIGNED_URL_TTL_SECONDS, VoiceSession, VoiceSessionRequest
from app.services.conversations import ConversationStore
from app.services.quota import DailyQuota, seconds_until_utc_midnight
from app.voice.base import VoiceProvider, VoiceProviderError

router = APIRouter(tags=["voice"])


@router.post("/voice-session")
async def create_voice_session(
    request: VoiceSessionRequest,
    response: Response,
    access_id: Annotated[str, Depends(require_access_code)],
    voice: Annotated[VoiceProvider, Depends(get_voice_provider)],
    quota: Annotated[DailyQuota, Depends(get_voice_quota)],
    conversations: Annotated[ConversationStore, Depends(get_conversation_store)],
) -> VoiceSession:
    """Start a voice interview that follows `plan`.

    Returns a single-use signed URL so the browser talks to the interviewer agent directly.
    The plan stays on the server, bound to the conversation id; the agent's custom LLM
    endpoint looks it up on every turn.
    """
    if not quota.try_consume(access_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily voice session limit reached for this access code.",
            headers={"Retry-After": str(seconds_until_utc_midnight())},
        )
    try:
        conversation = await voice.create_conversation()
    except VoiceProviderError:
        quota.refund(access_id)  # a provider failure must not cost the user an attempt
        raise

    conversations.start(conversation.conversation_id, plan=request.plan, access_id=access_id)
    # The signed URL works like a short-lived credential: never let anything cache it.
    response.headers["Cache-Control"] = "no-store"
    return VoiceSession(
        signed_url=conversation.signed_url,
        conversation_id=conversation.conversation_id,
        expires_in_seconds=SIGNED_URL_TTL_SECONDS,
    )
