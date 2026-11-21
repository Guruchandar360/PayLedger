import os
import socket
import threading
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import anyio
import httpx
import pytest
import uvicorn
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.config import DEFAULT_DATABASE_URL
from app.db import make_engine
from app.main import create_app


@pytest.fixture(scope="session")
def database():
    default_test_url = make_url(DEFAULT_DATABASE_URL).set(database="payledger_test")
    url = make_url(os.environ["TEST_DATABASE_URL"]) if "TEST_DATABASE_URL" in os.environ else default_test_url
    if url.database != "payledger_test":
        pytest.fail("TEST_DATABASE_URL must point to the dedicated payledger_test database")
    engine = make_engine(url.render_as_string(hide_password=False))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def app(database):
    schema = f"test_{uuid4().hex}"
    with database.begin() as connection:
        connection.execute(CreateSchema(schema))
    url = database.url.update_query_dict({"options": f"-csearch_path={schema}"})
    try:
        yield create_app(url.render_as_string(hide_password=False))
    finally:
        with database.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))


@pytest.fixture
def live_url(app):
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        # Run all 50 synchronous handlers concurrently with independent sessions.
        anyio.to_thread.current_default_thread_limiter().total_tokens = 60
        async with original_lifespan(application):
            yield

    app.router.lifespan_context = lifespan
    server = uvicorn.Server(
        uvicorn.Config(app, workers=1, log_level="error", access_log=False, ws="none")
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started, "Uvicorn did not start"
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "Uvicorn did not stop"


@pytest.fixture
def client(live_url):
    # Uvicorn closes the connection after an unhandled exception.
    limits = httpx.Limits(max_keepalive_connections=0)
    with httpx.Client(base_url=live_url, timeout=30, trust_env=False, limits=limits) as client:
        yield client
