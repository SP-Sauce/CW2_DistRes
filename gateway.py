import asyncio
import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse


GATEWAY_MODE = "active-active-read-scaling-leader-routed-writes"
GATEWAY_HEADER_VALUE = "active-active-read-scaling-leader-election"
LEADER_ELECTION_ALGORITHM = "Simplified Bully Algorithm"

NODE1_URL = os.environ.get(
    "DISTRES_NODE1_URL",
    os.environ.get("DISTRES_PRIMARY_URL", "http://127.0.0.1:8001"),
).rstrip("/")
NODE2_URL = os.environ.get(
    "DISTRES_NODE2_URL",
    os.environ.get("DISTRES_STANDBY_URL", "http://127.0.0.1:8002"),
).rstrip("/")
NODE3_URL = os.environ.get("DISTRES_NODE3_URL", "http://127.0.0.1:8003").rstrip("/")

HEALTH_TIMEOUT = float(os.environ.get("DISTRES_HEALTH_TIMEOUT", "1.2"))
REQUEST_TIMEOUT = float(os.environ.get("DISTRES_REQUEST_TIMEOUT", "8"))
SSE_TIMEOUT = float(os.environ.get("DISTRES_SSE_TIMEOUT", "30"))

CLUSTER_NODES = [
    {
        "name": "node1","url": NODE1_URL,"priority": 3,
    },
    {
        "name": "node2","url": NODE2_URL,"priority": 2,
    },
    {
        "name": "node3","url": NODE3_URL,"priority": 1,
    },
]

SAFE_EXACT_ROUTES = {
    ("GET", "/"),
    ("HEAD", "/"),
    ("GET", "/dashboard"),
    ("GET", "/api/state"),
    ("GET", "/api/me"),
    ("GET", "/api/health"),
    ("POST", "/api/read/start"),
    ("POST", "/api/read/finish"),
}

LEADER_EXACT_ROUTES = {
    ("POST", "/login"),
    ("POST", "/logout"),
    ("POST", "/gateway/election"),
    ("POST", "/api/write/request"),
    ("POST", "/api/write/save"),
    ("POST", "/api/write/finish"),
    ("GET", "/internal/export/state"),
    ("POST", "/internal/replicate/state"),
}

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


