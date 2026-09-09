"""
E2E test infrastructure -- a real uvicorn server process, bound to the
same farm_master_test Postgres database as the API layer, driven by a
real Chromium browser (Playwright). Unlike tests/api's per-test rolled-
back transactions, this layer needs a real running app.seed() dataset to
click through -- that's the whole point of end-to-end testing the actual
served pages, matching exactly how every Stage 6 screen was manually
verified throughout the build.

The test database is dropped and recreated once per test session before
the server starts, so every E2E run begins from the same known seed.py
dataset -- see app/seed.py for the seeded accounts (all passwords
"password123").
"""

import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import pytest

os.environ["FARM_MASTER_DATABASE_URL"] = os.environ.get(
    "FARM_MASTER_TEST_DATABASE_URL",
    "postgresql+psycopg://farmmaster:farmmaster_dev_pw@127.0.0.1:5432/farm_master_test",
)

from sqlalchemy import create_engine
from app.database import Base, DATABASE_URL

assert "farm_master_test" in DATABASE_URL, (
    "Refusing to run E2E tests: FARM_MASTER_DATABASE_URL does not point at "
    "farm_master_test. This layer drops and reseeds the whole database."
)


def _free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _kill_process_tree(pid: int) -> None:
    """
    On Windows, Popen.terminate()/kill() were found (8 Sep 2026 E2E
    debugging) to sometimes not actually free the process -- a leftover
    server from an earlier run was later found still listening and still
    holding real Postgres connections against farm_master_test, which is
    strongly suspected to have corrupted a subsequent run's drop_all/
    create_all cycle (cascading Page.goto timeouts partway through that
    run). `taskkill /T /F` kills the whole process tree unconditionally,
    which plain Popen.terminate() does not guarantee.
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        import signal

        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _terminate_stale_connections():
    """
    Belt-and-braces alongside _kill_process_tree: forcibly ends any other
    session already connected to farm_master_test (e.g. a leftover server
    from an aborted prior run whose OS process cleanup failed) before this
    run's drop_all/create_all -- a stale connection holding a lock is the
    actual mechanism that corrupted a run during E2E debugging on 8 Sep
    2026, independent of whether the OS process itself was also cleaned up.
    """
    import psycopg

    admin_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://").rsplit("/", 1)[0] + "/postgres"
    try:
        conn = psycopg.connect(admin_url, autocommit=True, connect_timeout=5)
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'farm_master_test' AND pid <> pg_backend_pid()"
        )
        conn.close()
    except Exception:
        pass  # best-effort -- drop_all below will surface a real problem loudly if this didn't help


@pytest.fixture(scope="session")
def live_server_url():
    _terminate_stale_connections()
    engine = create_engine(DATABASE_URL)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    port = _free_port()
    env = os.environ.copy()
    env["FARM_MASTER_DATABASE_URL"] = DATABASE_URL
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # `stdout=subprocess.PIPE` with nothing ever reading it was the actual
    # root cause of the cascading Page.goto timeouts found during E2E
    # debugging on 8/9 Sep 2026: uvicorn logs one access-log line per HTTP
    # request, and once those fill the OS pipe buffer (a few dozen
    # requests in), the child's next stdout write() blocks forever,
    # freezing its single event loop -- every subsequent request then
    # hangs until Playwright's own timeout fires. A real log file has no
    # such blocking-buffer limit, and doubles as a debugging artifact.
    log_path = os.path.join(backend_dir, "tests", "e2e", "_live_server.log")
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=backend_dir, env=env,
        stdout=log_file, stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        import urllib.request
        import urllib.error

        deadline = time.time() + 30
        up = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        up = True
                        break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.3)
        if not up:
            log_file.flush()
            with open(log_path, encoding="utf-8") as f:
                out = f.read()
            raise RuntimeError(f"E2E live server never came up on {base_url}.\n{out}")

        yield base_url
    finally:
        _kill_process_tree(proc.pid)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        log_file.close()
