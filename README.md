# DistRes v2 - 6CM604 CW2 Python Implementation

This is a Python/FastAPI implementation of the **Distributed Resource Access and Synchronisation Engine (DistRes)**.

## What it demonstrates

- **Client nodes:** browser clients log in as Ali, Omar, Uthman, Abu Bakr, Talha, or Zaid.
- **Server node:** FastAPI server hosts the application logic.
- **Data layer:** SQLite `users.db` and `ProductSpecification.txt` are created server-side.
- **Client-server coordination:** HTTP endpoints coordinate login, read, write and state requests.
- **Shared resource access:** multiple readers can access the product spec concurrently, but only one writer can write at a time.
- **Publish-subscribe:** Server-Sent Events push updates to all connected clients.
- **Fault tolerance:** frontend retry logic plus logical primary/standby failover state.
- **Replication:** writes create backup snapshots of the database and product file.

## Replit run

From the repository root, either click **Run** or use:

```bash
cd python-app
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open the web preview.

## Local run

From `CW2/python-app`:

```bash
pip install -r requirements.txt
python main.py
```

Then open `http://127.0.0.1:8000`. If port 8000 is already in use, set `PORT` first, for example in PowerShell:

```powershell
$env:PORT = "8010"
python main.py
```

Auto-reload is optional:

```powershell
$env:DISTRES_RELOAD = "1"
python main.py
```

## Demo usernames

All passwords are:

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

## Suggested demonstration flow

1. Open the app in five browser tabs.
2. Log in as five different users. Each tab keeps its own client-node session.
3. Start read sessions in multiple tabs to show concurrent reads.
4. Request write access in another tab and show it waits while readers are active.
5. Finish reads and show the writer becomes active.
6. Save an update to `ProductSpecification.txt`.
7. Show every client receives the `file_updated` PubSub event.
8. Promote standby to show failover notification and retry-aware UI.
9. Navigate through the code:
   - `routes.py` for client-server coordination.
   - `rw_lock.py` for read/write coordination.
   - `event_bus.py` for publish-subscribe.
   - `resource_service.py` for shared file access.
   - `database.py` for SQLite data layer.
