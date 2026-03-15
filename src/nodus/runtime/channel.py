"""Channel runtime objects for coroutine communication."""

from __future__ import annotations

from collections import deque


class Channel:
    def __init__(self):
        self.queue = deque()
        self.waiting_receivers: deque[object] = deque()  # O(1) popleft
        self.waiting_senders: deque[tuple[object, object]] = deque()  # O(1) popleft
        self.closed: bool = False


class ChannelRecvRequest:
    def __init__(self, channel: Channel):
        self.channel = channel
