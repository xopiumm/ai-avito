from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

mcp = FastMCP("todo-mcp")

DATA_FILE = Path("todo_data.json")


def _load_tasks() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_tasks(tasks: list[dict[str, Any]]) -> None:
    DATA_FILE.write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@mcp.tool
def list_tasks() -> list[dict[str, Any]]:
    """Return all tasks."""
    return _load_tasks()


@mcp.tool
def add_task(title: str, description: str = "") -> dict[str, Any]:
    """Add a new task."""
    tasks = _load_tasks()
    next_id = max((task["id"] for task in tasks), default=0) + 1

    task = {
        "id": next_id,
        "title": title,
        "description": description,
        "done": False,
    }
    tasks.append(task)
    _save_tasks(tasks)
    return task


@mcp.tool
def complete_task(task_id: int) -> dict[str, Any]:
    """Mark a task as completed."""
    tasks = _load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            _save_tasks(tasks)
            return task
    raise ValueError(f"Task with id={task_id} not found")


@mcp.tool
def search_tasks(query: str) -> list[dict[str, Any]]:
    """Search tasks by title or description."""
    q = query.lower().strip()
    return [
        task
        for task in _load_tasks()
        if q in task["title"].lower() or q in task["description"].lower()
    ]


if __name__ == "__main__":
    mcp.run()