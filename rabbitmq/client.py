from __future__ import annotations

import json
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, Message, RobustChannel, RobustConnection
from pydantic import BaseModel

from rabbitmq.settings import CommunicationSettings, SETTINGS
from rabbitmq.topology import RabbitTopology, declare_topology


class RabbitMQClient:
    def __init__(self, settings: CommunicationSettings = SETTINGS) -> None:
        self.settings = settings
        self.connection: RobustConnection | None = None
        self.channel: RobustChannel | None = None
        self.topology: RabbitTopology | None = None

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(
            host=self.settings.rabbitmq_host,
            port=self.settings.rabbitmq_port,
            login=self.settings.rabbitmq_user,
            password=self.settings.rabbitmq_password,
            virtualhost=self.settings.rabbitmq_vhost,
            heartbeat=self.settings.rabbitmq_heartbeat,
            timeout=self.settings.rabbitmq_connection_timeout,
        )

        self.channel = await self.connection.channel(
            publisher_confirms=self.settings.publisher_confirms,
        )
        await self.channel.set_qos(prefetch_count=self.settings.prefetch_count)
        self.topology = await declare_topology(self.channel, self.settings)

    async def close(self) -> None:
        if self.channel and not self.channel.is_closed:
            await self.channel.close()
        if self.connection and not self.connection.is_closed:
            await self.connection.close()

    def _build_message(self, event: dict[str, Any]) -> Message:
        body = json.dumps(event, default=str).encode("utf-8")
        delivery_mode = (
            DeliveryMode.PERSISTENT
            if self.settings.persistent_messages
            else DeliveryMode.NOT_PERSISTENT
        )
        return Message(
            body=body,
            content_type="application/json",
            delivery_mode=delivery_mode,
        )

    def _to_payload(self, event: dict[str, Any] | BaseModel) -> dict[str, Any]:
        if isinstance(event, BaseModel):
            return event.model_dump(mode="json")
        return event

    async def publish_event(
        self,
        event: dict[str, Any] | BaseModel,
        routing_key: str,
    ) -> None:
        if not self.topology:
            raise RuntimeError("RabbitMQ client is not connected")

        payload = self._to_payload(event)
        message = self._build_message(payload)
        await self.topology.events_exchange.publish(message, routing_key=routing_key)

    async def publish_retry(self, event: dict[str, Any] | BaseModel) -> None:
        if not self.topology:
            raise RuntimeError("RabbitMQ client is not connected")

        payload = self._to_payload(event)
        message = self._build_message(payload)
        await self.topology.retry_exchange.publish(
            message,
            routing_key=self.settings.file_conversion_retry_routing_key,
        )

    async def publish_failed_event(self, event: dict[str, Any] | BaseModel) -> None:
        if not self.topology:
            raise RuntimeError("RabbitMQ client is not connected")

        payload = self._to_payload(event)
        message = self._build_message(payload)
        await self.topology.failed_exchange.publish(
            message,
            routing_key=self.settings.failed_routing_key,
        )
