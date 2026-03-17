"""Communication channel abstraction for agent-to-agent negotiation."""

import asyncio
from abc import ABC, abstractmethod

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
