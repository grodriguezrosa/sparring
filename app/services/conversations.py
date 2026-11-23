from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.schemas.interview_plan import InterviewPlan

# The browser has 15 minutes to start the conversation, and the agent cuts it at 35
# minutes (ElevenLabs dashboard). Two hours covers both with a wide margin.
SESSION_TTL = timedelta(hours=2)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class InterviewSession:
    """What the backend knows about one voice conversation."""

    conversation_id: str
    access_id: str  # hash of the access code that started it, never the code
    plan: InterviewPlan
    started_at: datetime


class ConversationStore:
    """Maps ElevenLabs conversation ids to their interview sessions, in memory.

    Same limits as DailyQuota: one backend instance, lost on restart. Moves to Postgres
    in phase 1. Sessions expire after SESSION_TTL so memory does not grow forever.
    """

    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._sessions: dict[str, InterviewSession] = {}

    def start(self, conversation_id: str, *, plan: InterviewPlan, access_id: str) -> None:
        self._remove_expired()
        self._sessions[conversation_id] = InterviewSession(
            conversation_id=conversation_id,
            access_id=access_id,
            plan=plan,
            started_at=self._clock(),
        )

    def get(self, conversation_id: str) -> InterviewSession | None:
        """The session for this conversation, or None if unknown or expired."""
        session = self._sessions.get(conversation_id)
        if session is None or self._is_expired(session):
            return None
        return session

    def __len__(self) -> int:
        return len(self._sessions)

    def _is_expired(self, session: InterviewSession) -> bool:
        return self._clock() - session.started_at >= SESSION_TTL

    def _remove_expired(self) -> None:
        expired = [cid for cid, session in self._sessions.items() if self._is_expired(session)]
        for conversation_id in expired:
            del self._sessions[conversation_id]
