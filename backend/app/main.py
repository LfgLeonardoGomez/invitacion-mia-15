"""FastAPI endpoints. Run one API worker behind HTTPS; do not publish SQLite."""

from contextlib import asynccontextmanager
import logging
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .database import ConfirmationConflictError, Database, MAX_WISHES_PER_INVITATION, NotFoundError, QuotaExceededError, WishConflictError, WishLimitError
from .link_crypto import LegacyLinkError, LinkUnavailableError
from .models import (
    AdminInvitation,
    AdminSummary,
    AdminWish,
    CreatedInvitation,
    EventData,
    HealthResponse,
    InvitationCreate,
    InvitationPatch,
    InvitationResponse,
    RotatedToken,
    RsvpData,
    RsvpInput,
    SectionsData,
    WishData,
    WishInput,
)
from .security import ADMIN_SESSION_COOKIE, ADMIN_SESSION_LIFETIME, SecurityMiddleware, admin_key, key_fingerprint, local_session_cookie, require_admin, require_admin_session, require_bootstrap_key


logger = logging.getLogger(__name__)


def get_database(request: Request) -> Database:
    return request.app.state.database


DatabaseDep = Annotated[Database, Depends(get_database)]
InvitationId = Annotated[UUID, Path()]
InvitationToken = Annotated[str, Path()]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_environment()
    database = Database(settings.database_path, settings.link_encryption_key)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await run_in_threadpool(database.initialize)
        yield

    application = FastAPI(
        title="Invitación de Mia — API",
        version="0.4.0",
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
    application.add_middleware(SecurityMiddleware, admin_read_limit=120)
    # Outermost CORS ensures rejected API requests also get an allowed origin's headers.
    if settings.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
            allow_credentials=True,
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

    @application.exception_handler(WishConflictError)
    async def wish_conflict_handler(request: Request, exception: WishConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "La solicitud de deseo ya fue utilizada con otro contenido."})

    @application.exception_handler(WishLimitError)
    async def wish_limit_handler(request: Request, exception: WishLimitError) -> JSONResponse:
        return JSONResponse(status_code=409, content={
            "detail": "Esta invitación alcanzó el límite de deseos.",
            "code": "wish_limit_reached",
            "maxWishes": MAX_WISHES_PER_INVITATION,
        })

    @application.exception_handler(LegacyLinkError)
    async def legacy_link_handler(request: Request, exception: LegacyLinkError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "El enlace anterior no es recuperable. Regenerarlo invalida el enlace anterior, sin borrar confirmaciones ni deseos."})

    @application.exception_handler(LinkUnavailableError)
    async def link_unavailable_handler(request: Request, exception: LinkUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "El servicio de enlaces no está disponible."})

    @application.exception_handler(sqlite3.OperationalError)
    async def database_unavailable_handler(request: Request, exception: sqlite3.OperationalError) -> JSONResponse:
        # Never log database paths, token-bearing URLs, SQL inputs, or exception messages.
        logger.warning("Database unavailable (%s)", type(exception).__name__)
        return JSONResponse(status_code=503, content={"detail": "Servicio temporalmente no disponible."})

    public = APIRouter(prefix="/api", tags=["invitaciones"])
    admin = APIRouter(prefix="/api/admin", tags=["administración"], dependencies=[Depends(require_admin)])
    sessions = APIRouter(prefix="/api/admin", tags=["sesión"])

    @sessions.post("/session", dependencies=[Depends(require_bootstrap_key)])
    def create_session(request: Request, response: Response, store: DatabaseDep) -> dict:
        previous = request.cookies.get(ADMIN_SESSION_COOKIE)
        if previous:
            store.revoke_admin_session(previous)
        token, session = store.create_admin_session(key_fingerprint(admin_key(request)))
        cookie_path = request.scope.get("root_path", "").rstrip("/") + "/api/admin"
        response.set_cookie(ADMIN_SESSION_COOKIE, token, max_age=ADMIN_SESSION_LIFETIME, httponly=True,
                            secure=not local_session_cookie(request), samesite="strict", path=cookie_path)
        return {"authenticated": True, **session}

    @sessions.get("/session")
    def read_session(session: Annotated[dict[str, str], Depends(require_admin_session)]) -> dict:
        return {"authenticated": True, **session}

    @sessions.delete("/session", dependencies=[Depends(require_admin_session)])
    def delete_session(request: Request, response: Response, store: DatabaseDep) -> dict:
        store.revoke_admin_session(request.cookies[ADMIN_SESSION_COOKIE])
        cookie_path = request.scope.get("root_path", "").rstrip("/") + "/api/admin"
        response.delete_cookie(ADMIN_SESSION_COOKIE, path=cookie_path, httponly=True,
                               secure=not local_session_cookie(request), samesite="strict")
        return {"authenticated": False}

    @public.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @public.get("/invitations/{token}")
    def read_invitation(token: InvitationToken, store: DatabaseDep) -> InvitationResponse:
        return store.get_public_invitation(token)

    @public.put("/invitations/{token}/rsvp")
    def replace_rsvp(token: InvitationToken, answer: RsvpInput, store: DatabaseDep) -> RsvpData:
        return store.save_rsvp(token, answer)

    @public.post("/invitations/{token}/wishes", status_code=201)
    def create_wish(token: InvitationToken, wish: WishInput, store: DatabaseDep) -> WishData:
        return store.save_wish(token, wish)

    @admin.get("/event")
    def read_event(store: DatabaseDep) -> EventData:
        return store.get_event()

    @admin.put("/event")
    def replace_event(event: EventData, store: DatabaseDep) -> EventData:
        return store.replace_event(event)

    @admin.get("/sections")
    def read_sections(store: DatabaseDep) -> SectionsData:
        return store.get_sections()

    @admin.put("/sections")
    def replace_sections(sections: SectionsData, store: DatabaseDep) -> SectionsData:
        return store.replace_sections(sections)

    @admin.get("/summary")
    def read_summary(store: DatabaseDep) -> AdminSummary:
        return store.summary()

    @admin.get("/wishes")
    def read_wishes(
        store: DatabaseDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        q: Annotated[str, Query(max_length=120)] = "",
    ) -> list[AdminWish]:
        return store.list_wishes(limit=limit, offset=offset, q=q.strip())

    @admin.post("/invitations", status_code=201)
    def create_invitation(invitation: InvitationCreate, store: DatabaseDep) -> CreatedInvitation:
        return store.create_invitation(invitation)

    @admin.get("/invitations")
    def list_invitations(
        store: DatabaseDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        status: Annotated[Literal["all", "active", "inactive", "confirmed", "declined", "pending"], Query()] = "all",
        q: Annotated[str, Query(max_length=120)] = "",
    ) -> list[AdminInvitation]:
        return store.list_invitations(limit=limit, offset=offset, status=status, q=q.strip())

    @admin.patch("/invitations/{invitation_id}")
    def patch_invitation(invitation_id: InvitationId, changes: InvitationPatch, store: DatabaseDep) -> AdminInvitation:
        return store.patch_invitation(str(invitation_id), changes)

    @admin.post("/invitations/{invitation_id}/rotate-token")
    def rotate_invitation_token(invitation_id: InvitationId, store: DatabaseDep) -> RotatedToken:
        return store.rotate_token(str(invitation_id))

    @admin.get("/invitations/{invitation_id}/link")
    def recover_invitation_link(invitation_id: InvitationId, store: DatabaseDep) -> RotatedToken:
        return store.recover_link(str(invitation_id))

    application.include_router(public)
    application.include_router(sessions)
    application.include_router(admin)
    return application


app = create_app()
