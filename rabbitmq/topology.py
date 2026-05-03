from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aio_pika import ExchangeType, RobustChannel
from aio_pika.abc import AbstractExchange, AbstractQueue

from rabbitmq.settings import CommunicationSettings, SETTINGS


@dataclass
class RabbitTopology:
    events_exchange: AbstractExchange
    retry_exchange: AbstractExchange
    failed_exchange: AbstractExchange
    file_conversion_queue: AbstractQueue
    file_conversion_retry_queue: AbstractQueue
    failed_queue: AbstractQueue


def _queue_arguments(settings: CommunicationSettings, include_queue_type: bool) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    if include_queue_type and settings.queue_type.lower() == "quorum":
        arguments["x-queue-type"] = "quorum"
    return arguments


async def declare_topology(
    channel: RobustChannel,
    settings: CommunicationSettings = SETTINGS,
) -> RabbitTopology:
    events_exchange = await channel.declare_exchange(
        settings.events_exchange,
        ExchangeType(settings.events_exchange_type),
        durable=True,
    )
    retry_exchange = await channel.declare_exchange(
        settings.retry_exchange,
        ExchangeType(settings.retry_exchange_type),
        durable=True,
    )
    failed_exchange = await channel.declare_exchange(
        settings.failed_exchange,
        ExchangeType(settings.failed_exchange_type),
        durable=True,
    )

    file_conversion_queue = await channel.declare_queue(
        settings.file_conversion_queue,
        durable=True,
        arguments=_queue_arguments(settings, include_queue_type=True),
    )

    retry_queue_arguments = {
        "x-message-ttl": settings.retry_delay_ms,
        "x-dead-letter-exchange": settings.events_exchange,
        "x-dead-letter-routing-key": settings.file_discovered_routing_key,
    }
    file_conversion_retry_queue = await channel.declare_queue(
        settings.file_conversion_retry_queue,
        durable=True,
        arguments=retry_queue_arguments,
    )

    failed_queue = await channel.declare_queue(
        settings.failed_queue,
        durable=True,
        arguments=_queue_arguments(settings, include_queue_type=True),
    )

    await file_conversion_queue.bind(
        events_exchange,
        routing_key=settings.file_discovered_routing_key,
    )
    await file_conversion_retry_queue.bind(
        retry_exchange,
        routing_key=settings.file_conversion_retry_routing_key,
    )
    await failed_queue.bind(
        failed_exchange,
        routing_key=settings.failed_routing_key,
    )

    return RabbitTopology(
        events_exchange=events_exchange,
        retry_exchange=retry_exchange,
        failed_exchange=failed_exchange,
        file_conversion_queue=file_conversion_queue,
        file_conversion_retry_queue=file_conversion_retry_queue,
        failed_queue=failed_queue,
    )
