import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


def require_access_code(
    settings: Annotated[Settings, Depends(get_settings)],
    x_access_code: Annotated[str | None, Header()] = None,
) -> str:
    """Reject the request unless it carries a valid X-Access-Code header.

    Returns a short, non-reversible id of the code, used as the key for per-code quotas,
    so the code itself is never stored anywhere else.
    """
    if x_access_code is None or not _is_valid(x_access_code, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid access code.",
        )
    return hashlib.sha256(x_access_code.encode()).hexdigest()[:16]


def _is_valid(candidate: str, settings: Settings) -> bool:
    # compare_digest takes the same time wherever the first difference is, so response
    # times do not reveal how much of a guessed code was right.
    return any(
        secrets.compare_digest(candidate.encode(), code.get_secret_value().encode())
        for code in settings.access_codes
    )
