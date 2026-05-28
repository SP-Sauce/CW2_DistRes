import asyncio
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from .auth_service import auth_service
from .config import PRODUCT_FILE_PATH, TEMPLATES_DIR
from .event_bus import event_bus
from .node_status import node_status
from .replication_service import replication_service
from .resource_service import resource_service
from .session_manager import session_manager

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
GATEWAY_HEADER_VALUE = "active-active-read-scaling-leader-election"


# Looks up the current session from a tab token first, then from the fallback cookie.
def current_user(session_token: str | None, cookie_session: str | None = None):
    session, _ = _current_session_from_tokens(session_token, cookie_session)
    if not session:
        raise HTTPException(status_code=401, detail="Not logged in")
    return session


def _current_session_from_tokens(*tokens: str | None):
    seen = set()
    for token in tokens:
        if not token or token in seen:
            continue
        seen.add(token)
        session = session_manager.get(token)
        if session:
            session_manager.touch(session.session_id)
            return session, session.session_id
    return None, None


def _is_leader_routed_write(
    x_distres_gateway: str | None,
    x_distres_routing_policy: str | None,
) -> bool:
    return (
        x_distres_gateway == GATEWAY_HEADER_VALUE
        and "leader-routed" in (x_distres_routing_policy or "")
    )


def ensure_leader_routed_write(
    x_distres_gateway: str | None,
    x_distres_routing_policy: str | None,
) -> None:
    if not _is_leader_routed_write(x_distres_gateway, x_distres_routing_policy):
        raise HTTPException(
            status_code=409,
            detail="Write request rejected: use the gateway so writes are routed to the Bully-elected leader.",
        )


