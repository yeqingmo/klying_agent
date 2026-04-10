"""
Kling OmniVideo 任务轮询模块。

这个文件用于“查任务是否生成完成”，并且支持接收“上一步创建任务接口返回值”：
- 直接传 task_id
- 直接传创建接口响应 JSON 字符串
- 从 JSON 文件读取
- 从 stdin 读取（适合 shell 管线）

典型管线：
python Klyingrequest.py ... --pipe-output | python Klyingcheck.py --from-stdin --api-token xxx
"""

import argparse
import json
import os
import sys
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

QUERY_API_URL_TEMPLATE = "https://api-beijing.klingai.com/v1/videos/omni-video/{task_id}"
RUNNING_STATUSES = {"submitted", "processing"}
SUCCESS_STATUSES = {"succeed", "success", "completed"}
FAILED_STATUSES = {"failed", "error"}


def _safe_json_loads(raw: str) -> dict[str, Any]:
    """
    将字符串解析为 JSON 对象，并确保结果是 dict。
    """
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")
    return data


def extract_task_id_from_submit_response(submit_response: dict[str, Any]) -> str:
    """
    从“创建任务响应”中提取 task_id。

    兼容常见结构：
    - {"data": {"task_id": "..."}}
    - {"task_id": "..."}
    """
    task_id = (
        submit_response.get("data", {}).get("task_id")
        if isinstance(submit_response.get("data"), dict)
        else None
    ) or submit_response.get("task_id")

    if not task_id:
        raise ValueError("task_id not found in submit response JSON.")
    return str(task_id)


def query_task_once(
    *,
    api_token: str,
    task_id: str,
    timeout: int = 60,
    connect_retries: int = 3,
) -> dict[str, Any]:
    """
    查询一次任务状态，返回服务端原始响应 JSON。
    """
    url = QUERY_API_URL_TEMPLATE.format(task_id=task_id)
    headers = {"Authorization": f"Bearer {api_token}"}

    # 为查询接口建立一个带重试的会话，提升短时网络抖动/SSL EOF 场景下的成功率。
    retry = Retry(
        total=connect_retries,
        connect=connect_retries,
        read=connect_retries,
        status=connect_retries,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))

    response = session.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def normalize_task_state(query_response: dict[str, Any]) -> dict[str, Any]:
    """
    将服务端响应归一化，便于上层处理。
    """
    data = query_response.get("data", {}) if isinstance(query_response.get("data"), dict) else {}
    task_status = str(data.get("task_status", "")).lower()

    videos = data.get("task_result", {}).get("videos", [])
    final_video_url = None
    if isinstance(videos, list) and videos and isinstance(videos[0], dict):
        final_video_url = videos[0].get("url")

    return {
        "code": query_response.get("code"),
        "message": query_response.get("message"),
        "task_id": data.get("task_id"),
        "task_status": task_status,
        "task_status_msg": data.get("task_status_msg"),
        "final_video_url": final_video_url,
        "raw": query_response,
    }


def poll_task_until_done(
    *,
    api_token: str,
    task_id: str,
    poll_interval_seconds: int = 10,
    max_wait_seconds: int = 1800,
    timeout_per_request: int = 60,
    connect_retries_per_request: int = 3,
) -> dict[str, Any]:
    """
    轮询任务直到完成/失败/超时。

    返回统一结构：
    - state: "succeed" | "failed" | "timeout" | "error"
    - task_id / task_status / final_video_url / raw
    """
    start_ts = time.time()
    last_network_error: str | None = None
    while True:
        try:
            query_raw = query_task_once(
                api_token=api_token,
                task_id=task_id,
                timeout=timeout_per_request,
                connect_retries=connect_retries_per_request,
            )
            last_network_error = None
        except requests.exceptions.RequestException as e:
            # 网络层异常（如 SSLEOFError）不立刻中断任务，继续轮询直到超时。
            last_network_error = str(e)
            elapsed = time.time() - start_ts
            if elapsed >= max_wait_seconds:
                return {
                    "state": "timeout",
                    "task_id": task_id,
                    "task_status": "network_error",
                    "error": f"Polling timeout after repeated network errors: {last_network_error}",
                    "raw": None,
                }
            time.sleep(poll_interval_seconds)
            continue

        state = normalize_task_state(query_raw)

        # code != 0 通常表示接口层错误（鉴权、参数、服务异常等）。
        if state["code"] != 0:
            return {
                "state": "error",
                "task_id": task_id,
                "task_status": state.get("task_status"),
                "final_video_url": state.get("final_video_url"),
                "error": state.get("message"),
                "raw": state["raw"],
            }

        task_status = str(state.get("task_status", "")).lower()
        if task_status in SUCCESS_STATUSES:
            return {
                "state": "succeed",
                "task_id": task_id,
                "task_status": task_status,
                "final_video_url": state.get("final_video_url"),
                "raw": state["raw"],
            }
        if task_status in FAILED_STATUSES:
            return {
                "state": "failed",
                "task_id": task_id,
                "task_status": task_status,
                "error": state.get("task_status_msg"),
                "raw": state["raw"],
            }

        # submitted / processing 等进行中状态继续等待。
        if task_status in RUNNING_STATUSES:
            elapsed = time.time() - start_ts
            if elapsed >= max_wait_seconds:
                return {
                    "state": "timeout",
                    "task_id": task_id,
                    "task_status": task_status,
                    "error": last_network_error,
                    "raw": state["raw"],
                }
            time.sleep(poll_interval_seconds)
            continue

        # 未知状态兜底为 error，避免脚本无休止轮询。
        return {
            "state": "error",
            "task_id": task_id,
            "task_status": task_status,
            "error": f"Unknown task_status: {task_status}",
            "raw": state["raw"],
        }


