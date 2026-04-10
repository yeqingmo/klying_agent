# -*- coding: utf-8 -*-
"""Kling callback storage helpers."""

import json
import os
import time
from typing import Any


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _state_file(task_id: str, store_dir: str) -> str:
    _ensure_dir(store_dir)
    return os.path.join(store_dir, f"{task_id}.json")


def _events_file(task_id: str, store_dir: str) -> str:
    _ensure_dir(store_dir)
    return os.path.join(store_dir, f"events_{task_id}.jsonl")


def save_callback_event(event: dict[str, Any], store_dir: str) -> str:
    """
    Save callback event by task_id, and append raw event log.
    Returns state file path.
    """
    task_id = str(event.get("task_id", "")).strip()
    if not task_id:
        raise ValueError("callback event missing task_id")

    state_path = _state_file(task_id, store_dir)
    now_ms = int(time.time() * 1000)
    event = {**event, "_received_at_ms": now_ms}

    previous: dict[str, Any] | None = None
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                previous = json.load(f)
        except Exception:
            previous = None

    should_replace = True
    if previous:
        prev_updated = int(previous.get("updated_at", 0) or 0)
        cur_updated = int(event.get("updated_at", 0) or 0)
        if cur_updated and prev_updated and cur_updated < prev_updated:
            should_replace = False

    if should_replace:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(event, f, ensure_ascii=False, indent=2)

    with open(_events_file(task_id, store_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return state_path


def load_callback_event(task_id: str, store_dir: str) -> dict[str, Any] | None:
    """Load latest callback state for task_id."""
    path = _state_file(task_id, store_dir)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else None


def callback_event_to_check_result(event: dict[str, Any]) -> dict[str, Any]:
    """Convert callback payload to check_result-like structure."""
    status = str(event.get("task_status", "")).lower()
    videos = (event.get("task_result") or {}).get("videos") or []
    final_video_url = None
    if isinstance(videos, list) and videos and isinstance(videos[0], dict):
        final_video_url = videos[0].get("url")

    if status == "succeed":
        state = "succeed"
    elif status == "failed":
        state = "failed"
    elif status in {"submitted", "processing"}:
        state = "processing"
    else:
        state = "error"

    return {
        "state": state,
        "task_id": event.get("task_id"),
        "task_status": status,
        "final_video_url": final_video_url,
        "error": event.get("task_status_msg") if state in {"failed", "error"} else None,
        "raw": {
            "source": "callback",
            "event": event,
        },
    }
