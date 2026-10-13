from fastapi import APIRouter, HTTPException, status
import storage
from schemas import Task, TaskCreate

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    responses={404: {"description": "Task not found"}},
)


@router.get("", response_model=list[Task])
def read_tasks():
    return storage.list_tasks()


@router.get("/{task_id}", response_model=Task)
def read_task(task_id: int):
    task = storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate):
    return storage.create_task(payload.title)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    if not storage.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")