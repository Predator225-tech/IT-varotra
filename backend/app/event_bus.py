from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import uuid4


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    ressource_id: str | None
    ts: str

    def as_dict(self) -> dict[str, str | None]:
        return {"id": self.id, "type": self.type, "ressource_id": self.ressource_id, "ts": self.ts}


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event_type: str, resource_id: str | None = None) -> Event:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, last_event_id: str | None = None) -> AsyncIterator[Event | None]:
        raise NotImplementedError

    @abstractmethod
    def replay(self, last_event_id: str | None) -> tuple[list[Event], bool]:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    def __init__(self, limit: int = 200) -> None:
        self.events: deque[Event] = deque(maxlen=limit)
        self.waiters: set[asyncio.Queue[Event]] = set()
        self.lock = asyncio.Lock()

    def replay(self, last_event_id: str | None) -> tuple[list[Event], bool]:
        events = list(self.events)
        if not last_event_id:
            return [], False
        for index, event in enumerate(events):
            if event.id == last_event_id:
                return events[index + 1:], False
        return [], bool(events)

    async def publish(self, event_type: str, resource_id: str | None = None) -> Event:
        event = Event(str(uuid4()), event_type, resource_id, datetime.now(timezone.utc).isoformat())
        async with self.lock:
            self.events.append(event)
            waiters = tuple(self.waiters)
        for queue in waiters:
            queue.put_nowait(event)
        return event

    async def subscribe(self, last_event_id: str | None = None) -> AsyncIterator[Event | None]:
        replay, missed = self.replay(last_event_id)
        if missed:
            yield None
        for event in replay:
            yield event
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self.waiters.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self.waiters.discard(queue)


class PostgresEventBus(InMemoryEventBus):
    """In-memory replay plus PostgreSQL NOTIFY for multi-process delivery."""

    channel = "campus_shop_events"

    async def publish(self, event_type: str, resource_id: str | None = None) -> Event:
        event = await super().publish(event_type, resource_id)
        try:
            import psycopg

            database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
            async with await psycopg.AsyncConnection.connect(database_url) as connection:
                await connection.execute(
                    "SELECT pg_notify(%s, %s)", self.channel, json.dumps(event.as_dict())
                )
                await connection.commit()
        except (KeyError, OSError, RuntimeError, Exception) as error:
            if os.getenv("EVENT_BUS_REQUIRED", "0") == "1":
                raise error
        return event

    async def subscribe(self, last_event_id: str | None = None) -> AsyncIterator[Event | None]:
        replay, missed = self.replay(last_event_id)
        if missed:
            yield None
        for event in replay:
            yield event
        try:
            import psycopg

            database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
            async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as connection:
                await connection.execute(f"LISTEN {self.channel}")
                async for notification in connection.notifies():
                    event = Event(**json.loads(notification.payload))
                    self.events.append(event)
                    yield event
        except Exception:
            async for event in super().subscribe(last_event_id):
                yield event



def create_event_bus() -> EventBus:
    if os.getenv("EVENT_BUS", "postgres").lower() == "memory":
        return InMemoryEventBus()
    return PostgresEventBus()
