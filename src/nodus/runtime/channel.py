"""Channel runtime objects for coroutine communication."""

from __future__ import annotations

from collections import deque


class Channel:
    def __init__(self, maxsize: int = 0):
        self.maxsize = maxsize  # 0 means unbounded
        self.queue: deque[object] = deque()
        self.waiting_receivers: deque[object] = deque()  # O(1) popleft
        self.waiting_senders: deque[tuple[object, object]] = deque()  # O(1) popleft
        self.closed: bool = False


class ChannelRecvRequest:
    def __init__(self, channel: Channel):
        self.channel = channel


class ChannelSendRequest(ChannelRecvRequest):
    """A send suspended on a full channel (#402).

    A subclass so the VM's suspend handling (`isinstance(result,
    ChannelRecvRequest)`) covers both directions without a second branch --
    the request means the same thing either way: this coroutine is parked on
    a channel and the scheduler owns it now.
    """
