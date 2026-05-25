# DistRes v2 - 6CM604 CW2 Python Implementation

DistRes v2 is a Python/FastAPI implementation of the Distributed Resource Access and Synchronisation Engine. It demonstrates browser clients acting as distributed client nodes, server-hosted credentials and file resources, read/write synchronisation, publish-subscribe notifications, retry handling, and a real active-passive primary/standby failover demo.

## What It Demonstrates

- Client nodes: browser tabs log in as separate users.
- Server-side data layer: SQLite `users.db` and `ProductSpecification.txt`.
- Client-server coordination: FastAPI HTTP endpoints coordinate login, sessions, read, write, state, health and logout.
- Shared resource access: multiple clients can read concurrently; only one writer can write at a time.
- Publish-subscribe: Server-Sent Events broadcast server updates to all active clients.
- Real failover: a gateway process forwards traffic to a primary server and promotes a standby server if the primary stops responding.
- Replication: the active server pushes file/session state to the standby and keeps local backup snapshots.

## Install

From this project folder:

```powershell
pip install -r requirements.txt
```

No extra packages are required beyond `requirements.txt`.

## Run: Single Server Mode

This is useful for quick development, but the assessed failover demo should use the primary/standby/gateway setup below.

```powershell
$env:PORT = "8010"
python main.py
```

Open:

```text
http://127.0.0.1:8010
```

## Run: Real Primary/Standby Failover Mode

Use three separate PowerShell terminals, or run the batch launchers from the repository root:

```text
run_primary_server.bat
run_standby_server.bat
run_failover_gateway.bat
```

The batch files set the same environment variables shown below and start the matching Python wrapper in `app/Run_Servers`.

Manual PowerShell equivalent:

### Terminal 1 - Primary Server

```powershell
$env:DISTRES_NODE_ID = "primary"
$env:DISTRES_ROLE = "primary"
$env:DISTRES_DATA_DIR = "data"
$env:DISTRES_REPLICATION_TARGET = "http://127.0.0.1:8002"
$env:PORT = "8001"
python main.py
```

### Terminal 2 - Standby Server

```powershell
$env:DISTRES_NODE_ID = "standby"
$env:DISTRES_ROLE = "standby"
$env:DISTRES_DATA_DIR = "data\standby"
Remove-Item Env:DISTRES_REPLICATION_TARGET -ErrorAction SilentlyContinue
$env:PORT = "8002"
python main.py
```

### Terminal 3 - Failover Gateway

```powershell
$env:DISTRES_PRIMARY_URL = "http://127.0.0.1:8001"
$env:DISTRES_STANDBY_URL = "http://127.0.0.1:8002"
$env:PORT = "8000"
python gateway.py
```

Open the application through the gateway:

```text
http://127.0.0.1:8000
```

The browser should use the gateway URL only. The gateway health-checks the primary, forwards client requests to the active server, and promotes the standby if the primary fails.

## Demo Users

All demo passwords are:

```text
pass123
```

Users:

```text
Ali
Omar
Uthman
Abu Bakr
Talha
Zaid
```

## Real Failover Demo Steps

1. Start the primary server, standby server, and gateway using the three-terminal setup.
2. Open `http://127.0.0.1:8000` in two or more browser tabs.
3. Log in as different users, for example `Ali` and `Omar`.
4. Show active clients in the dashboard.
5. Start read sessions in multiple tabs to show concurrent reads.
6. Request write access in one tab, edit `ProductSpecification.txt`, and save.
7. Show PubSub events appearing in other tabs.
8. Click `Gateway status` to show the gateway can see primary and standby health.
9. Stop the primary server with `Ctrl+C` in Terminal 1.
10. Continue using the dashboard through `http://127.0.0.1:8000`.
11. Click `Gateway status` again and show the gateway active backend is now `standby`.
12. Save another update to prove the standby is now serving client traffic.

Note: the primary server uses the normal `data` folder, while the standby server keeps its replica in `data\standby`. Lock ownership is intentionally process-local. During failover, clients keep their replicated sessions, but active read/write locks are reset and clients request resource access again. This is appropriate for an active-passive coursework prototype; production systems usually use an external distributed lock service.

## Implementation Report Presentation Plan

The implementation report requires a maximum 10-minute demonstration. Use this structure.

### Client Nodes - 4 Minutes

- Client connection to server: login form in `app/templates/index.html`, login endpoint in `app/routes.py:46`, session creation in `app/session_manager.py:25`.
- Client coordination with server: authenticated session lookup and request headers in `app/routes.py:21` and `app/templates/dashboard.html:93`.
- Access to shared distributed resource: dashboard actions in `app/templates/dashboard.html:136`, `app/templates/dashboard.html:149`, and `app/templates/dashboard.html:158`; read/write endpoints in `app/routes.py:140`, `app/routes.py:166`, and `app/routes.py:182`.

### Server Nodes - 4 Minutes

- Server startup and app wiring: `main.py:11`, `app/__init__.py:10`, `app/__init__.py:22`, `app/__init__.py:23`.
- Server-side data layer: SQLite/file setup in `app/database.py:13`, `app/database.py:25`, and server paths in `app/config.py:11`.
- Managing client nodes: session persistence and active-client listing in `app/session_manager.py:19`, `app/session_manager.py:25`, and `app/session_manager.py:88`.
- Real primary/standby failover: gateway selection in `gateway.py:37`, `gateway.py:64`, standby promotion in `gateway.py:107`, and node health state in `app/failover.py:8`.
- Replication to standby: `app/replication_service.py:12`, `app/replication_service.py:31`, internal receiver in `app/routes.py:211`, and internal promotion in `app/routes.py:232`.

