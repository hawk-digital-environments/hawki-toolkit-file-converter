from __future__ import annotations

import asyncio

from rabbitmq.settings import CommunicationSettings
from rabbitmq.topology import declare_topology


class FakeExchange:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeQueue:
    def __init__(self, name: str, arguments: dict | None) -> None:
        self.name = name
        self.arguments = arguments or {}
        self.bind_calls: list[tuple[str, str]] = []

    async def bind(self, exchange: FakeExchange, routing_key: str) -> None:
        self.bind_calls.append((exchange.name, routing_key))


class FakeChannel:
    def __init__(self) -> None:
        self.exchange_calls: list[tuple[str, str, bool]] = []
        self.queue_calls: list[tuple[str, bool, dict | None]] = []
        self.queues: dict[str, FakeQueue] = {}

    async def declare_exchange(self, name: str, exchange_type, durable: bool):
        self.exchange_calls.append((name, str(exchange_type), durable))
        return FakeExchange(name)

    async def declare_queue(self, name: str, durable: bool, arguments: dict | None = None):
        self.queue_calls.append((name, durable, arguments))
        queue = FakeQueue(name, arguments)
        self.queues[name] = queue
        return queue


def test_topology_declaration_includes_retry_and_failed_bindings() -> None:
    settings = CommunicationSettings(
        events_exchange="pipeline.events",
        retry_exchange="pipeline.retry",
        failed_exchange="pipeline.failed",
        file_conversion_queue="file_conversion_jobs",
        file_conversion_retry_queue="file_conversion_jobs_retry",
        failed_queue="failed_jobs",
        file_discovered_routing_key="scrape.file.discovered",
        file_conversion_retry_routing_key="scrape.file.discovered.retry",
        failed_routing_key="pipeline.failed",
        retry_delay_ms=5000,
        queue_type="quorum",
    )

    channel = FakeChannel()
    topology = asyncio.run(declare_topology(channel, settings))

    assert topology.events_exchange.name == "pipeline.events"
    assert topology.retry_exchange.name == "pipeline.retry"
    assert topology.failed_exchange.name == "pipeline.failed"

    main_queue = channel.queues["file_conversion_jobs"]
    retry_queue = channel.queues["file_conversion_jobs_retry"]
    failed_queue = channel.queues["failed_jobs"]

    assert main_queue.arguments["x-queue-type"] == "quorum"
    assert failed_queue.arguments["x-queue-type"] == "quorum"
    assert retry_queue.arguments["x-message-ttl"] == 5000
    assert retry_queue.arguments["x-dead-letter-exchange"] == "pipeline.events"
    assert retry_queue.arguments["x-dead-letter-routing-key"] == "scrape.file.discovered"

    assert ("pipeline.events", "scrape.file.discovered") in main_queue.bind_calls
    assert ("pipeline.retry", "scrape.file.discovered.retry") in retry_queue.bind_calls
    assert ("pipeline.failed", "pipeline.failed") in failed_queue.bind_calls
