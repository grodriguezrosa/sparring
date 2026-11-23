import json

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMClient

MAX_ATTEMPTS = 2  # first attempt plus one retry, as CLAUDE.md requires


class LLMOutputError(Exception):
    """The LLM did not return a response with the expected shape, even after retrying."""


async def generate_structured[T: BaseModel](
    llm: LLMClient, *, system: str, user: str, schema: type[T]
) -> T:
    """Ask the LLM for JSON shaped like `schema` and return it already validated."""
    json_schema = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    system_with_format = (
        f"{system}\n\n"
        "Reply ONLY with a valid JSON object, with no extra text, "
        f"that matches this JSON Schema:\n{json_schema}"
    )

    last_error: ValidationError | None = None
    for _ in range(MAX_ATTEMPTS):
        raw = await llm.complete(system=system_with_format, user=user, json_mode=True)
        try:
            return schema.model_validate_json(raw)
        except ValidationError as error:
            last_error = error

    raise LLMOutputError(
        f"The LLM did not return a valid {schema.__name__} after {MAX_ATTEMPTS} attempts"
    ) from last_error
