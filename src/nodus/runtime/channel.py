"""Channel runtime objects for coroutine communication."""

from __future__ import annotations

from collections import deque


class Channel:
    def __init__(self):
        self.queue = deque()
        self.waiting_receivers: list[object] = []
        self.waiting_senders: list[tuple[object, object]] = []
        self.closed: bool = False


class ChannelRecvRequest:
    def __init__(self, channel: Channel):
        self.channel = channel