def parse_submit_source_to_task_id(
    *,
    task_id: str | None,
    submit_response_json: str | None,
    submit_response_file: str | None,
    from_stdin: bool,
) -> str:
    """
    从不同输入来源解析 task_id。

    优先级：
    1) --task-id
    2) --submit-response-json
    3) --submit-response-file
    4) --from-stdin
    """
    if task_id:
        return task_id.strip()

    if submit_response_json:
        return extract_task_id_from_submit_response(_safe_json_loads(submit_response_json))

    if submit_response_file:
        with open(submit_response_file, "r", encoding="utf-8") as f:
            return extract_task_id_from_submit_response(_safe_json_loads(f.read()))

    if from_stdin:
        raw = sys.stdin.read().strip()
        if not raw:
            raise ValueError("stdin is empty, cannot parse task_id.")
        return extract_task_id_from_submit_response(_safe_json_loads(raw))

    raise ValueError("Please provide one input source: --task-id / --submit-response-json / --submit-response-file / --from-stdin")


def main() -> None:
    """
    命令行入口。
    """
    parser = argparse.ArgumentParser(description="Poll Kling OmniVideo task status.")
    parser.add_argument("--api-token", default=os.getenv("KLING_API_TOKEN"), help="Kling API token.")
    parser.add_argument("--task-id", default=None, help="Task ID to query directly.")
    parser.add_argument("--submit-response-json", default=None, help="Raw submit response JSON string.")
    parser.add_argument("--submit-response-file", default=None, help="Path of submit response JSON file.")
    parser.add_argument("--from-stdin", action="store_true", help="Read submit response JSON from stdin.")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval (seconds).")
    parser.add_argument("--max-wait", type=int, default=1800, help="Max waiting time (seconds).")
    parser.add_argument("--request-timeout", type=int, default=60, help="Single request timeout (seconds).")
    parser.add_argument(
        "--connect-retries-per-request",
        type=int,
        default=3,
        help="HTTP retry count for each query request (handles transient SSL/network failures).",
    )
    parser.add_argument("--pipe-output", action="store_true", help="Only output machine-readable JSON.")
    args = parser.parse_args()

    if not args.api_token:
        raise ValueError("Missing api token. Pass --api-token or set KLING_API_TOKEN.")

    final_task_id = parse_submit_source_to_task_id(
        task_id=args.task_id,
        submit_response_json=args.submit_response_json,
        submit_response_file=args.submit_response_file,
        from_stdin=args.from_stdin,
    )

    result = poll_task_until_done(
        api_token=args.api_token,
        task_id=final_task_id,
        poll_interval_seconds=args.interval,
        max_wait_seconds=args.max_wait,
        timeout_per_request=args.request_timeout,
        connect_retries_per_request=args.connect_retries_per_request,
    )

    if args.pipe_output:
        print(json.dumps(result, ensure_ascii=False))
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("state") == "succeed" and result.get("final_video_url"):
        print(f"Final video URL: {result['final_video_url']}")


if __name__ == "__main__":
    main()
