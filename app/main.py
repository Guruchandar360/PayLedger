from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.config import CURRENCIES, database_url
from app.db import make_engine
from app.errors import DomainError
from app.routes import router

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def create_app(url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(url or database_url())
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(SCHEMA_PATH.read_text(encoding="utf-8"))
                connection.execute(
                    text(
                        "INSERT INTO accounts (owner, currency, is_internal) "
                        "VALUES ('**FUNDING**', :currency, true) ON CONFLICT DO NOTHING"
                    ),
                    [{"currency": currency} for currency in CURRENCIES],
                )
            app.state.sessions = sessionmaker(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="PayLedger", lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(error.body, status_code=error.status)

    return app


app = create_app()
