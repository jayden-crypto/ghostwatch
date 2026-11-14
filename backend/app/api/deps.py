"""Dependencies shared by the API routers."""

import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Annotated

from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session, session_scope
from app.errors import ApiError

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def get_session_factory() -> Callable[[], AbstractContextManager[Session]]:
    """How background tasks get a session of their own, after the request's session is gone."""
    return session_scope


SessionFactoryDep = Annotated[Callable[[], AbstractContextManager[Session]], Depends(get_session_factory)]


def require_api_key(settings: SettingsDep, authorization: Annotated[str | None, Header()] = None) -> None:
    """Guard for ingestion endpoints: `Authorization: Bearer <GHOSTWATCH_API_KEY>`."""
    expected = f"Bearer {settings.ghostwatch_api_key}"
    if authorization is None or not secrets.compare_digest(authorization.encode(), expected.encode()):
        raise ApiError(401, "unauthorized", "Missing or invalid API key.")


class PageParams:
    """Contract §0 pagination: `limit` (default 50, max 200) and `offset` (default 0)."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PageDep = Annotated[PageParams, Depends()]
