from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
   title: str = Field(min_length=1, max_length=200)


class Task(BaseModel):
    id: int
    title: str
    done: bool = False