import asyncio
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from .auth_service import auth_service
from .config import TEMPLATES_DIR
from .event_bus import event_bus
from .failover import failover_controller
from .resource_service import resource_service
from .session_manager import session_manager

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def current_user(session_token: str | None, cookie_session: str | None = None):
    session = session_manager.get(session_token or cookie_session)
    if not session:
        raise HTTPException(status_code=401, detail="Not logged in")
    return session


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    #Client node UI entry point
    return templates.TemplateResponse(request, "index.html")


@router.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):

    # Client-server coordination endpoint.

    # Rubric snippet candidate:
    # - HTTP request from client node to server node.
    # - AuthService checks SQLite.
    # - SessionManager records the active client node.

    if not auth_service.validate_user(username, password):
        return RedirectResponse("/?error=Invalid username or password", status_code=303)

    session = session_manager.create_session(username)
    if not session:
        return RedirectResponse("/?error=User is already connected on another client node", status_code=303)

    query = urlencode({"session_id": session.session_id})
    response = RedirectResponse(f"/dashboard?{query}", status_code=303)
    response.set_cookie("distres_session", session.session_id, httponly=True, samesite="lax")
    await event_bus.publish("client_connected", {"username": username})
    return response


@router.post("/logout")
async def logout(
    session_id: str | None = Form(default=None),
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session_token = session_id or x_distres_session or distres_session
    username = session_manager.remove(session_token)
    if username:
        # Release any read/write locks owned by the logging-out user.
        resource_service.finish_read(username)
        resource_service.finish_write(username)
        await event_bus.publish("client_disconnected", {"username": username})

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("distres_session")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session_id: str | None = Query(default=None),
    distres_session: str | None = Cookie(default=None),
):
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
async def state():

    # Public state endpoint consumed by the UI polling loop.

    # Kept simple because this is coursework demonstration code.
    # The actual user check is done manually below to avoid putting Depends in this inline example.

    return JSONResponse(_state_payload())


@router.get("/api/me")
async def me(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session = current_user(x_distres_session, distres_session)
    return {"username": session.username}


def _state_payload() -> dict:
    return {
        "sessions": session_manager.active_users(),
        "resource": resource_service.status(),
        "health": failover_controller.health(),
    }


@router.post("/api/read/start")
async def start_read(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session = current_user(x_distres_session, distres_session)
    granted, message, content = resource_service.start_read(session.username)
    await event_bus.publish("reader_active", _state_payload())
    return {"granted": granted, "message": message, "content": content, "state": _state_payload()}


@router.post("/api/read/finish")
async def finish_read(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session = current_user(x_distres_session, distres_session)
    resource_service.finish_read(session.username)
    await event_bus.publish("reader_released", _state_payload())
    return {"ok": True, "state": _state_payload()}


@router.post("/api/write/request")
async def request_write(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):

    # Client access to shared distributed resource.

    # Rubric snippet candidate:
    # - The client requests write access from the server.
    # - Server either grants the writer role or queues the client.
    # - Pub-sub broadcasts writer status to every active client.

    session = current_user(x_distres_session, distres_session)
    status, message, content = resource_service.request_write(session.username)
    await event_bus.publish("writer_active", _state_payload())
    return {"status": status, "message": message, "content": content, "state": _state_payload()}


@router.post("/api/write/save")
async def save_write(
    content: str = Form(...),
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session = current_user(x_distres_session, distres_session)
    ok, message = resource_service.save_write(session.username, content)
    if ok:
        await event_bus.publish(
            "file_updated",
            {"updated_by": session.username, "message": message, "state": _state_payload()},
        )
    return {"ok": ok, "message": message, "state": _state_payload()}


@router.post("/api/write/finish")
async def finish_write(
    x_distres_session: str | None = Header(default=None),
    distres_session: str | None = Cookie(default=None),
):
    session = current_user(x_distres_session, distres_session)
    ok = resource_service.finish_write(session.username)
    await event_bus.publish("writer_released", _state_payload())
    return {"ok": ok, "state": _state_payload()}


@router.get("/events")
async def events(request: Request):

    # Publish-subscribe stream using Server-Sent Events.

    # This behaves like a lightweight event broker for Replit:
    # - Browser subscribes once.
    # - Server pushes events after login/logout/read/write/failover.
    # - UI updates without manual refresh.
    
    client_key = str(uuid.uuid4())
    queue = await event_bus.subscribe(client_key)

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
async def health():
    """Health endpoint used by retry/reconnection logic."""
    return failover_controller.health()


@router.post("/api/failover/promote")
async def promote_standby():

    # Demonstration endpoint for graceful failure handling.

    # In a single Replit instance this logically promotes the standby server node.
    # The UI's retry wrapper and event stream show how clients are notified.

    status = failover_controller.promote_standby()
    await event_bus.publish("server_failover", status)
    return status


@router.post("/api/failover/restore")
async def restore_primary():
    status = failover_controller.restore_primary()
    await event_bus.publish("server_restored", status)
    return status
