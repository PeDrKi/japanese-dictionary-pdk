"""Đồng bộ ngầm sau khi đóng app: khoá liên-tiến-trình + tiến trình --sync-only."""
import os
import subprocess
import sys
import time

import pytest

from infrastructure import sync_lock

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_lock_acquire_release(tmp_path):
    p = str(tmp_path / "x.lock")
    t = sync_lock.acquire(p)
    assert t and os.path.exists(p)
    sync_lock.release(t)
    assert not os.path.exists(p)


def test_lock_held_by_live_other_process_blocks(tmp_path):
    p = str(tmp_path / "x.lock")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with open(p, "w") as f:
            f.write(f"{child.pid} {time.time()}")
        assert sync_lock.acquire(p) is None
        t0 = time.monotonic()
        assert sync_lock.acquire(p, wait_s=0.7) is None      # chờ rồi vẫn bị chặn
        assert time.monotonic() - t0 >= 0.6
    finally:
        child.kill()
        child.wait()


def test_stale_lock_of_dead_process_is_taken_over(tmp_path):
    p = str(tmp_path / "x.lock")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    with open(p, "w") as f:
        f.write(f"{child.pid} {time.time()}")
    t = sync_lock.acquire(p)
    assert t
    sync_lock.release(t)


def test_old_lock_is_taken_over_even_if_pid_alive(tmp_path):
    p = str(tmp_path / "x.lock")
    with open(p, "w") as f:
        f.write(f"{os.getppid()} {time.time() - sync_lock.STALE_S - 5}")
    assert sync_lock.acquire(p)


def test_cloudsync_reports_busy_when_other_process_holds_lock(tmp_path):
    from infrastructure.cloud_sync import CloudSync, StaticAuth
    from database import db as dbm
    dbp = str(tmp_path / "d.db")
    dbm.init_db(db_path=dbp)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with open(dbp + ".sync.lock", "w") as f:
            f.write(f"{child.pid} {time.time()}")
        ok, st, err = CloudSync(auth=StaticAuth("t", "u"), rest_url="http://127.0.0.1:9", db_path=dbp).sync()
        assert not ok and err.startswith("Đang có một lần đồng bộ khác")
    finally:
        child.kill()
        child.wait()


def test_sync_only_process_exits_cleanly_without_config(tmp_path):
    """`main.pyw --sync-only` chưa cấu hình Supabase → thoát mã 0 ngay, không mở cửa sổ, không cần Tk."""
    import shutil
    work = tmp_path / "app"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.db", "settings.json", ".pytest_cache", "docs"))
    r = subprocess.run([sys.executable, str(work / "main.pyw"), "--sync-only"], cwd=work, capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode()[-500:]


def test_spawn_detached_returns_immediately():
    from infrastructure import sync_worker
    t0 = time.monotonic()
    assert sync_worker.spawn_detached() is True
    assert time.monotonic() - t0 < 2.0