### Core Source Code Explanation - 2 Minutes

- Client-server coordination: `app/routes.py:46` for login, `app/routes.py:140` for reads, `app/routes.py:166` for write requests, `app/routes.py:182` for saving writes.
- Synchronisation: `app/rw_lock.py:7`, `app/rw_lock.py:16`, `app/rw_lock.py:32`, and `app/rw_lock.py:56`.
- Publish-subscribe: `app/event_bus.py:9`, `app/event_bus.py:16`, `app/event_bus.py:29`, SSE route in `app/routes.py:250`, browser subscription in `app/templates/dashboard.html:181`.

## Rubric / Scenario Evidence Map

Use this table when writing the report and when deciding which code to show during the presentation.

| Required area to highlight | Evidence in this project |
| --- | --- |
| Distributed node communication | Browser clients call FastAPI endpoints through HTTP: `app/routes.py:46`, `app/routes.py:140`, `app/routes.py:166`; gateway proxies to real servers: `gateway.py:183`. |
| Client-server architecture | App creation and routing: `app/__init__.py:10`, `app/__init__.py:22`, `app/__init__.py:23`; server entry point: `main.py:11`. |
| Each user acts as a client node | Login UI: `app/templates/index.html:14`; session creation: `app/session_manager.py:25`; active users: `app/session_manager.py:88`. |
| Server hosts credential database | DB setup: `app/database.py:13`; credential table: `app/database.py:19`; authentication query: `app/auth_service.py:7`. |
| Server hosts shared distributed file | Product file path: `app/config.py:13`; read file: `app/resource_service.py:9`; save file: `app/resource_service.py:26`. |
| Layered architecture | UI templates in `app/templates`; API/controller layer in `app/routes.py`; logic services in `app/resource_service.py`, `app/session_manager.py`, `app/replication_service.py`; data layer in `app/database.py` and `app/config.py`. |
| Concurrent reads | Read lock grant: `app/rw_lock.py:16`; active readers set: `app/rw_lock.py:11`; read endpoint: `app/routes.py:140`. |
| Single writer | Write request logic: `app/rw_lock.py:32`; active writer field: `app/rw_lock.py:12`; save ownership check: `app/resource_service.py:27`. |
| Race-condition prevention | Mutex-protected coordinator: `app/rw_lock.py:10`; guarded read/write methods: `app/rw_lock.py:16`, `app/rw_lock.py:32`, `app/rw_lock.py:56`. |
| Publish-subscribe notifications | Event bus subscriber registry: `app/event_bus.py:16`; broadcast: `app/event_bus.py:29`; SSE formatting: `app/event_bus.py:37`; browser `EventSource`: `app/templates/dashboard.html:181`. |
| Write update notifies clients | Save endpoint publishes `file_updated`: `app/routes.py:182`; browser listens for events: `app/templates/dashboard.html:181`. |
| Fault tolerance and retries | Frontend retry wrapper: `app/templates/dashboard.html:93`; gateway health/status: `gateway.py:206`; backend selection and failover: `gateway.py:64`. |
| Real primary/standby failover | Separate server processes with `DISTRES_NODE_ID` and `DISTRES_ROLE`: `app/config.py:17` and `app/config.py:18`; gateway promotion: `gateway.py:107`; standby internal promotion route: `app/routes.py:232`. |
| Replication | Active server pushes state: `app/replication_service.py:31`; standby receives state: `app/routes.py:211`; SQLite sessions are replicated: `app/session_manager.py:103`, `app/session_manager.py:118`. |
| Client node demonstration | Use dashboard panels and actions in `app/templates/dashboard.html:21`, `app/templates/dashboard.html:28`, and `app/templates/dashboard.html:44`. |
| Server node demonstration | Show health and failover panel in `app/templates/dashboard.html:57`; show server health route in `app/routes.py:275`; show gateway in `gateway.py:37`. |
| Code snippet for client-server coordination | `app/routes.py:46`, `app/routes.py:140`, `app/routes.py:166`, `app/routes.py:182`. |
| Code snippet for shared resource access | `app/resource_service.py:9`, `app/resource_service.py:20`, `app/resource_service.py:26`; lock logic in `app/rw_lock.py:16` and `app/rw_lock.py:32`. |
| Code snippet for publish-subscribe | `app/event_bus.py:16`, `app/event_bus.py:29`, `app/routes.py:250`, `app/templates/dashboard.html:181`. |
| User interface screenshots | Login page: `app/templates/index.html:10`; dashboard panels: `app/templates/dashboard.html:21`; dark liquid-glass styling: `app/static/style.css:100`. |
| GitHub/source-code deliverable | Include this whole repository and confirm `requirements.txt`, `main.py`, `gateway.py`, `app/`, and `data/ProductSpecification.txt` are present. |

## Presentation Talking Points

- "DistRes uses HTTP as the distributed communication mechanism between browser client nodes and the server node."
- "The gateway gives the browser one stable URL while it forwards traffic to the currently active backend."
- "The primary writes to the normal server-side data folder, and the standby is a separate FastAPI process with its own replicated data folder."
- "The primary replicates product-file and session state to the standby, so the standby can continue serving logged-in clients after failover."
- "Read/write consistency is maintained by a mutex-protected read/write coordinator: multiple readers are allowed, but only one writer can own the write lock."
- "Publish-subscribe is implemented with Server-Sent Events. Each client subscribes once and receives server events after login, logout, reads, writes, replication/failover and file updates."
