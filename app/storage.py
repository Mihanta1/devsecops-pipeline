import os

import psycopg
from psycopg.rows import dict_row


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("La variable d'environnement DATABASE_URL est obligatoire.")
    return psycopg.connect(database_url, row_factory=dict_row)


def init_db() -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            create table if not exists tasks (
                id serial primary key,
                title text not null,
                done boolean not null default false
            );
        """)


def list_tasks() -> list[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("select id, title, done from tasks order by id;")
        return cur.fetchall()


def get_task(task_id: int) -> dict | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("select id, title, done from tasks where id = %s;", (task_id,))
        return cur.fetchone()


def create_task(title: str) -> dict:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into tasks (title, done) values (%s, false) returning id, title, done;",
            (title,)
        )
        return cur.fetchone()


def delete_task(task_id: int) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("delete from tasks where id = %s;", (task_id,))
        return cur.rowcount > 0


def reset() -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("truncate table tasks restart identity;")