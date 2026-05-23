import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Dict


class EventBus:
    
    # Logical microservice: PubSub Broker / Event Bus.

    # Rubric/design link:
    # - Implements publish-subscribe notifications.
    # - Clients subscribe through Server-Sent Events (SSE).
    # - Server publishes file_updated, writer_active, reader_active and failover events.
    

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, asyncio.Queue] = {}

    async def subscribe(self, client_key: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[client_key] = queue
        await queue.put(self._format_event("subscribed", {"message": "Connected to DistRes event bus"}))
        return queue

    def unsubscribe(self, client_key: str) -> None:
        with self._lock:
            self._subscribers.pop(client_key, None)

    async def publish(self, event_type: str, payload: dict) -> None:
        event = self._format_event(event_type, payload)
        with self._lock:
            queues = list(self._subscribers.values())
        for queue in queues:
            await queue.put(event)

    def _format_event(self, event_type: str, payload: dict) -> str:
        body = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "payload": payload,
        }
        # SSE format: each event is sent as a data line followed by a blank line.
        return f"event: {event_type}\ndata: {json.dumps(body)}\n\n"


event_bus = EventBus()