@router.get("/", response_class=HTMLResponse)
# Shows the login page used by each browser tab/client node.
async def login_page(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.post("/login")
# Validates credentials, creates a client session, and redirects to the dashboard.
async def login(
    username: str = Form(...),
    password: str = Form(...),
    x_distres_gateway: str | None = Header(default=None),
    x_distres_routing_policy: str | None = Header(default=None),
):
    # - HTTP request from client node to server node.
    # - AuthService checks SQLite.
    # - SessionManager records the active client node.
    if not _is_leader_routed_write(x_distres_gateway, x_distres_routing_policy):
        return RedirectResponse(
            "/?error=Write request rejected. Connect through the gateway so login is routed to the elected leader.",
            status_code=303,
        )

    if not auth_service.validate_user(username, password):
        return RedirectResponse("/?error=Invalid username or password", status_code=303)

    session = session_manager.create_session(username)
    if not session:
        # Browser restarts can lose the session token while SQLite still has the user marked active.
        # A fresh valid login by the same username takes over that abandoned session.
        resource_service.finish_read(username)
        resource_service.finish_write(username)
        session_manager.remove_user(username)
        session = session_manager.create_session(username)
        if not session:
            return RedirectResponse("/?error=Could not create a fresh session", status_code=303)

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
    x_distres_gateway: str | None = Header(default=None),
    x_distres_routing_policy: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_leader_routed_write(x_distres_gateway, x_distres_routing_policy)
    session, valid_token = _current_session_from_tokens(session_id, x_distres_session, distres_session)
    username = session_manager.remove(valid_token or session_id or x_distres_session or distres_session)
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
    session, valid_token = _current_session_from_tokens(session_id, distres_session)
    if not session:
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie("distres_session")
        return response
    response = templates.TemplateResponse(
        request,
        "dashboard.html",
        {"username": session.username, "session_token": valid_token},
    )
    response.set_cookie("distres_session", valid_token, httponly=True, samesite="lax")
    return response


@router.get("/api/state")
# Returns the shared system state used by the dashboard polling loop.
async def state(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session, _ = _current_session_from_tokens(x_distres_session, distres_session)
    if session:
        resource_service.touch_read(session.username)
    return JSONResponse(_state_payload())


@router.get("/api/me")
# Returns the username for the current authenticated client node.
async def me(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session = current_user(x_distres_session, distres_session)
    return {"username": session.username}


# Builds one dictionary containing sessions, resource locks, and node health.
def _state_payload() -> dict:
    resource_status = resource_service.status()
    return {
        "sessions": session_manager.active_users(),
        "resource": resource_status,
        "distributed_write_lock": resource_status["distributed_write_lock"],
        "health": node_status.health(),
    }


@router.post("/api/read/start")
# Requests a read lock and returns the file content when reading is allowed.
async def start_read(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
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
    session = current_user(x_distres_session, distres_session)
    resource_service.finish_read(session.username)
    await event_bus.publish("reader_released", _state_payload())
    return {"ok": True, "state": _state_payload()}


@router.post("/api/write/request")
# Requests exclusive write access or queues the user behind active readers/writers.
async def request_write(
    x_distres_session: str | None = Header(default=None),
    x_distres_gateway: str | None = Header(default=None),
    x_distres_routing_policy: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_leader_routed_write(x_distres_gateway, x_distres_routing_policy)
    # - The client requests write access from the server.
    # - The gateway routes this request to the Bully-elected leader.
    # - The leader uses the database-backed distributed write lock as final guard.
    # - Pub-sub broadcasts writer status to every active client.
    session = current_user(x_distres_session, distres_session)
    status, message, content, lock_token = resource_service.request_write(session.username)
    await event_bus.publish("writer_active", _state_payload())
    return {
        "status": status,
        "message": message,
        "content": content,
        "lock_token": lock_token,
        "state": _state_payload(),
    }


@router.post("/api/write/save")
# Saves edited file content when the current user owns the write lock.
async def save_write(
    content: str = Form(...),
    lock_token: str | None = Form(default=None),
    x_distres_session: str | None = Header(default=None),
    x_distres_lock_token: str | None = Header(default=None),
    x_distres_gateway: str | None = Header(default=None),
    x_distres_routing_policy: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_leader_routed_write(x_distres_gateway, x_distres_routing_policy)
    session = current_user(x_distres_session, distres_session)
    submitted_token = lock_token or x_distres_lock_token
    ok, message = resource_service.save_write(session.username, content, submitted_token)
    if ok:
        await event_bus.publish(
            "file_updated",
            {"updated_by": session.username, "message": message, "state": _state_payload()},
        )
    return {"ok": ok, "message": message, "state": _state_payload()}


@router.post("/api/write/finish")
# Releases the current user's write lock and publishes the updated lock state.
async def finish_write(
    lock_token: str | None = Form(default=None),
    x_distres_session: str | None = Header(default=None),
    x_distres_lock_token: str | None = Header(default=None),
    x_distres_gateway: str | None = Header(default=None),
    x_distres_routing_policy: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    ensure_leader_routed_write(x_distres_gateway, x_distres_routing_policy)
    session = current_user(x_distres_session, distres_session)
    submitted_token = lock_token or x_distres_lock_token
    ok = resource_service.finish_write(session.username, submitted_token)
    await event_bus.publish("writer_released", _state_payload())
    return {"ok": ok, "state": _state_payload()}


@router.post("/internal/replicate/state")
# Receives replicated state when compatibility replication is enabled.
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
        "node": node_status.health(),
        "replicated_product": product_content is not None,
        "replicated_sessions": sessions is not None,
    }


@router.get("/internal/export/state")
# Exports full local state for inspection or compatibility replication.
async def export_replicated_state():
    return {
        "ok": True,
        "node": node_status.health(),
        "product_content": PRODUCT_FILE_PATH.read_text(encoding="utf-8"),
        "sessions": session_manager.export_sessions(),
    }


@router.get("/events")
# Opens the Server-Sent Events stream used for publish-subscribe notifications.
async def events(request: Request):
    # - Browser subscribes once.
    # - Server pushes events after login/logout/read/write/leader election.
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
# Returns node health data for gateway routing and election checks.
async def health():
    return node_status.health()
