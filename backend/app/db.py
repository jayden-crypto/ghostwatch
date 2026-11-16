"""Database engine and the per-request session dependency."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def new_session() -> Session:
    """A session for work outside a request (background tasks, the sweeper). The caller closes it."""
    return Session(get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """`with session_scope() as session:` for background work; the session is closed on exit."""
    with new_session() as session:
        yield session


def get_session() -> Iterator[Session]:
    with new_session() as session:
        yield session
