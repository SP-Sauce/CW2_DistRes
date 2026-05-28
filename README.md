# DistRes v2 - Distributed Resource Access and Synchronisation Engine

DistRes v2 is a Python/FastAPI coursework implementation of a distributed resource access system. Browser tabs act as client nodes, three FastAPI processes act as DistRes server nodes, and a gateway provides load balancing, leader election, and write routing.

## Architecture: Active-Active Reads and Leader-Routed Writes

The system now runs three active DistRes server nodes behind an API Gateway / Load Balancer:

- Safe/read-oriented requests are load-balanced across healthy nodes with round-robin routing.
- Write-sensitive requests are routed to the Bully-elected leader/coordinator.
- A simplified Bully Algorithm elects the highest-priority healthy node as leader.
- The database-backed distributed write lock ensures only one client owns write access.
- The shared SQLite database and shared `ProductSpecification.txt` file are hosted server-side.
- Server-Sent Events provide publish-subscribe notifications to connected clients.

This keeps the prototype coursework-friendly while still showing client-server communication, layered architecture, load balancing, leader election, distributed coordination, retry/failure handling, and one-writer consistency. It does not implement Raft, Paxos, or full consensus.

## Implemented Features

- Multiple browser clients can connect as separate users.
- Seeded users are stored in SQLite and checked during login.
- Active sessions are stored server-side in SQLite.
- A fresh login by the same username replaces an abandoned session after browser restart.
- `ProductSpecification.txt` is the server-hosted shared distributed resource.
- Safe dashboard/state/read requests can be routed across node1, node2, and node3.
- Write requests are routed to the elected leader by the gateway.
- The gateway runs a simplified Bully Algorithm: highest-priority healthy node wins.
- The `resource_readers` SQLite table keeps active-reader display consistent across nodes.
- The `resource_locks` SQLite table protects file writes with a lease-based distributed write lock.
- The `resource_write_waiters` SQLite table keeps blocked writers visible in the waiting list.
- Server-Sent Events notify clients about login/logout/read/write/gateway events.
- The frontend has retry handling for transient gateway/node failures.
- Backup snapshots of the database and shared file are kept in `data\backup`.

## How To Run

Install dependencies from the `CW2_DistRes` folder:

```powershell
pip install -r requirements.txt
```

Use four separate terminals:

```text
run_node1_server.bat
run_node2_server.bat
run_node3_server.bat
run_gateway.bat
```

Open the application through the gateway:

```text
http://127.0.0.1:8000
```

The browser should use the gateway URL, not the direct node URLs.

## Ports And Node Identity

`run_node1_server.bat` starts node1 on:

```text
http://127.0.0.1:8001
DISTRES_NODE_ID=node1
DISTRES_DATA_DIR=data\shared
DISTRES_BACKUP_DIR=data\backup
```

`run_node2_server.bat` starts node2 on:

```text
http://127.0.0.1:8002
DISTRES_NODE_ID=node2
DISTRES_DATA_DIR=data\shared
DISTRES_BACKUP_DIR=data\backup
```

`run_node3_server.bat` starts node3 on:

```text
http://127.0.0.1:8003
DISTRES_NODE_ID=node3
DISTRES_DATA_DIR=data\shared
DISTRES_BACKUP_DIR=data\backup
```

`run_gateway.bat` starts the gateway on:

```text
http://127.0.0.1:8000
DISTRES_NODE1_URL=http://127.0.0.1:8001
DISTRES_NODE2_URL=http://127.0.0.1:8002
DISTRES_NODE3_URL=http://127.0.0.1:8003
DISTRES_SSE_TIMEOUT=30 optional, keeps gateway SSE proxy alive between keep-alives
```

All three nodes use `data\shared\users.db` and `data\shared\ProductSpecification.txt` in the local demo. This is important because the SQLite `resource_readers`, `resource_locks`, and `resource_write_waiters` tables must be shared for active-reader display, waiting-writer display, and the database-backed distributed write lock to coordinate all nodes.

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

## Key Endpoints

```text
GET  /gateway/status
GET  /gateway/election
POST /gateway/election
GET  /api/state
POST /api/read/start
POST /api/read/finish
POST /api/write/request
POST /api/write/save
POST /api/write/finish
GET  /events
```

`/gateway/status` shows the active routing mode, node health, elected leader, round-robin state, and last election result.

## Project Structure

