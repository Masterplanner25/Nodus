"""Bounded channels exert backpressure: send on a full channel blocks (#402).

`waiting_senders` was declared and never wired -- `send` on a full channel
raised, so a bounded channel was an assertion about queue depth rather than a
flow-control primitive. A send in a coroutine now parks on the channel and a
`recv` that frees a slot wakes it, mirroring the blocking-receive path; the
deadlock detector accounts for parked senders the way it always did for
receivers; and `close` flushes parked senders' values into the (still
drainable) queue. Outside a coroutine there is nothing to suspend, so the
raise remains, with the same guidance `recv` gives.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


# closes: #402
class ChannelBackpressureTests(unittest.TestCase):
    def test_producer_blocks_until_consumer_frees_a_slot(self):
        result = _run(
            "fn main() {\n"
            "    let ch = channel(1i)\n"
            "    let producer = coroutine(fn() {\n"
            '        send(ch, "a")\n'
            '        print("sent a")\n'
            '        send(ch, "b")\n'
            '        print("sent b")\n'
            "        close(ch)\n"
            "    })\n"
            "    let consumer = coroutine(fn() {\n"
            "        let x = recv(ch)\n"
            '        print("got \\(x)")\n'
            "        let y = recv(ch)\n"
            '        print("got \\(y)")\n'
            "    })\n"
            "    spawn(producer)\n"
            "    spawn(consumer)\n"
            "    run_loop()\n"
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        stdout = result.get("stdout") or ""
        # The second send completes only after the first recv freed the slot.
        self.assertIn("sent a", stdout)
        self.assertIn("sent b", stdout)
        self.assertIn("got a", stdout)
        self.assertIn("got b", stdout)
        self.assertLess(stdout.index("got a"), stdout.index("sent b"))

    def test_blocked_sender_with_no_receiver_is_a_deadlock(self):
        result = _run(
            "fn main() {\n"
            "    let ch = channel(1i)\n"
            "    let producer = coroutine(fn() {\n"
            '        send(ch, "a")\n'
            '        send(ch, "b")\n'
            "    })\n"
            "    spawn(producer)\n"
            "    run_loop()\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("Deadlock", text)
        self.assertIn("blocked on send() with no possible receiver", text)

    def test_full_send_outside_a_coroutine_still_raises_with_guidance(self):
        """There is nothing to suspend outside the scheduler; the raise stays,
        now pointing at the fix."""
        result = _run(
            "fn main() {\n"
            "    let ch = channel(1i)\n"
            '    send(ch, "a")\n'
            '    send(ch, "b")\n'
            "}\n"
        )
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("channel is full", text)
        self.assertIn("run_loop", text)

    def test_close_flushes_a_parked_senders_value(self):
        result = _run(
            "fn main() {\n"
            "    let ch = channel(1i)\n"
            "    let producer = coroutine(fn() {\n"
            '        send(ch, "a")\n'
            '        send(ch, "b")\n'
            '        print("producer done")\n'
            "    })\n"
            "    let closer = coroutine(fn() {\n"
            "        close(ch)\n"
            "    })\n"
            "    let drainer = coroutine(fn() {\n"
            "        let x = recv(ch)\n"
            "        let y = recv(ch)\n"
            '        print("drained \\(x) \\(y)")\n'
            "    })\n"
            "    spawn(producer)\n"
            "    spawn(closer)\n"
            "    spawn(drainer)\n"
            "    run_loop()\n"
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        stdout = result.get("stdout") or ""
        self.assertIn("producer done", stdout)
        self.assertIn("drained a b", stdout)

    def test_unbounded_send_never_blocks(self):
        """Falsifiability control: backpressure applies to bounded channels
        only."""
        result = _run(
            "fn main() {\n"
            "    let ch = channel()\n"
            "    let n = 0i\n"
            "    while (n < 100i) {\n"
            '        send(ch, "x")\n'
            "        n = n + 1i\n"
            "    }\n"
            '    print("queued 100")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("queued 100", result.get("stdout") or "")

    def test_recv_deadlock_message_is_unchanged(self):
        """The published denial-contract lesson: keep the recv wording."""
        result = _run(
            "fn main() {\n"
            "    let ch = channel()\n"
            "    let waiter = coroutine(fn() { let x = recv(ch); return x })\n"
            "    spawn(waiter)\n"
            "    run_loop()\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        self.assertIn("blocked on recv() with no possible sender", str(result))


if __name__ == "__main__":
    unittest.main()
