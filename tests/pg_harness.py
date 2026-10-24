"""
Hạ tầng test tích hợp: dựng Postgres 16 + PostgREST thật (cùng schema.sql với bản web) trong thư mục tạm.
Tự bỏ qua (skip) nếu máy không có Postgres/PostgREST. Có thể chỉ đường dẫn bằng biến môi trường:
    JPDIC_PG_BIN=/usr/lib/postgresql/16/bin   JPDIC_POSTGREST=/path/to/postgrest
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

SECRET = b"test-secret-test-secret-test-secret-1234"
USERS = {"a": "11111111-1111-4111-8111-111111111111", "b": "22222222-2222-4222-8222-222222222222"}
SCHEMA = os.path.join(os.path.dirname(__file__), "..", "docs", "supabase_schema.sql")


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def jwt(sub, role="authenticated"):
    h = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = _b64(json.dumps({"sub": sub, "role": role, "aud": "authenticated", "exp": int(time.time()) + 86400}).encode())
    return f"{h}.{p}.{_b64(hmac.new(SECRET, f'{h}.{p}'.encode(), hashlib.sha256).digest())}"


def find_bins():
    pg = os.environ.get("JPDIC_PG_BIN")
    if not pg:
        for c in ("/usr/lib/postgresql/16/bin", "/usr/lib/postgresql/15/bin", "/usr/lib/postgresql/17/bin"):
            if os.path.exists(os.path.join(c, "initdb")):
                pg = c
                break
    pgrst = os.environ.get("JPDIC_POSTGREST") or shutil.which("postgrest") or "/home/claude/tools/pgrst/postgrest"
    if pg and os.path.exists(os.path.join(pg, "initdb")) and os.path.exists(pgrst):
        return pg, pgrst
    return None


class PgHarness:
    def __init__(self, tmp):
        self.pg_bin, self.pgrst = find_bins()
        self.dir = str(tmp)
        self.pgdata = os.path.join(self.dir, "data")
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.pg_port = s.getsockname()[1]; s.close()
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.api_port = s.getsockname()[1]; s.close()
        self.rest_url = f"http://127.0.0.1:{self.api_port}"
        self.as_user = os.environ.get("JPDIC_PG_USER")      # initdb không chạy được bằng root
        self.procs = []

    def _run(self, cmd, **kw):
        if os.geteuid() == 0:
            cmd = ["su", "postgres", "-s", "/bin/bash", "-c", " ".join(f"'{c}'" for c in cmd)]
        return subprocess.run(cmd, check=True, capture_output=True, **kw)

    def start(self):
        os.makedirs(self.dir, exist_ok=True)
        if os.geteuid() == 0:
            subprocess.run(["chown", "-R", "postgres", self.dir], check=True)
            subprocess.run(["chmod", "755", self.dir], check=True)
        self._run([f"{self.pg_bin}/initdb", "-D", self.pgdata, "-A", "trust"])
        self._run([f"{self.pg_bin}/pg_ctl", "-D", self.pgdata, "-o", f"-p {self.pg_port} -k {self.dir} -c max_connections=60",
                   "-l", os.path.join(self.dir, "pg.log"), "-w", "start"])
        stub = """
create role anon nologin; create role authenticated nologin; create role authenticator noinherit login;
grant anon, authenticated to authenticator;
create schema auth; create table auth.users(id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(coalesce(current_setting('request.jwt.claim.sub', true), (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')), '')::uuid $$;
grant usage on schema public to anon, authenticated;
"""
        for k, u in USERS.items():
            stub += f"insert into auth.users values ('{u}','{k}@x.co');\n"
        self.psql(stub)
        self.psql(open(SCHEMA, encoding="utf-8").read())
        self.psql("grant all on all tables in schema public to authenticated")
        conf = os.path.join(self.dir, "pgrst.conf")
        open(conf, "w").write(f'''db-uri = "postgresql://authenticator@/postgres?host={self.dir}&port={self.pg_port}"
db-schemas = "public"
db-anon-role = "anon"
jwt-secret = "{SECRET.decode()}"
server-host = "127.0.0.1"
server-port = {self.api_port}
''')
        self.procs.append(subprocess.Popen([self.pgrst, conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for _ in range(80):
            try:
                urllib.request.urlopen(self.rest_url + "/", timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.25)
        # đợi schema cache nạp xong
        for _ in range(40):
            try:
                self.api("POST", "/rpc/jp_schema_version", {}, "a")
                break
            except Exception:
                time.sleep(0.25)

    def psql(self, sql):
        path = os.path.join(self.dir, "q.sql")
        open(path, "w", encoding="utf-8").write(sql)
        os.chmod(path, 0o644)
        self._run([f"{self.pg_bin}/psql", "-h", self.dir, "-p", str(self.pg_port), "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-f", path])

    def reset(self):
        self.psql("truncate cards, decks, deck_categories, deck_cards, radicals, radical_cards, user_decompositions, study_sessions, grammar_points, translations, conj_forms, conj_verbs, conj_cells cascade")

    def stop(self):
        for p in self.procs:
            p.terminate()
        try:
            self._run([f"{self.pg_bin}/pg_ctl", "-D", self.pgdata, "-m", "immediate", "stop"])
        except Exception:
            pass

    def api(self, method, path, body=None, user="a", prefer=None):
        h = {"Authorization": "Bearer " + jwt(USERS[user]), "Content-Type": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        req = urllib.request.Request(self.rest_url + path, data=None if body is None else json.dumps(body).encode(), headers=h, method=method)
        try:
            raw = urllib.request.urlopen(req).read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{e.code}: {e.read().decode()}")
        return json.loads(raw) if raw else None
