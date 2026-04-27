import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import venv


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_SMOKE_ENV = "NODUS_RUN_DIST_SMOKE"


@unittest.skipUnless(os.environ.get(DIST_SMOKE_ENV) == "1", f"set {DIST_SMOKE_ENV}=1 to run distribution smoke tests")
class DistributionSmokeTests(unittest.TestCase):
    def test_installed_wheel_cli_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            wheel_path = self._build_wheel(temp_root / "wheelhouse")
            venv_dir = temp_root / "venv"
            self._create_venv(venv_dir)
            python_exe = self._python_executable(venv_dir)
            env = self._clean_env()

            self._run([str(python_exe), "-m", "pip", "install", "--no-deps", str(wheel_path)], cwd=temp_root, env=env)
            nodus_exe = self._nodus_executable(venv_dir)
            env = self._clean_env(nodus_exe.parent)

            workspace = temp_root / "workspace"
            workspace.mkdir()

            hello_script = workspace / "hello.nd"
            hello_script.write_text('print("hello wheel")\n', encoding="utf-8")
            hello_run = self._run([str(nodus_exe), "run", str(hello_script)], cwd=workspace, env=env)
            self.assertEqual(hello_run.stdout, "hello wheel\n")

            stdlib_script = workspace / "stdlib_check.nd"
            stdlib_script.write_text(
                '\n'.join(
                    [
                        'import "std:strings" as s',
                        'print(s.repeat("ha", 3))',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            stdlib_run = self._run([str(nodus_exe), "run", str(stdlib_script)], cwd=workspace, env=env)
            self.assertEqual(stdlib_run.stdout, "hahaha\n")

            project_dir = workspace / "project"
            project_dir.mkdir()
            self._run([str(nodus_exe), "init"], cwd=project_dir, env=env)
            self.assertTrue((project_dir / "nodus.toml").is_file())
            self.assertTrue((project_dir / "src" / "main.nd").is_file())
            init_run = self._run([str(nodus_exe), "run"], cwd=project_dir, env=env)
            self.assertEqual(init_run.stdout, "hello from nodus\n")

            repl_run = self._run([str(nodus_exe), "repl"], cwd=workspace, env=env, input_text=":quit\n")
            self.assertIn("REPL", repl_run.stdout)
            self.assertEqual(repl_run.returncode, 0)

            port = self._reserve_port()
            server = subprocess.Popen(
                [str(nodus_exe), "serve", "--host", "127.0.0.1", "--port", str(port), "--allow-paths", str(workspace)],
                cwd=workspace,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                payload = self._wait_for_health(port, server)
                self.assertEqual(payload["status"], "ok")
                self.assertEqual(payload["runtime"], "nodus")
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
                if server.stdout is not None:
                    server.stdout.close()
                if server.stderr is not None:
                    server.stderr.close()

    def _build_wheel(self, wheelhouse: Path) -> Path:
        wheelhouse.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(wheelhouse),
            ],
            cwd=REPO_ROOT,
            env=self._clean_env(),
            timeout=180,
        )
        wheels = sorted(wheelhouse.glob("nodus_lang-*.whl"))
        self.assertTrue(wheels, "wheel build did not produce a nodus-lang wheel")
        return wheels[-1]

    def _create_venv(self, venv_dir: Path) -> None:
        builder = venv.EnvBuilder(with_pip=True, clear=True)
        builder.create(str(venv_dir))

    def _python_executable(self, venv_dir: Path) -> Path:
        if os.name == "nt":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def _nodus_executable(self, venv_dir: Path) -> Path:
        candidates = ["nodus.exe", "nodus.cmd", "nodus"] if os.name == "nt" else ["nodus"]
        base = venv_dir / ("Scripts" if os.name == "nt" else "bin")
        for name in candidates:
            candidate = base / name
            if candidate.exists():
                return candidate
        self.fail(f"nodus console script not found in {base}")

    def _clean_env(self, prepend_path: Path | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        if prepend_path is not None:
            env["PATH"] = str(prepend_path) + os.pathsep + env.get("PATH", "")
        return env

    def _run(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        input_text: str | None = None,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            self.fail(
                "command failed:\n"
                f"cmd: {' '.join(command)}\n"
                f"cwd: {cwd}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def _reserve_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _wait_for_health(self, port: int, server: subprocess.Popen[str]) -> dict:
        deadline = time.time() + 15
        last_error: Exception | None = None
        while time.time() < deadline:
            if server.poll() is not None:
                stdout, stderr = server.communicate(timeout=1)
                self.fail(
                    "nodus serve exited before becoming healthy:\n"
                    f"stdout:\n{stdout}\n"
                    f"stderr:\n{stderr}"
                )
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                conn.request("GET", "/health")
                response = conn.getresponse()
                body = response.read().decode("utf-8")
                conn.close()
                if response.status == 200:
                    return {"status": "ok", "runtime": "nodus"} if not body else json.loads(body)
            except Exception as exc:  # pragma: no cover - timing dependent
                last_error = exc
                time.sleep(0.1)
                continue
            time.sleep(0.1)
        self.fail(f"timed out waiting for /health on port {port}: {last_error}")
