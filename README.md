# DistRes v2 - Distributed Resource Access and Synchronisation Engine

DistRes v2 is a Python/FastAPI coursework implementation of a distributed resource access system. Browser tabs act as client nodes, the FastAPI application acts as the server node, and a gateway process provides active-passive failover between a primary server and a standby server.

## Implemented Features

- Multiple browser clients can connect as separate users.
- User credentials and active client sessions are stored server-side in SQLite.
- The shared distributed resource is a server-hosted `ProductSpecification.txt` file.
- Client-server coordination is handled through FastAPI HTTP endpoints.
- Shared resource access is controlled by a read/write coordinator.
- Multiple readers can access the shared file at the same time.
- Only one writer can hold write access at a time.
- Waiting writers are queued fairly so new readers do not starve writers.
- Server-Sent Events provide publish-subscribe notifications to all connected clients.
- The frontend includes retry handling for transient request failures.
- A gateway forwards traffic to the active backend server.
- A standby server can be promoted automatically when the primary server fails.
- The primary server replicates file/session state to standby.
- Backup snapshots of the database and shared file are kept in `data\backup`.

## How To Run

Install dependencies from the `CW2_DistRes` folder:

```powershell
pip install -r requirements.txt
```

The recommended setup uses three separate terminals:

```text
run_primary_server.bat
run_standby_server.bat
run_failover_gateway.bat
```

Open the application through the gateway:

```text
http://127.0.0.1:8000
```

The browser should use the gateway URL, not the direct primary or standby URLs.

## What The Batch Files Do

`run_primary_server.bat` starts the primary FastAPI server on:

```text
http://127.0.0.1:8001
```

It calls `app\Run_Servers\Primary_Server_Run.py`, which sets:

```text
DISTRES_NODE_ID=primary
DISTRES_ROLE=primary
DISTRES_DATA_DIR=data
DISTRES_REPLICATION_TARGET=http://127.0.0.1:8002
PORT=8001
```

`run_standby_server.bat` starts the standby FastAPI server on:

```text
http://127.0.0.1:8002
```

It calls `app\Run_Servers\Standby_Server_Run.py`, which sets:

```text
DISTRES_NODE_ID=standby
DISTRES_ROLE=standby
DISTRES_DATA_DIR=data\standby
PORT=8002
```

`run_failover_gateway.bat` starts the gateway on:

```text
http://127.0.0.1:8000
```

It calls `app\Run_Servers\Failover_Gateway_Run.py`, which sets:

```text
DISTRES_PRIMARY_URL=http://127.0.0.1:8001
DISTRES_STANDBY_URL=http://127.0.0.1:8002
PORT=8000
```

The gateway health-checks the primary and standby servers, forwards browser requests to the active backend, and promotes standby when the primary stops responding.

## Login Users

All seeded users use the password:

```text
pass123
```

Available users:

```text
Ali
Omar
Uthman
Abu Bakr
Talha
Zaid
```

The users are seeded in `app/config.py` and inserted into SQLite by `app/database.py`.

## Project Structure

| Path | Purpose |
| --- | --- |
| `main.py` | Starts the FastAPI application server. |
| `gateway.py` | Runs the failover gateway and proxies requests to primary or standby. |
| `run_primary_server.bat` | Windows launcher for the primary server. |
| `run_standby_server.bat` | Windows launcher for the standby server. |
| `run_failover_gateway.bat` | Windows launcher for the gateway. |
| `app/__init__.py` | Creates the FastAPI app, mounts static assets, and registers routes. |
| `app/routes.py` | Main HTTP API, dashboard routes, SSE endpoint, and internal replication/failover endpoints. |
| `app/session_manager.py` | Tracks active client nodes and replicable session state. |
| `app/rw_lock.py` | Implements the read/write coordination algorithm. |
| `app/resource_service.py` | Reads/writes the shared file through the read/write lock. |
| `app/event_bus.py` | Implements publish-subscribe using Server-Sent Events. |
| `app/replication_service.py` | Creates snapshots and replicates state to standby. |
| `app/failover.py` | Tracks whether a server process is active or passive. |
| `app/database.py` | Creates SQLite tables and seeds default users. |
| `app/auth_service.py` | Validates login credentials against SQLite. |
| `app/config.py` | Defines paths, default users, node identity, role, and replication target. |
| `app/templates/index.html` | Login page used by browser client nodes. |
| `app/templates/dashboard.html` | Client dashboard for sessions, resource access, events, and failover state. |
| `app/static/style.css` | Dashboard and login page styling. |
| `data/users.db` | Primary server SQLite database. |
| `data/ProductSpecification.txt` | Primary shared resource file. |
| `data/standby` | Standby server replica data directory. |
| `data/backup` | Local snapshot directory for recovery evidence. |

## Rubric And Scenario Implementation Map

