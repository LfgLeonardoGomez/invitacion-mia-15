"""FastAPI endpoints. Run one API worker behind HTTPS; do not publish SQLite."""

from contextlib import asynccontextmanager
import logging
import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .database import ConfirmationConflictError, Database, NotFoundError, QuotaExceededError
from .models import (
    AdminInvitation,
    CreatedInvitation,
    EventData,
    HealthResponse,
    InvitationCreate,
    InvitationPatch,
    InvitationResponse,
    RotatedToken,
    RsvpData,
    RsvpInput,
)
from .security import SecurityMiddleware, require_admin


logger = logging.getLogger(__name__)


def get_database(request: Request) -> Database:
    return request.app.state.database


DatabaseDep = Annotated[Database, Depends(get_database)]
InvitationId = Annotated[UUID, Path()]
InvitationToken = Annotated[str, Path()]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_environment()
    database = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await run_in_threadpool(database.initialize)
        yield

    application = FastAPI(
        title="Invitación de Mia — API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.enable_docs else None,
        debug=False,
        # Public links and family responses must not enter automatic trace/log exporters.
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
            "auto_configure": False,
        },
    )
    application.state.settings = settings
    application.state.database = database
    application.add_middleware(SecurityMiddleware)
    # Outermost CORS ensures rejected API requests also get an allowed origin's headers.
    if settings.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
            max_age=600,
        )

    @application.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exception: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Invitación no encontrada."})

    @application.exception_handler(QuotaExceededError)
    async def quota_handler(request: Request, exception: QuotaExceededError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "La cantidad de asistentes supera el cupo reservado."})

    @application.exception_handler(ConfirmationConflictError)
    async def confirmation_conflict_handler(request: Request, exception: ConfirmationConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "El cupo no puede ser menor que la confirmación existente."})

    @application.exception_handler(sqlite3.OperationalError)
    async def database_unavailable_handler(request: Request, exception: sqlite3.OperationalError) -> JSONResponse:
        # Never log database paths, token-bearing URLs, SQL inputs, or exception messages.
        logger.warning("Database unavailable (%s)", type(exception).__name__)
        return JSONResponse(status_code=503, content={"detail": "Servicio temporalmente no disponible."})

    public = APIRouter(prefix="/api", tags=["invitaciones"])
    admin = APIRouter(prefix="/api/admin", tags=["administración"], dependencies=[Depends(require_admin)])

    @public.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @public.get("/invitations/{token}")
    def read_invitation(token: InvitationToken, store: DatabaseDep) -> InvitationResponse:
        return store.get_public_invitation(token)

    @public.put("/invitations/{token}/rsvp")
    def replace_rsvp(token: InvitationToken, answer: RsvpInput, store: DatabaseDep) -> RsvpData:
        return store.save_rsvp(token, answer)

    @admin.get("/event")
    def read_event(store: DatabaseDep) -> EventData:
        return store.get_event()

    @admin.put("/event")
    def replace_event(event: EventData, store: DatabaseDep) -> EventData:
        return store.replace_event(event)

    @admin.post("/invitations", status_code=201)
    def create_invitation(invitation: InvitationCreate, store: DatabaseDep) -> CreatedInvitation:
        return store.create_invitation(invitation)

    @admin.get("/invitations")
    def list_invitations(
        store: DatabaseDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[AdminInvitation]:
        return store.list_invitations(limit=limit, offset=offset)

    @admin.patch("/invitations/{invitation_id}")
    def patch_invitation(invitation_id: InvitationId, changes: InvitationPatch, store: DatabaseDep) -> AdminInvitation:
        return store.patch_invitation(str(invitation_id), changes)

    @admin.post("/invitations/{invitation_id}/rotate-token")
    def rotate_invitation_token(invitation_id: InvitationId, store: DatabaseDep) -> RotatedToken:
        return store.rotate_token(str(invitation_id))

    application.include_router(public)
    application.include_router(admin)
    return application


app = create_app()
