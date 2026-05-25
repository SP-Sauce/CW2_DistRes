import asyncio
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse


PRIMARY_URL = os.environ.get("DISTRES_PRIMARY_URL", "http://127.0.0.1:8001").rstrip("/")
STANDBY_URL = os.environ.get("DISTRES_STANDBY_URL", "http://127.0.0.1:8002").rstrip("/")
HEALTH_TIMEOUT = float(os.environ.get("DISTRES_HEALTH_TIMEOUT", "1.2"))
REQUEST_TIMEOUT = float(os.environ.get("DISTRES_REQUEST_TIMEOUT", "8"))

HOP_BY_HOP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class BackendUnavailable(RuntimeError):
    pass


class FailoverGateway:
    # Stores primary/standby URLs and starts with primary as the preferred backend.
    def __init__(self, primary_url: str, standby_url: str) -> None:
        self.primary_url = primary_url
        self.standby_url = standby_url
        self._active_url = primary_url
        self._active_name = "primary"
        self._standby_promoted = False
        self._lock = threading.Lock()

    # Returns gateway state plus fresh health checks for primary and standby.
    def status(self) -> dict:
        primary_health = self._health(self.primary_url)
        standby_health = self._health(self.standby_url)
        with self._lock:
            active_name = self._active_name
            active_url = self._active_url
            standby_promoted = self._standby_promoted
        return {
            "active_backend": active_name,
            "active_url": active_url,
            "primary_url": self.primary_url,
            "standby_url": self.standby_url,
            "primary_health": primary_health,
            "standby_health": standby_health,
            "standby_promoted": standby_promoted,
        }

    # Chooses the backend for the next client request and promotes standby if needed.
    def choose_backend(self) -> tuple[str, str]:
        with self._lock:
            active_name = self._active_name
            active_url = self._active_url

        if active_name == "standby":
            standby_ok = self._is_healthy(active_url)
            primary_ok = self._is_healthy(self.primary_url)
            if primary_ok:
                if standby_ok and not self._sync_state(self.standby_url, self.primary_url):
                    return active_name, active_url
                if standby_ok:
                    self._demote_standby()
                with self._lock:
                    self._active_name = "primary"
                    self._active_url = self.primary_url
                    self._standby_promoted = False
                    return self._active_name, self._active_url
            if standby_ok:
                return active_name, active_url

        if self._is_healthy(self.primary_url):
            with self._lock:
                self._active_name = "primary"
                self._active_url = self.primary_url
                self._standby_promoted = False
                return self._active_name, self._active_url

        if self._is_healthy(self.standby_url):
            self._promote_standby()
            with self._lock:
                self._active_name = "standby"
                self._active_url = self.standby_url
                self._standby_promoted = True
                return self._active_name, self._active_url

        raise BackendUnavailable("Neither primary nor standby server is healthy.")

    # Moves traffic away from a failed primary so the next request checks standby first.
    def mark_failed(self, backend_url: str) -> None:
        with self._lock:
            if backend_url == self._active_url and self._active_name == "primary":
                self._active_url = self.standby_url
                self._active_name = "standby"

    # Returns True when a backend responds successfully to its health endpoint.
    def _is_healthy(self, base_url: str) -> bool:
        return self._health(base_url).get("ok", False)

    # Calls a backend's health endpoint and normalises success or failure details.
    def _health(self, base_url: str) -> dict:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=HEALTH_TIMEOUT) as response:
                body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return {"ok": True, "status": getattr(response, "status", 200), "payload": payload}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}

    # Tells the standby server to start accepting client requests after primary failure.
    def _promote_standby(self) -> None:
        with self._lock:
            if self._standby_promoted:
                return

        request = urllib.request.Request(
            f"{self.standby_url}/internal/promote",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            response.read()

    # Copies full active state from one backend into another during manual failback.
    def _sync_state(self, source_url: str, target_url: str) -> bool:
        try:
            with urllib.request.urlopen(
                f"{source_url}/internal/export/state",
                timeout=REQUEST_TIMEOUT,
            ) as response:
                body = response.read().decode("utf-8")
            source_state = json.loads(body) if body else {}

            payload = {
                "product_content": source_state.get("product_content"),
                "sessions": source_state.get("sessions", []),
            }
            request = urllib.request.Request(
                f"{target_url}/internal/replicate/state",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                response.read()
            return True
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return False

    # Returns a promoted standby to passive mode after primary has been restored.
    def _demote_standby(self) -> None:
        request = urllib.request.Request(
            f"{self.standby_url}/internal/demote",
            data=b"",
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                response.read()
        except (urllib.error.URLError, TimeoutError):
            pass


gateway = FailoverGateway(PRIMARY_URL, STANDBY_URL)
app = FastAPI(
    title="DistRes Failover Gateway",
    description="Active-passive gateway for real primary/standby DistRes failover.",
)


# Builds the upstream backend URL while preserving the original path and query string.
def _target_url(base_url: str, path: str, query_string: bytes) -> str:
    url = f"{base_url}/{path}" if path else f"{base_url}/"
    if query_string:
        url = f"{url}?{query_string.decode('latin-1')}"
    return url


# Copies safe request headers to the backend and tags requests as gateway traffic.
def _forward_headers(request: Request) -> dict:
    headers = {}
    for name, value in request.headers.items():
        lower_name = name.lower()
        if lower_name in HOP_BY_HOP_HEADERS or lower_name == "host":
            continue
        headers[name] = value
    headers["X-DistRes-Gateway"] = "active-passive"
    return headers


# Copies safe upstream response headers back to the browser response.
def _copy_response_headers(source_headers: Iterable[tuple[str, str]], response: Response) -> None:
    for name, value in source_headers:
        lower_name = name.lower()
        if lower_name in HOP_BY_HOP_HEADERS or lower_name == "set-cookie":
            continue
        response.headers[name] = value


# Performs one blocking HTTP request to a selected backend server.
def _proxy_blocking(method: str, url: str, headers: dict, body: bytes) -> Response:
    data = None if method in {"GET", "HEAD"} else body
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as upstream:
            content = upstream.read()
            status = upstream.status
            upstream_headers = list(upstream.headers.items())
            set_cookies = upstream.headers.get_all("Set-Cookie", [])
    except urllib.error.HTTPError as exc:
        content = exc.read()
        status = exc.code
        upstream_headers = list(exc.headers.items())
        set_cookies = exc.headers.get_all("Set-Cookie", [])

    response = Response(content=content, status_code=status)
    _copy_response_headers(upstream_headers, response)
    for cookie in set_cookies:
        response.raw_headers.append((b"set-cookie", cookie.encode("latin-1")))
    return response


# Proxies normal HTTP requests and retries once if the selected backend fails.
async def _proxy_request(path: str, request: Request) -> Response:
    body = await request.body()
    headers = _forward_headers(request)

    last_error = "No backend selected."
    for _ in range(2):
        try:
            _backend_name, backend_url = gateway.choose_backend()
            url = _target_url(backend_url, path, request.scope.get("query_string", b""))
            return await asyncio.to_thread(
                _proxy_blocking,
                request.method,
                url,
                headers,
                body,
            )
        except (BackendUnavailable, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
            try:
                gateway.mark_failed(backend_url)
            except UnboundLocalError:
                pass

    return JSONResponse(
        {"detail": "No healthy DistRes backend is available.", "error": last_error},
        status_code=503,
    )


@app.get("/gateway/status")
# Shows gateway health and which backend is currently active.
async def gateway_status():
    return gateway.status()


@app.post("/gateway/reset-primary")
# Resets the gateway preference back to primary after manually restarting it.
async def reset_primary():
    if not gateway._is_healthy(PRIMARY_URL):
        return JSONResponse({"detail": "Primary is not healthy."}, status_code=503)
    if gateway._is_healthy(STANDBY_URL):
        if not gateway._sync_state(STANDBY_URL, PRIMARY_URL):
            return JSONResponse(
                {"detail": "Could not sync standby state back to primary."},
                status_code=502,
            )
        gateway._demote_standby()
    with gateway._lock:
        gateway._active_name = "primary"
        gateway._active_url = PRIMARY_URL
        gateway._standby_promoted = False
    return gateway.status()


@app.get("/events")
# Proxies Server-Sent Events and reconnects through standby after failover.
async def proxy_events(request: Request):
    headers = _forward_headers(request)

    # Streams backend SSE lines to the browser until the browser disconnects.
    async def event_stream():
        while True:
            if await request.is_disconnected():
                break
            try:
                backend_name, backend_url = gateway.choose_backend()
                url = f"{backend_url}/events"
                upstream_request = urllib.request.Request(url, headers=headers, method="GET")
                upstream = await asyncio.to_thread(
                    urllib.request.urlopen,
                    upstream_request,
                    timeout=REQUEST_TIMEOUT,
                )
                while True:
                    line = await asyncio.to_thread(upstream.readline)
                    if not line:
                        break
                    yield line
            except (BackendUnavailable, urllib.error.URLError, TimeoutError) as exc:
                payload = json.dumps(
                    {
                        "type": "gateway_failover",
                        "payload": {"message": str(exc), "gateway": gateway.status()},
                    }
                )
                yield f"event: gateway_failover\ndata: {payload}\n\n".encode("utf-8")
                if "backend_url" in locals():
                    gateway.mark_failed(backend_url)
                await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.api_route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
# Proxies requests for the root path to the active backend.
async def proxy_root(request: Request):
    return await _proxy_request("", request)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
# Proxies all other paths to the active backend.
async def proxy_path(path: str, request: Request):
    return await _proxy_request(path, request)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
