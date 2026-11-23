from datetime import UTC, datetime, timedelta

from app.schemas.interview_plan import InterviewPlan
from app.services.conversations import SESSION_TTL, ConversationStore
from tests.plans import make_plan

START = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def test_returns_the_session_stored_for_a_conversation() -> None:
    store = ConversationStore(clock=FakeClock())
    plan: InterviewPlan = make_plan()

    store.start("conv_1", plan=plan, access_id="code-a")

    session = store.get("conv_1")
    assert session is not None
    assert session.plan == plan
    assert session.access_id == "code-a"
    assert session.started_at == START


def test_unknown_conversation_returns_none() -> None:
    assert ConversationStore().get("conv_unknown") is None


def test_sessions_expire_after_the_ttl() -> None:
    clock = FakeClock()
    store = ConversationStore(clock=clock)
    store.start("conv_1", plan=make_plan(), access_id="code-a")

    clock.now = START + SESSION_TTL - timedelta(seconds=1)
    assert store.get("conv_1") is not None

    clock.now = START + SESSION_TTL
    assert store.get("conv_1") is None


def test_expired_sessions_are_removed_from_memory() -> None:
    clock = FakeClock()
    store = ConversationStore(clock=clock)
    store.start("conv_old", plan=make_plan(), access_id="code-a")

    clock.now = START + SESSION_TTL
    store.start("conv_new", plan=make_plan(), access_id="code-a")

    assert len(store) == 1
