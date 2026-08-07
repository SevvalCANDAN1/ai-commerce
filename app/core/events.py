"""In-process event bus for order lifecycle side effects."""

from collections import defaultdict
from collections.abc import Awaitable, Callable

EventHandler = Callable[[dict], Awaitable[None]]

_subscribers: dict[str, list[EventHandler]] = defaultdict(list)


def subscribe(event_name: str, handler: EventHandler) -> None:
    _subscribers[event_name].append(handler)


async def publish(event_name: str, payload: dict) -> None:
    for handler in _subscribers[event_name]:
        await handler(payload)