| Requirement | Where implemented | What to inspect |
| --- | --- | --- |
| Client nodes | `app/templates/index.html:14`, `app/templates/dashboard.html:23`, `app/session_manager.py:27` | Browser tabs log in as different users and become active client sessions. |
| Client connection to server | `app/routes.py:47`, `app/auth_service.py:7`, `app/session_manager.py:27` | Login posts credentials to the server, validates them, then creates a server-side session. |
| Client coordination with server | `app/routes.py:22`, `app/routes.py:116`, `app/templates/dashboard.html:93` | Each request includes the session token and the server updates session activity. |
| Managing active client nodes | `app/session_manager.py:21`, `app/session_manager.py:71`, `app/session_manager.py:108` | SessionManager creates, refreshes, removes, and lists active clients. |
| Server-hosted credentials | `app/config.py:23`, `app/database.py:20`, `app/database.py:26`, `app/auth_service.py:7` | Default users are seeded into the SQLite `users` table and checked on login. |
| Server-hosted shared resource | `app/config.py:13`, `app/database.py:53`, `app/resource_service.py:9`, `app/resource_service.py:26` | `ProductSpecification.txt` is created and then read/written only through server-side code. |
| Access to shared distributed resource | `app/routes.py:146`, `app/routes.py:159`, `app/routes.py:172`, `app/routes.py:188`, `app/routes.py:206` | API endpoints start/finish reads, request write access, save writes, and release write access. |
| Concurrent reads | `app/rw_lock.py:16`, `app/resource_service.py:9`, `app/templates/dashboard.html:135` | `start_read` allows multiple active readers when no writer is active or waiting. |
| Single writer access | `app/rw_lock.py:32`, `app/rw_lock.py:66`, `app/resource_service.py:26` | `request_write` grants one writer, queues others, and `save_write` checks write ownership. |
| Race-condition prevention | `app/rw_lock.py:10`, `app/rw_lock.py:16`, `app/rw_lock.py:32`, `app/rw_lock.py:84` | A process-local mutex protects active reader, active writer, and waiting writer state. |
| Client-server coordination API | `app/routes.py:47`, `app/routes.py:96`, `app/routes.py:116`, `app/routes.py:146`, `app/routes.py:172`, `app/routes.py:188` | Routes coordinate login, dashboard access, state polling, reads, writes, and saves. |
| Publish-subscribe mechanism | `app/event_bus.py:9`, `app/event_bus.py:16`, `app/event_bus.py:29`, `app/event_bus.py:37` | EventBus stores subscriber queues and formats Server-Sent Events. |
| SSE endpoint | `app/routes.py:267` | `/events` keeps a streaming connection open for each subscribed browser. |
| Browser subscription to events | `app/templates/dashboard.html:182` | The dashboard uses `EventSource("/events")` and listens for server events. |
| Events after client actions | `app/routes.py:63`, `app/routes.py:89`, `app/routes.py:153`, `app/routes.py:178`, `app/routes.py:192`, `app/routes.py:209` | Login, logout, read, write, save, and release operations publish events to all clients. |
| Frontend retry handling | `app/templates/dashboard.html:93` | `safeFetch` retries failed HTTP requests before surfacing an error. |
| Server node startup | `main.py:5`, `app/__init__.py:10`, `app/__init__.py:14`, `app/__init__.py:23` | The app is created, the database is initialised, and routes are registered. |
| Primary/standby node identity | `app/config.py:17`, `app/config.py:18`, `app/failover.py:8` | Environment variables define whether the process is primary or standby. |
| Passive standby protection | `app/failover.py:39`, `app/routes.py:29` | Client-facing operations reject direct access when the node is passive standby. |
| Failover gateway | `gateway.py:37`, `gateway.py:66`, `gateway.py:239`, `gateway.py:334`, `gateway.py:340` | The gateway chooses the active backend and proxies normal browser requests. |
| Gateway health/status | `gateway.py:48`, `gateway.py:116`, `gateway.py:270`, `app/templates/dashboard.html:170` | The gateway checks `/api/health` on primary/standby and exposes `/gateway/status`. |
| Standby promotion | `gateway.py:126`, `app/routes.py:251`, `app/failover.py:24` | The gateway calls `/internal/promote`, and standby starts accepting client requests. |
| Failback state sync | `gateway.py:140`, `gateway.py:276`, `app/routes.py:240`, `app/routes.py:259` | The gateway can export standby state, replicate it to primary, and demote standby. |
| State replication to standby | `app/replication_service.py:31`, `app/routes.py:219`, `app/session_manager.py:127`, `app/session_manager.py:146` | File content and sessions are sent from primary to standby over an internal HTTP endpoint. |
| Snapshot recovery evidence | `app/replication_service.py:14`, `app/replication_service.py:20`, `app/replication_service.py:22` | SQLite and text-file snapshots are copied into `data\backup`. |
| Layered architecture | `app/templates`, `app/routes.py`, `app/resource_service.py`, `app/session_manager.py`, `app/database.py` | UI, controller/API, service logic, and data storage are separated by file responsibility. |

## Extra Notes

The implementation is an active-passive coursework prototype. The primary server uses `data`, while the standby server uses `data\standby`. Sessions and shared file content are replicated to standby, so connected users can continue after failover through the gateway.

Read/write lock ownership is process-local. During failover, replicated sessions remain available, but active read/write locks are reset because the standby is a separate server process. Clients request read or write access again after promotion.

The gateway URL, `http://127.0.0.1:8000`, is the intended client entry point for the full system. Direct primary and standby URLs are implementation endpoints used by the gateway and for inspection.
