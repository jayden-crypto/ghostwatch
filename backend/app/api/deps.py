"""Dependencies shared by the API routers."""

import secrets
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.errors import ApiError

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def require_api_key(settings: SettingsDep, authorization: Annotated[str | None, Header()] = None) -> None:
    """Guard for ingestion endpoints: `Authorization: Bearer <GHOSTWATCH_API_KEY>`."""
    expected = f"Bearer {settings.ghostwatch_api_key}"
    if authorization is None or not secrets.compare_digest(authorization.encode(), expected.encode()):
        raise ApiError(401, "unauthorized", "Missing or invalid API key.")
