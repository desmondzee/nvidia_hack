"""Communication channel abstraction for agent-to-agent negotiation."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.models.negotiation import NegotiationMessage


class MessageLog:
    """Shared log of all negotiation messages for display."""

    def __init__(self) -> None:
        self.messages: list[NegotiationMessage] = []

    def append(self, msg: NegotiationMessage) -> None:
        self.messages.append(msg)


class NegotiationChannel(ABC):
    """Abstract communication channel between two negotiation agents."""

    @abstractmethod
    async def send_message(self, message: NegotiationMessage) -> None:
        """Send a negotiation message to the peer."""
        ...

    @abstractmethod
    async def receive_message(self, timeout: float = 60.0) -> NegotiationMessage:
        """Wait for and return a negotiation message from the peer."""
        ...


class InMemoryChannel(NegotiationChannel):
    """In-process channel using asyncio.Queue for local simulation.

    Create a pair of channels — one for each direction of communication:

        a_to_b = InMemoryChannel()
        b_to_a = InMemoryChannel()

    Satellite A sends on `a_to_b` and receives on `b_to_a`, and vice versa.
    """

    def __init__(self, message_log: MessageLog | None = None) -> None:
        self._queue: asyncio.Queue[NegotiationMessage] = asyncio.Queue()
        self._message_log = message_log

    async def send_message(self, message: NegotiationMessage) -> None:
        if self._message_log:
            self._message_log.append(message)
        await self._queue.put(message)

    async def receive_message(self, timeout: float = 60.0) -> NegotiationMessage:
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)


class StreamableChannel(InMemoryChannel):
    """In-memory channel that emits negotiation messages to a stream queue.

    Use when you want to stream negotiation events (proposals, responses) to
    an API consumer. Pass an asyncio.Queue; each send_message will put an
    event dict into the queue.
    """

    def __init__(
        self,
        message_log: MessageLog | None = None,
        stream_queue: asyncio.Queue[dict[str, Any]] | None = None,
        pair_label: str | None = None,
    ) -> None:
        super().__init__(message_log=message_log)
        self._stream_queue = stream_queue
        self._pair_label = pair_label

    async def send_message(self, message: NegotiationMessage) -> None:
        await super().send_message(message)
        if self._stream_queue is not None:
            event = {
                "type": "negotiation_message",
                "pair_label": self._pair_label,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": message.model_dump(mode="json"),
            }
            await self._stream_queue.put(event)
