from dataclasses import dataclass


@dataclass(frozen=True)
class Call:
    """Record of one call to FakeLLM, so tests can inspect it."""

    system: str
    user: str
    json_mode: bool


class FakeLLM:
    """Fake LLM for tests: returns canned responses, in order, without network."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[Call] = []

    async def complete(self, *, system: str, user: str, json_mode: bool = False) -> str:
        self.calls.append(Call(system=system, user=user, json_mode=json_mode))
        if not self._responses:
            raise RuntimeError("FakeLLM ran out of canned responses")
        return self._responses.pop(0)
