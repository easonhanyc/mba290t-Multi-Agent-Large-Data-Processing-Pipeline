"""Create (or rotate) a SELECT-only Postgres role for the deployed backend and print nothing secret.

Uses the owner connection (DATABASE_URL_UNPOOLED / DATABASE_URL from .env or web/.env.local), creates
role `dashboard_ro` with a fresh random password, grants CONNECT + USAGE + SELECT on every table now and
on tables the owner creates later (each reload recreates them), then writes the read-only URL (pooled host)
to --out (a git-ignored env file) so it can be piped into `vercel env add DATABASE_URL_READONLY production`.

  .venv/bin/python web/make_readonly_role.py --out web/.env.readonly.local
"""

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_db import load_env  # noqa: E402  (reads .env and web/.env.local without printing values)

ROLE = "dashboard_ro"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="git-ignored env file to write DATABASE_URL_READONLY into")
    a = ap.parse_args(argv)
    load_env()
    owner = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
    pooled = os.environ.get("DATABASE_URL") or owner
    if not owner:
        raise SystemExit("DATABASE_URL is not set (web/.env.local or .env)")
    import psycopg
    from psycopg import sql
    password = secrets.token_urlsafe(32)
    with psycopg.connect(owner, autocommit=True) as con:
        owner_role = con.execute("SELECT current_user").fetchone()[0]
        db = con.execute("SELECT current_database()").fetchone()[0]
        exists = con.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        con.execute(sql.SQL(verb + " ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(ROLE), sql.Literal(password)))
        for stmt in ("GRANT CONNECT ON DATABASE {db} TO {r}", "GRANT USAGE ON SCHEMA public TO {r}",
                     "GRANT SELECT ON ALL TABLES IN SCHEMA public TO {r}",
                     "ALTER DEFAULT PRIVILEGES FOR ROLE {o} IN SCHEMA public GRANT SELECT ON TABLES TO {r}",
                     "ALTER ROLE {r} SET default_transaction_read_only = on"):
            con.execute(sql.SQL(stmt).format(db=sql.Identifier(db), r=sql.Identifier(ROLE), o=sql.Identifier(owner_role)))
    u = urlsplit(pooled)
    host = u.hostname + (f":{u.port}" if u.port else "")
    ro = urlunsplit((u.scheme, f"{ROLE}:{quote(password, safe='')}@{host}", u.path, u.query, u.fragment))
    with psycopg.connect(ro) as con:  # prove it can read and cannot write
        n = con.execute("SELECT count(*) FROM reviews").fetchone()[0]
        try:
            con.execute("CREATE TABLE ro_probe (x int)")
            raise SystemExit("read-only role could create a table; refusing to use it")
        except psycopg.Error:
            con.rollback()
    out = Path(a.out)
    out.write_text(f"DATABASE_URL_READONLY={ro}\n", encoding="utf-8")
    os.chmod(out, 0o600)
    print(f"[ro-role] {verb.lower()}d role {ROLE}: reads {n} reviews, writes refused; URL written to {out} (not printed)")


if __name__ == "__main__":
    main()
