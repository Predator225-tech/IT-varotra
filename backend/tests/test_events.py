import asyncio
import json

from app.event_bus import InMemoryEventBus


def test_event_payload_contains_no_personal_data():
    async def scenario():
        bus = InMemoryEventBus()
        event = await bus.publish("vente.creee", "42")
        payload = json.dumps(event.as_dict())
        assert "Aina" not in payload
        assert "034" not in payload
        assert set(event.as_dict()) == {"id", "type", "ressource_id", "ts"}

    asyncio.run(scenario())


def test_replay_requires_known_last_event_id_and_detects_missed_events():
    async def scenario():
        bus = InMemoryEventBus(limit=1)
        first = await bus.publish("produit.cree", "1")
        second = await bus.publish("produit.cree", "2")
        replay, missed = bus.replay(first.id)
        assert replay == []
        assert missed is True
        replay, missed = bus.replay(second.id)
        assert replay == []
        assert missed is False

    asyncio.run(scenario())