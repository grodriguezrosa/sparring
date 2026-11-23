from pydantic import BaseModel, Field

SIGNED_URL_TTL_SECONDS = 15 * 60  # documented by ElevenLabs


class VoiceSession(BaseModel):
    signed_url: str = Field(description="WebSocket URL the browser uses to talk to the agent")
    expires_in_seconds: int = Field(
        description="The conversation must start before the signed URL expires"
    )