| Path | Purpose |
| --- | --- |
| `main.py` | Starts a DistRes server node. |
| `gateway.py` | API Gateway / Load Balancer with round-robin safe reads and Bully leader election. |
| `app/routes.py` | Login, dashboard, API endpoints, SSE, health, replication, and write guards. |
| `app/resource_service.py` | Reads/writes `ProductSpecification.txt` through shared reader tracking and the DB lock. |
| `app/distributed_lock.py` | SQLite-backed distributed write lock using `resource_locks`. |
| `app/distributed_readers.py` | SQLite-backed active-reader tracking using `resource_readers`. |
| `app/node_status.py` | Reports each server node's health and identity. |
| `app/event_bus.py` | Publish-subscribe notifications using Server-Sent Events. |
| `app/database.py` | Creates SQLite tables, seeded users, sessions, `resource_readers`, `resource_locks`, and `resource_write_waiters`. |
| `app/session_manager.py` | Tracks active browser/client sessions in SQLite. |
| `app/config.py` | Paths, node identity, users, and distributed lock lease configuration. |
| `app/templates/dashboard.html` | Dashboard UI, gateway status display, lock token handling. |
| `run_node1_server.bat` | Windows launcher for node1. |
| `run_node2_server.bat` | Windows launcher for node2. |
| `run_node3_server.bat` | Windows launcher for node3. |
| `run_gateway.bat` | Windows launcher for the gateway. |
| `data\shared` | Shared local demo database and product file. |
| `data\backup` | Backup snapshots. |

## Rubric And Scenario Implementation Map

| Requirement | Where implemented | What to inspect |
| --- | --- | --- |
| Client nodes | `app/templates/index.html`, `app/templates/dashboard.html`, `app/session_manager.py` | Browser tabs log in as separate client nodes. |
| Client-server communication | `app/routes.py` | Login, dashboard, read, write, state, and SSE routes. |
| Layered architecture | `app/templates`, `app/routes.py`, `app/resource_service.py`, `app/database.py` | UI, API, service logic, and data storage are separated. |
| Load balancing | `gateway.py` `choose_backend` | Safe/read routes use round-robin healthy-node selection. |
| Bully Algorithm | `gateway.py` `run_bully_election` | Highest-priority healthy node becomes coordinator. |
| Leader-routed writes | `gateway.py` write-sensitive routing | Mutating routes go to the elected leader. |
| Distributed reader tracking | `app/distributed_readers.py`, `app/database.py` | `resource_readers` table keeps active readers visible across load-balanced nodes. |
| Distributed write lock | `app/distributed_lock.py`, `app/database.py` | `resource_locks` table grants one lease-based writer. |
| Waiting writer tracking | `app/distributed_lock.py`, `app/database.py` | `resource_write_waiters` table keeps blocked writers visible across nodes. |
| Shared resource access | `app/resource_service.py` | Reads and writes use server-hosted `ProductSpecification.txt`. |
| One-writer consistency | `app/resource_service.py`, `app/distributed_lock.py` | Saves are rejected unless the user owns the DB-backed lock. |
| Publish-subscribe | `app/event_bus.py`, `app/routes.py`, `app/templates/dashboard.html` | SSE events update connected clients. |
| Browser restart recovery | `app/routes.py`, `app/session_manager.py` | A same-user login clears abandoned session/lock state and creates a fresh session. |
| Failure handling | `gateway.py`, dashboard retry logic | Gateway health checks, retries, and elections keep routing available. |
| Server-hosted database/file | `app/database.py`, `app/config.py` | SQLite and `ProductSpecification.txt` are created under the data directory. |

## Demo Checklist

Demo 1 - Load-balanced reads:

- Start node1, node2, node3, and gateway.
- Open `http://127.0.0.1:8000`.
- Call `/gateway/status` and show all healthy nodes.
- Refresh dashboard/state and show safe requests route across healthy nodes.

Demo 2 - Bully election:

- Show node1 is leader because priority 3.
- Stop node1.
- Trigger `POST /gateway/election`.
- Show node2 becomes leader because it is now the highest-priority healthy node.
- Stop node2 and show node3 becomes leader.
- Restart node1, trigger election, and show node1 becomes leader again.

Demo 3 - Distributed write lock:

- Login with two clients.
- Client A requests write access and receives the distributed write lock.
- Client B requests write access and is blocked or waiting.
- Client A saves and releases.
- Client B requests write access again and can proceed.
- Show the distributed write lock owner in the dashboard or `/api/state`.

Demo 4 - Pub-sub:

- Keep multiple clients open.
- Save a write update.
- Show the `file_updated` event appears across clients.

Demo 5 - Failure handling:

- Stop one non-leader node.
- Reads continue through other healthy nodes.
- Stop the leader node.
- The gateway runs election and routes writes to the new leader.

## Notes

The distributed write lock is a final consistency guard. It does not mean every server should independently accept writes. Write requests must be routed through the gateway to the Bully-elected leader first, then checked by the DB-backed distributed lock.

If a browser restart loses the local session token while SQLite still contains that user's old session, logging in again with the same username takes over the abandoned session. The old session, reader marker, writer wait entry, and owned write lock are cleared before the new session is created.

The gateway uses a longer SSE timeout than normal HTTP proxy requests so `/events` stays open between server keep-alive messages.

The default shared file text is created if missing:

```text
this our model file to access
```
