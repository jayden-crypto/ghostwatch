"""Dependencies shared by the API routers."""

import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="IngestionKey",
    description="The ingestion key (`GHOSTWATCH_API_KEY`). Required by the endpoints an SDK writes to.",
)


def require_api_key(
    settings: SettingsDep, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> None:
    """Guard for ingestion endpoints: `Authorization: Bearer <GHOSTWATCH_API_KEY>`."""
    expected = settings.ghostwatch_api_key.encode()
    if credentials is None or not secrets.compare_digest(credentials.credentials.encode(), expected):
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