class AAGateway:
    # AA: ctive-active read scaling with leader-routed writes.
    def __init__(self, cluster_nodes: list[dict]) -> None:
        self.cluster_nodes = cluster_nodes
        leader = max(cluster_nodes, key=lambda node: node["priority"])
        self._leader_name = leader["name"]
        self._leader_url = leader["url"]
        self._active_name = leader["name"]
        self._active_url = leader["url"]
        self._last_election = None
        self._rr_index = 0
        self._lock = threading.Lock()

    # Returns gateway routing policy, cluster health, and election state for the UI/demo.
    def status(self) -> dict:
        health = self._cluster_health()
        with self._lock:
            leader_name = self._leader_name
            leader_url = self._leader_url
            active_name = self._active_name
            active_url = self._active_url
            last_election = self._last_election
            rr_index = self._rr_index

        return {
            "gateway_mode": GATEWAY_MODE,
            "model": "active-active read scaling with leader-routed writes.",
            "load_balancing_policy": "round-robin for safe/read requests",
            "write_routing_policy": "writes routed to Bully-elected leader",
            "leader_election_algorithm": LEADER_ELECTION_ALGORITHM,
            "cluster_nodes": [
                {
                    "name": node["name"],
                    "url": node["url"],
                    "priority": node["priority"],
                }
                for node in self.cluster_nodes
            ],
            "cluster_health": health,
            "leader": leader_name,
            "leader_url": leader_url,
            "selected_backend": active_name,
            "selected_url": active_url,
            "active_backend": active_name,
            "active_url": active_url,
            "last_election": last_election,
            "round_robin_index": rr_index,
        }

    # Simplified Bully Algorithm: highest-priority healthy server becomes coordinator.
    def run_bully_election(self, reason: str = "manual") -> dict:
        candidates = []
        unavailable_nodes = []

        for node in self.cluster_nodes:
            health = self._health(node["url"])
            election_node = {
                "name": node["name"],
                "url": node["url"],
                "priority": node["priority"],
                "health": health,
            }
            if health.get("ok", False):
                candidates.append(election_node)
            else:
                unavailable_nodes.append(election_node)

        if not candidates:
            raise BackendUnavailable("Election failed: no healthy nodes responded.")

        winner = max(candidates, key=lambda node: node["priority"])
        election_result = {
            "algorithm": LEADER_ELECTION_ALGORITHM,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "winner": winner["name"],
            "winner_url": winner["url"],
            "winner_priority": winner["priority"],
            "candidates": [
                {
                    "name": candidate["name"],
                    "url": candidate["url"],
                    "priority": candidate["priority"],
                    "healthy": True,
                    "health": candidate["health"],
                }
                for candidate in candidates
            ],
            "unavailable_nodes": [
                {
                    "name": node["name"],
                    "url": node["url"],
                    "priority": node["priority"],
                    "healthy": False,
                    "health": node["health"],
                }
                for node in unavailable_nodes
            ],
        }

        with self._lock:
            self._leader_name = winner["name"]
            self._leader_url = winner["url"]
            self._active_name = winner["name"]
            self._active_url = winner["url"]
            self._last_election = election_result

        return election_result

    # Chooses a backend using routing: load-balanced reads, leader-routed writes.
    def choose_backend(self, path: str, method: str) -> tuple[str, str, str]:
        normalised_path = _normalise_path(path)
        method = method.upper()

        if normalised_path == "/events":
            return self._choose_leader_backend("sse stream prefers elected leader")

        if _requires_leader(normalised_path, method):
            return self._choose_leader_backend("leader-routed write/coordination request")

        return self._choose_read_backend("round-robin safe/read request")

    # Clears the selected leader after a proxy failure so the next write triggers election.
    def mark_failed(self, backend_url: str) -> None:
        with self._lock:
            if backend_url == self._leader_url:
                self._leader_name = ""
                self._leader_url = ""
            if backend_url == self._active_url:
                self._active_name = ""
                self._active_url = ""

    # Returns True when a backend responds successfully to its health endpoint.
    def _is_healthy(self, base_url: str) -> bool:
        return self._health(base_url).get("ok", False)

    # Calls a backend's health endpoint and normalises success or failure details.
    def _health(self, base_url: str) -> dict:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=HEALTH_TIMEOUT) as response:
                body = response.read().decode("utf-8")
                status = getattr(response, "status", 200)
            payload = json.loads(body) if body else {}
            return {"ok": True, "status": status, "payload": payload}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}

    def _cluster_health(self) -> dict:
        return {
            node["name"]: {
                "url": node["url"],
                "priority": node["priority"],
                **self._health(node["url"]),
            }
            for node in self.cluster_nodes
        }

    def _healthy_nodes(self) -> list[dict]:
        healthy = []
        for node in self.cluster_nodes:
            health = self._health(node["url"])
            if health.get("ok", False):
                healthy.append({**node, "health": health})
        return healthy

    def _choose_read_backend(self, policy: str) -> tuple[str, str, str]:
        healthy_nodes = self._healthy_nodes()
        if not healthy_nodes:
            raise BackendUnavailable("No healthy DistRes nodes are available for read routing.")

        with self._lock:
            selected = healthy_nodes[self._rr_index % len(healthy_nodes)]
            self._rr_index = (self._rr_index + 1) % len(self.cluster_nodes)
            self._active_name = selected["name"]
            self._active_url = selected["url"]

        return selected["name"], selected["url"], policy

    def _choose_leader_backend(self, policy: str) -> tuple[str, str, str]:
        with self._lock:
            leader_name = self._leader_name
            leader_url = self._leader_url

        if leader_url and self._is_healthy(leader_url):
            with self._lock:
                self._active_name = leader_name
                self._active_url = leader_url
            return leader_name, leader_url, policy

        election = self.run_bully_election(reason="current leader failed health check")
        return election["winner"], election["winner_url"], policy


gateway = AAGateway(CLUSTER_NODES)
app = FastAPI(
    title="DistRes Gateway",
    description="Active-Active read scaling with leader-routed writes.",
)


def _normalise_path(path: str) -> str:
    normalised = f"/{path.lstrip('/')}" if path else "/"
    if len(normalised) > 1:
        normalised = normalised.rstrip("/")
    return normalised


def _requires_leader(path: str, method: str) -> bool:
    route_key = (method.upper(), path)
    if route_key in LEADER_EXACT_ROUTES:
        return True
    if route_key in SAFE_EXACT_ROUTES:
        return False
    if path.startswith("/internal/"):
        return True
    if path.startswith("/api/write/"):
        return True
    if path.startswith("/static/"):
        return False
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return False
    return True


