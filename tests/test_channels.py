import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang


def run_program(src: str, source_path: str | None = None):
    _ast, code, functions, code_locs = lang.compile_source(
        src,
        source_path=source_path,
        import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
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


if __name__ == "__main__":
    unittest.main()
