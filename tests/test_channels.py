import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None):
    _loader = ModuleLoader(project_root=None)
    code, functions, code_locs = _loader.compile_only(
        src,
        module_name=source_path or "<memory>",
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        vm.run()
    return out_buf.getvalue().splitlines(), err_buf.getvalue()


class ChannelTests(unittest.TestCase):
    def test_simple_send_recv(self):
        src = """
fn sender(ch) {
    send(ch, 42)
}

fn receiver(ch) {
    let v = recv(ch)
    print(v)
}

let ch = channel()
spawn(coroutine(fn() { sender(ch) }))
spawn(coroutine(fn() { receiver(ch) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["42.0"])
        self.assertEqual(err.strip(), "")

    def test_blocking_recv(self):
        src = """
fn receiver(ch) {
    print("waiting")
    let v = recv(ch)
    print("got " + v)
}

fn sender(ch) {
    yield
    send(ch, "ok")
}

let ch = channel()
spawn(coroutine(fn() { receiver(ch) }))
spawn(coroutine(fn() { sender(ch) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["waiting", "got ok"])
        self.assertEqual(err.strip(), "")

    def test_pipeline(self):
        src = """
fn generator(out) {
    send(out, 1)
    send(out, 2)
    send(out, 3)
    close(out)
}

fn worker(inp, out) {
    let v = recv(inp)
    while (v != nil) {
        send(out, v * 2)
        v = recv(inp)
    }
    close(out)
}

fn consumer(inp) {
    let v = recv(inp)
    while (v != nil) {
        print(v)
        v = recv(inp)
    }
}

let jobs = channel()
let results = channel()
spawn(coroutine(fn() { generator(jobs) }))
spawn(coroutine(fn() { worker(jobs, results) }))
spawn(coroutine(fn() { consumer(results) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["2.0", "4.0", "6.0"])
        self.assertEqual(err.strip(), "")

    def test_close_behavior(self):
        src = """
fn receiver(ch) {
    let v = recv(ch)
    print(v)
}

fn closer(ch) {
    close(ch)
}

fn sender(ch) {
    yield
    send(ch, 1)
}

let ch = channel()
spawn(coroutine(fn() { receiver(ch) }))
spawn(coroutine(fn() { closer(ch) }))
spawn(coroutine(fn() { sender(ch) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["nil"])
        self.assertIn("Runtime error", err)
        self.assertIn("closed channel", err)

    def test_channel_queue_order(self):
        src = """
let ch = channel()
send(ch, 1)
send(ch, 2)
print(recv(ch))
print(recv(ch))
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["1.0", "2.0"])
        self.assertEqual(err.strip(), "")


class ChannelEdgeCaseTests(unittest.TestCase):
    """Edge cases: closed channels, multiple senders, concurrent access."""

    def test_send_to_closed_channel_raises(self):
        """Sending to a closed channel raises a runtime error."""
        src = """
fn sender(ch) {
    close(ch)
    send(ch, 1)
}
let ch = channel()
spawn(coroutine(fn() { sender(ch) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertIn("closed channel", err)

    def test_recv_from_closed_empty_channel_returns_nil(self):
        """Receiving from a closed empty channel returns nil (not an error)."""
        src = """
fn f(ch) {
    close(ch)
    print(recv(ch))
}
let ch = channel()
spawn(coroutine(fn() { f(ch) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["nil"])
        self.assertEqual(err.strip(), "")

    def test_multiple_senders_one_receiver_fifo(self):
        """Values from multiple senders arrive in send order."""
        src = """
fn sender(ch, v) {
    send(ch, v)
}
fn receiver(ch) {
    let a = recv(ch)
    let b = recv(ch)
    let c = recv(ch)
    print(a)
    print(b)
    print(c)
}
let ch = channel()
spawn(coroutine(fn() { sender(ch, 10) }))
spawn(coroutine(fn() { sender(ch, 20) }))
spawn(coroutine(fn() { sender(ch, 30) }))
spawn(coroutine(fn() { receiver(ch) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["10.0", "20.0", "30.0"])
        self.assertEqual(err.strip(), "")

    def test_recv_before_send_suspends_then_wakes(self):
        """A receiver that arrives before the sender is properly suspended then woken."""
        src = """
fn receiver(ch) {
    print("before")
    let v = recv(ch)
    print("after: " + v)
}
fn sender(ch) {
    yield
    yield
    send(ch, "hello")
}
let ch = channel()
spawn(coroutine(fn() { receiver(ch) }))
spawn(coroutine(fn() { sender(ch) }))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["before", "after: hello"])
        self.assertEqual(err.strip(), "")

    def test_channel_with_buffered_values_all_consumed(self):
        """All pre-buffered values in a channel are consumed in FIFO order."""
        src = """
send(channel(), 999)
let ch = channel()
send(ch, 1)
send(ch, 2)
send(ch, 3)
print(recv(ch))
print(recv(ch))
print(recv(ch))
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["1.0", "2.0", "3.0"])


class CoroutineEdgeCaseTests(unittest.TestCase):
    """Edge cases: exceptions in spawned coroutines, abort-during-sleep."""

    def test_exception_in_spawned_coroutine_does_not_crash_others(self):
        """An exception in one spawned coroutine is isolated; other coroutines run."""
        src = """
fn bad() {
    throw "oops"
}
fn good() {
    print("good")
}
spawn(coroutine(bad))
spawn(coroutine(good))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["good"])
        self.assertIn("oops", err)

    def test_exception_in_spawned_coroutine_printed_to_stderr(self):
        """Uncaught exception in spawned coroutine writes error to stderr."""
        src = """
fn bad() {
    throw {kind: "e", message: "worker-died"}
}
spawn(coroutine(bad))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, [])
        self.assertIn("worker-died", err)

    def test_caught_exception_in_spawned_coroutine_not_visible_to_caller(self):
        """An exception caught inside a spawned coroutine is fully contained."""
        src = """
fn worker() {
    try {
        throw "inner"
    } catch e {
        print("caught: " + e.message)
    }
}
spawn(coroutine(worker))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["caught: inner"])
        self.assertEqual(err.strip(), "")

    def test_multiple_coroutines_interleave_via_yield(self):
        """Coroutines interleave via yield, demonstrating cooperative scheduling."""
        src = """
fn a() {
    print("a1")
    yield
    print("a2")
}
fn b() {
    print("b1")
    yield
    print("b2")
}
spawn(coroutine(a))
spawn(coroutine(b))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["a1", "b1", "a2", "b2"])
        self.assertEqual(err.strip(), "")


if __name__ == "__main__":
    unittest.main()