# Builds the upstream backend URL while preserving the original path and query string.
def _target_url(base_url: str, path: str, query_string: bytes) -> str:
    url = f"{base_url}/{path}" if path else f"{base_url}/"
    if query_string:
        url = f"{url}?{query_string.decode('latin-1')}"
    return url


# Copies safe request headers to the backend; routing metadata is added after selection.
def _forward_headers(request: Request) -> dict:
    headers = {}
    for name, value in request.headers.items():
        lower_name = name.lower()
        if lower_name in HOP_BY_HOP_HEADERS or lower_name == "host":
            continue
        headers[name] = value
    headers["X-DistRes-Gateway"] = GATEWAY_HEADER_VALUE
    return headers


def _add_routing_headers(headers: dict, backend_name: str, routing_policy: str) -> dict:
    routed_headers = dict(headers)
    routed_headers["X-DistRes-Selected-Backend"] = backend_name
    routed_headers["X-DistRes-Routing-Policy"] = routing_policy
    with gateway._lock:
        routed_headers["X-DistRes-Leader"] = gateway._leader_name
    return routed_headers


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


# Proxies normal HTTP requests and retries across healthy nodes when routing fails.
async def _proxy_request(path: str, request: Request) -> Response:
    body = await request.body()
    base_headers = _forward_headers(request)

    last_error = "No backend selected."
    max_attempts = max(2, len(CLUSTER_NODES) + 1)
    for _ in range(max_attempts):
        backend_url = ""
        try:
            backend_name, backend_url, routing_policy = gateway.choose_backend(path, request.method)
            headers = _add_routing_headers(base_headers, backend_name, routing_policy)
            url = _target_url(backend_url, path, request.scope.get("query_string", b""))
            response = await asyncio.to_thread(
                _proxy_blocking,
                request.method,
                url,
                headers,
                body,
            )
            response.headers["X-DistRes-Routed-Backend"] = backend_name
            response.headers["X-DistRes-Routing-Policy"] = routing_policy
            return response
        except (BackendUnavailable, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
            if backend_url:
                gateway.mark_failed(backend_url)

    return JSONResponse(
        {"detail": "No healthy DistRes backend is available.", "error": last_error},
        status_code=503,
    )


@app.get("/gateway/status")
async def gateway_status():
    return gateway.status()


@app.get("/gateway/election")
async def gateway_election_status():
    with gateway._lock:
        return {
            "ok": True,
            "algorithm": LEADER_ELECTION_ALGORITHM,
            "leader": gateway._leader_name,
            "leader_url": gateway._leader_url,
            "last_election": gateway._last_election,
        }


@app.post("/gateway/election")
async def gateway_election():
    try:
        result = gateway.run_bully_election(reason="manual election requested")
        return {
            "ok": True,
            "algorithm": LEADER_ELECTION_ALGORITHM,
            "election": result,
            "gateway": gateway.status(),
        }
    except BackendUnavailable as exc:
        return JSONResponse(
            {
                "ok": False,
                "algorithm": LEADER_ELECTION_ALGORITHM,
                "detail": str(exc),
            },
            status_code=503,
        )


@app.get("/events")
async def proxy_events(request: Request):
    base_headers = _forward_headers(request)

    async def event_stream():
        while True:
            if await request.is_disconnected():
                break
            backend_url = ""
            try:
                backend_name, backend_url, routing_policy = gateway.choose_backend("events", "GET")
                headers = _add_routing_headers(base_headers, backend_name, routing_policy)
                upstream_request = urllib.request.Request(
                    f"{backend_url}/events",
                    headers=headers,
                    method="GET",
                )
                upstream = await asyncio.to_thread(
                    urllib.request.urlopen,
                    upstream_request,
                    timeout=SSE_TIMEOUT,
                )
                while True:
                    line = await asyncio.to_thread(upstream.readline)
                    if not line:
                        break
                    yield line
            except (BackendUnavailable, urllib.error.URLError, TimeoutError) as exc:
                payload = json.dumps(
                    {
                        "type": "gateway_routing_issue",
                        "payload": {"message": str(exc), "gateway": gateway.status()},
                    }
                )
                yield f"event: gateway_routing_issue\ndata: {payload}\n\n".encode("utf-8")
                if backend_url:
                    gateway.mark_failed(backend_url)
                await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.api_route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy_root(request: Request):
    return await _proxy_request("", request)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy_path(path: str, request: Request):
    return await _proxy_request(path, request)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
