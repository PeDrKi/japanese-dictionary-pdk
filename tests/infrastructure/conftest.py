import os
import shutil
import tempfile

import pytest

from tests import pg_harness


@pytest.fixture(scope="session")
def pg():
    if pg_harness.find_bins() is None:
        pytest.skip("Không có Postgres/PostgREST để chạy test tích hợp đồng bộ (đặt JPDIC_PG_BIN / JPDIC_POSTGREST)")
    # root: initdb phải chạy bằng user 'postgres' nên thư mục phải truy cập được (không dùng /tmp/pytest-of-root, mode 700)
    base = tempfile.mkdtemp(prefix="jpdic_pg_", dir="/var/tmp" if os.geteuid() == 0 else None)
    h = pg_harness.PgHarness(base)
    try:
        h.start()
        yield h
    finally:
        h.stop()
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def cloud(pg):
    pg.reset()
    return pg
