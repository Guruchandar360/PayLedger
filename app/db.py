from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_size=20, max_overflow=40, pool_pre_ping=True)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session
