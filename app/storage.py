tasks_db: dict[int, dict] = {}
_next_id = 1


def list_tasks() -> list[dict]:
    return list(tasks_db.values())


def get_task(task_id: int) -> dict | None:
    return tasks_db.get(task_id)


def create_task(title: str) -> dict:
    global _next_id
    task = {"id": _next_id, "title": title, "done": False}
    tasks_db[_next_id] = task
    _next_id += 1
    return task


def delete_task(task_id: int) -> bool:
    return tasks_db.pop(task_id, None) is not None


def reset() -> None:
    global _next_id
    tasks_db.clear()
    _next_id = 1