import asyncio
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from .auth_service import auth_service
from .config import PRODUCT_FILE_PATH, TEMPLATES_DIR
from .event_bus import event_bus
from .failover import failover_controller
from .replication_service import replication_service
from .resource_service import resource_service
from .session_manager import session_manager

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Looks up the current session from a tab token first, then from the fallback cookie.
def current_user(session_token: str | None, cookie_session: str | None = None):
    session = session_manager.get(session_token or cookie_session)
    if not session:
        raise HTTPException(status_code=401, detail="Not logged in")
    return session


# Rejects normal client operations when this process is a passive standby.
def ensure_active_node() -> None:
    if not failover_controller.accepts_client_requests():
        raise HTTPException(
            status_code=503,
            detail="This standby node is passive. Connect through the failover gateway.",
        )


@router.get("/", response_class=HTMLResponse)
# Shows the login page used by each browser tab/client node.
async def login_page(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.post("/login")
# Validates credentials, creates a client session, and redirects to the dashboard.
async def login(username: str = Form(...), password: str = Form(...)):
    # - HTTP request from client node to server node.
    # - AuthService checks SQLite.
    # - SessionManager records the active client node.
    if not failover_controller.accepts_client_requests():
        return RedirectResponse(
            "/?error=This standby node is passive. Connect through the failover gateway.",
            status_code=303,
        )

    if not auth_service.validate_user(username, password):
        return RedirectResponse("/?error=Invalid username or password", status_code=303)

    session = session_manager.create_session(username)
    if not session:
        return RedirectResponse("/?error=User is already connected on another client node", status_code=303)

    query = urlencode({"session_id": session.session_id})
    response = RedirectResponse(f"/dashboard?{query}", status_code=303)
    response.set_cookie("distres_session", session.session_id, httponly=True, samesite="lax")
    replication_service.replicate_state(sessions=session_manager.export_sessions())
    await event_bus.publish("client_connected", {"username": username})
    return response


@router.post("/logout")
# Ends a client session, releases any locks owned by that user, and returns to login.
async def logout(
    session_id: str | None = Form(default=None),
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    session_token = session_id or x_distres_session or distres_session
    username = session_manager.remove(session_token)
    if username:
        # Release any read/write locks owned by the logging-out user.
        resource_service.finish_read(username)
        resource_service.finish_write(username)
        replication_service.replicate_state(sessions=session_manager.export_sessions())
        await event_bus.publish("client_disconnected", {"username": username})

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("distres_session")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
# Shows the dashboard for the session token belonging to this browser tab.
async def dashboard(
    request: Request,
    session_id: str | None = Query(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    session_token = session_id or distres_session
    session = session_manager.get(session_token)
    if not session:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"username": session.username, "session_token": session_token},
    )


@router.get("/api/state")
# Returns the shared system state used by the dashboard polling loop.
async def state():
    return JSONResponse(_state_payload())


@router.get("/api/me")
# Returns the username for the current authenticated client node.
async def me(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    session = current_user(x_distres_session, distres_session)
    return {"username": session.username}


# Builds one dictionary containing sessions, resource locks, and server health.
def _state_payload() -> dict:
    return {
        "sessions": session_manager.active_users(),
        "resource": resource_service.status(),
        "health": failover_controller.health(),
    }


@router.post("/api/read/start")
# Requests a read lock and returns the file content when reading is allowed.
async def start_read(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    session = current_user(x_distres_session, distres_session)
    granted, message, content = resource_service.start_read(session.username)
    await event_bus.publish("reader_active", _state_payload())
    return {"granted": granted, "message": message, "content": content, "state": _state_payload()}


@router.post("/api/read/finish")
# Releases the current user's read lock and publishes the updated lock state.
async def finish_read(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    session = current_user(x_distres_session, distres_session)
    resource_service.finish_read(session.username)
    await event_bus.publish("reader_released", _state_payload())
    return {"ok": True, "state": _state_payload()}


@router.post("/api/write/request")
# Requests exclusive write access or queues the user behind active readers/writers.
async def request_write(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    # - The client requests write access from the server.
    # - Server either grants the writer role or queues the client.
    # - Pub-sub broadcasts writer status to every active client.
    session = current_user(x_distres_session, distres_session)
    status, message, content = resource_service.request_write(session.username)
    await event_bus.publish("writer_active", _state_payload())
    return {"status": status, "message": message, "content": content, "state": _state_payload()}


@router.post("/api/write/save")
# Saves edited file content when the current user owns the write lock.
async def save_write(
    content: str = Form(...),
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    session = current_user(x_distres_session, distres_session)
    ok, message = resource_service.save_write(session.username, content)
    if ok:
        await event_bus.publish(
            "file_updated",
            {"updated_by": session.username, "message": message, "state": _state_payload()},
        )
    return {"ok": ok, "message": message, "state": _state_payload()}


@router.post("/api/write/finish")
# Releases the current user's write lock and publishes the updated lock state.
async def finish_write(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_active_node()
    session = current_user(x_distres_session, distres_session)
    ok = resource_service.finish_write(session.username)
    await event_bus.publish("writer_released", _state_payload())
    return {"ok": ok, "state": _state_payload()}


@router.post("/internal/replicate/state")
# Receives primary-to-standby replicated resource and session state.
async def receive_replicated_state(request: Request):
    payload = await request.json()

    product_content = payload.get("product_content")
    if product_content is not None:
        PRODUCT_FILE_PATH.write_text(product_content, encoding="utf-8")

    sessions = payload.get("sessions")
    if sessions is not None:
        session_manager.replace_sessions(sessions)

    return {
        "ok": True,
        "node": failover_controller.health(),
        "replicated_product": product_content is not None,
        "replicated_sessions": sessions is not None,
    }


@router.post("/internal/promote")
# Promotes a passive standby after the gateway detects primary failure.
async def promote_internal():
    status = failover_controller.promote_standby()
    await event_bus.publish("server_failover", status)
    return status


@router.post("/internal/demote")
# Returns a standby node to passive mode during a manual reset.
async def demote_internal():
    status = failover_controller.restore_primary()
    await event_bus.publish("server_restored", status)
    return status


@router.get("/events")
# Opens the Server-Sent Events stream used for publish-subscribe notifications.
async def events(request: Request):
    # - Browser subscribes once.
    # - Server pushes events after login/logout/read/write/failover.
    # - UI updates without manual refresh.
    client_key = str(uuid.uuid4())
    queue = await event_bus.subscribe(client_key)

    # Streams queued PubSub messages to one browser until it disconnects.
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield event
                except asyncio.TimeoutError:
                    # Keep-alive comment so proxies/Replit do not close the stream silently.
                    yield ": keep-alive\n\n"
        finally:
            event_bus.unsubscribe(client_key)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/health")
# Returns active server health data for retry and failover UI checks.
async def health():
    return failover_controller.health()


@router.post("/api/failover/promote")
# Manually promotes this node; the real demo normally does this through the gateway.
async def promote_standby():
    status = failover_controller.promote_standby()
    await event_bus.publish("server_failover", status)
    return status


@router.post("/api/failover/restore")
# Restores the logical primary server after a failover demonstration.
async def restore_primary():
    status = failover_controller.restore_primary()
    await event_bus.publish("server_restored", status)
    return status
