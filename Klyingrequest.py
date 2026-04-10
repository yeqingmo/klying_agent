# -*- coding: utf-8 -*-
"""Kling OmniVideo request runner with submit/check/mock/resume support."""

import argparse
import json
import os
import re
import time
import uuid
from typing import Any, Iterable

import requests

from KlyingApi import encode_jwt_token
from KlyingCallback import callback_event_to_check_result, load_callback_event
from Klyingcheck import extract_task_id_from_submit_response, poll_task_until_done

API_URL = "https://api-beijing.klingai.com/v1/videos/omni-video"
ALLOWED_REFER_TYPES = {"base", "feature"}
ALLOWED_MODES = {"std", "pro"}
ALLOWED_ASPECT_RATIOS = {"16:9", "9:16", "1:1"}
PLACEHOLDER_RE = re.compile(r"<<<(image|video|element)_(\d+)>>>")


def _load_env_file(file_path: str = ".env") -> None:
    if not os.path.exists(file_path):
        return
    with open(file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
                value = value[1:-1]
            os.environ.setdefault(key, value)


def _to_yes_no(value: bool | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).strip().lower()
    if text in {"yes", "true", "1"}:
        return "yes"
    if text in {"no", "false", "0"}:
        return "no"
    raise ValueError("keep_original_sound must be bool or yes/no.")


def _normalize_image_list(images: Iterable[str | dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not images:
        return []
    result: list[dict[str, Any]] = []
    for item in images:
        if isinstance(item, str):
            result.append({"image_url": item})
            continue
        if not isinstance(item, dict):
            raise ValueError("Each image must be a URL string or a dict.")
        image_url = item.get("image_url")
        if not image_url:
            raise ValueError("Image dict must contain image_url.")
        normalized = {"image_url": image_url}
        if item.get("type"):
            normalized["type"] = item["type"]
        result.append(normalized)
    return result


def _normalize_video_list(
    videos: Iterable[str | dict[str, Any]] | None,
    default_refer_type: str,
    default_keep_sound: bool | str | None,
) -> list[dict[str, Any]]:
    if not videos:
        return []
    keep_sound_default = _to_yes_no(default_keep_sound)
    result: list[dict[str, Any]] = []
    for item in videos:
        if isinstance(item, str):
            video_url = item
            refer_type = default_refer_type
            keep_sound = keep_sound_default
        elif isinstance(item, dict):
            video_url = item.get("video_url")
            refer_type = item.get("refer_type", default_refer_type)
            keep_sound = _to_yes_no(item.get("keep_original_sound", keep_sound_default))
        else:
            raise ValueError("Each video must be a URL string or a dict.")

        if not video_url:
            raise ValueError("Video item must contain video_url.")
        if refer_type not in ALLOWED_REFER_TYPES:
            raise ValueError(f"refer_type must be one of {sorted(ALLOWED_REFER_TYPES)}.")

        normalized = {"video_url": video_url, "refer_type": refer_type}
        if keep_sound is not None:
            normalized["keep_original_sound"] = keep_sound
        result.append(normalized)
    return result


def _validate_prompt_placeholders(prompt: str, image_count: int, video_count: int, element_count: int) -> None:
    max_index = {"image": 0, "video": 0, "element": 0}
    for kind, idx in PLACEHOLDER_RE.findall(prompt):
        max_index[kind] = max(max_index[kind], int(idx))

    if max_index["image"] > image_count:
        raise ValueError(f"Prompt uses image_{max_index['image']} but only {image_count} image(s) were provided.")
    if max_index["video"] > video_count:
        raise ValueError(f"Prompt uses video_{max_index['video']} but only {video_count} video(s) were provided.")
    if max_index["element"] > element_count:
        raise ValueError(f"Prompt uses element_{max_index['element']} but only {element_count} element(s) were provided.")


def build_omnivideo_payload(
    *,
    model_name: str = "kling-video-o1",
    prompt: str,
    mode: str = "pro",
    aspect_ratio: str | None = "16:9",
    seconds: int | str | None = None,
    image_list: Iterable[str | dict[str, Any]] | None = None,
    element_ids: Iterable[str | int] | None = None,
    video_list: Iterable[str | dict[str, Any]] | None = None,
    refer_type: str = "base",
    keep_original_sound: bool | str | None = None,
    callback_url: str | None = None,
    external_task_id: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not prompt or not prompt.strip():
        raise ValueError("prompt cannot be empty.")
    if mode not in ALLOWED_MODES:
        raise ValueError(f"mode must be one of {sorted(ALLOWED_MODES)}.")
    if refer_type not in ALLOWED_REFER_TYPES:
        raise ValueError(f"refer_type must be one of {sorted(ALLOWED_REFER_TYPES)}.")
    if aspect_ratio is not None and aspect_ratio not in ALLOWED_ASPECT_RATIOS:
        raise ValueError(f"aspect_ratio must be one of {sorted(ALLOWED_ASPECT_RATIOS)}.")

    normalized_images = _normalize_image_list(image_list)
    normalized_elements = [{"element_id": str(x)} for x in (element_ids or [])]
    normalized_videos = _normalize_video_list(video_list, refer_type, keep_original_sound)

    if not normalized_videos:
        raise ValueError("video_list is required for video edit/reference mode.")
    if seconds is not None and any(v["refer_type"] == "base" for v in normalized_videos):
        raise ValueError("Do not pass seconds when refer_type is base.")

    _validate_prompt_placeholders(prompt, len(normalized_images), len(normalized_videos), len(normalized_elements))

    payload: dict[str, Any] = {
        "model_name": model_name,
        "prompt": prompt.strip(),
        "mode": mode,
        "aspect_ratio": aspect_ratio,
        "video_list": normalized_videos,
    }
    if normalized_images:
        payload["image_list"] = normalized_images
    if seconds is not None:
        payload["seconds"] = str(seconds)
    if normalized_elements:
        payload["element_list"] = normalized_elements
    if callback_url:
        payload["callback_url"] = callback_url
    if external_task_id:
        payload["external_task_id"] = external_task_id
    if extra_fields:
        payload.update(extra_fields)
    return payload


def submit_omnivideo_task(*, api_token: str, payload: dict[str, Any], api_url: str = API_URL, timeout: int = 60) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        # 尽量把服务端返回体带出来，方便定位 400/401 等错误原因。
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code} error from Kling API: {detail}") from e
    return resp.json()


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _load_payload_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.payload_json and args.payload_file:
        raise ValueError("Use only one of --payload-json or --payload-file.")
    if args.payload_json:
        data = json.loads(args.payload_json)
    elif args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    else:
        return None
    if not isinstance(data, dict):
        raise ValueError("Payload JSON root must be an object.")
    return data


def _validate_payload_contract(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("payload.prompt is required and must be a non-empty string.")

    mode = payload.get("mode", "pro")
    if mode not in ALLOWED_MODES:
        raise ValueError(f"payload.mode must be one of {sorted(ALLOWED_MODES)}.")
    payload["mode"] = mode

    aspect_ratio = payload.get("aspect_ratio", "16:9")
    if aspect_ratio not in ALLOWED_ASPECT_RATIOS:
        raise ValueError(f"payload.aspect_ratio must be one of {sorted(ALLOWED_ASPECT_RATIOS)}.")
    payload["aspect_ratio"] = aspect_ratio

    normalized_images = _normalize_image_list(payload.get("image_list"))
    if normalized_images:
        payload["image_list"] = normalized_images
    else:
        payload.pop("image_list", None)

    videos_raw = payload.get("video_list")
    if not isinstance(videos_raw, list) or not videos_raw:
        raise ValueError("payload.video_list is required and must contain at least one video.")

    normalized_videos: list[dict[str, Any]] = []
    for idx, item in enumerate(videos_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"payload.video_list[{idx}] must be an object.")
        video_url = item.get("video_url")
        refer_type = item.get("refer_type")
        if not video_url:
            raise ValueError(f"payload.video_list[{idx}].video_url is required.")
        if refer_type not in ALLOWED_REFER_TYPES:
            raise ValueError(
                f"payload.video_list[{idx}].refer_type is required and must be one of {sorted(ALLOWED_REFER_TYPES)}."
            )
        normalized_item = {"video_url": video_url, "refer_type": refer_type}
        keep_sound = _to_yes_no(item.get("keep_original_sound"))
        if keep_sound is not None:
            normalized_item["keep_original_sound"] = keep_sound
        normalized_videos.append(normalized_item)
    payload["video_list"] = normalized_videos

    if "seconds" in payload and any(v["refer_type"] == "base" for v in normalized_videos):
        raise ValueError("Do not pass payload.seconds when refer_type is base.")

    element_list = payload.get("element_list", [])
    element_count = len(element_list) if isinstance(element_list, list) else 0
    _validate_prompt_placeholders(prompt, len(normalized_images), len(normalized_videos), element_count)

    if not payload.get("model_name") and not payload.get("model"):
        payload["model_name"] = "kling-video-o1"
    return payload


def _resolve_api_token(args: argparse.Namespace) -> str:
    if args.api_token:
        return args.api_token
    env_token = os.getenv("KLING_API_TOKEN")
    if env_token:
        return env_token

    access_key = args.access_key or os.getenv("KLING_ACCESS_KEY")
    secret_key = args.secret_key or os.getenv("KLING_SECRET_KEY")
    if access_key and secret_key:
        return encode_jwt_token(access_key=access_key, secret_key=secret_key, expire_seconds=args.token_expire_seconds)

    raise ValueError(
        "Missing credential. Provide --api-token, or provide --access-key and --secret-key, "
        "or set KLING_API_TOKEN / KLING_ACCESS_KEY / KLING_SECRET_KEY."
    )


def _save_task_id_to_file(file_path: str, task_id: str) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({"task_id": task_id}, f, ensure_ascii=False, indent=2)


def _load_task_id_from_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        raise ValueError(f"Task id file is empty: {file_path}")
    if raw.startswith("{"):
        data = json.loads(raw)
        task_id = data.get("task_id") if isinstance(data, dict) else None
        if not task_id:
            raise ValueError(f"Cannot find task_id in JSON file: {file_path}")
        return str(task_id)
    return raw


def _mock_submit_response() -> dict[str, Any]:
    task_id = str(int(time.time() * 1000))
    now_ms = int(time.time() * 1000)
    return {
        "code": 0,
        "message": "SUCCEED",
        "request_id": str(uuid.uuid4()),
        "data": {
            "task_id": task_id,
            "task_status": "submitted",
            "task_info": {},
            "created_at": now_ms,
            "updated_at": now_ms,
        },
    }


def _mock_check_result(task_id: str, output_url: str, duration_seconds: float) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "state": "succeed",
        "task_id": task_id,
        "task_status": "succeed",
        "final_video_url": output_url,
        "raw": {
            "code": 0,
            "message": "SUCCEED",
            "request_id": str(uuid.uuid4()),
            "data": {
                "task_id": task_id,
                "task_status": "succeed",
                "task_info": {},
                "task_result": {"videos": [{"id": str(now_ms + 1), "url": output_url, "duration": f"{duration_seconds:.3f}"}]},
                "task_status_msg": "",
                "created_at": now_ms - 3000,
                "updated_at": now_ms,
                "final_unit_deduction": "0",
            },
        },
    }


def _write_json_file(file_path: str, data: dict[str, Any]) -> None:
    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_result_json_path(result_dir: str, base_name: str, task_id: str | None) -> str:
    os.makedirs(result_dir, exist_ok=True)
    clean_task_id = task_id or "unknown_task"
    base = os.path.basename(base_name)
    stem, ext = os.path.splitext(base)
    if not ext:
        ext = ".json"
    return os.path.join(result_dir, f"{stem}_{clean_task_id}{ext}")


def _build_modular_result(
    *,
    task_id: str | None,
    submit_response: dict[str, Any] | None,
    check_result: dict[str, Any] | None,
    resumed_from_task_id_file: str | None,
    auto_check_attempts: int,
    auto_check_max_attempts: int,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    status = "unknown"
    if check_result:
        status = str(check_result.get("state", "unknown"))
    elif submit_response:
        status = "submitted"

    task_id_stamp = f"{task_id}_{now_ms}" if task_id else None
    return {
        "task": {
            "task_id": task_id,
            "status": status,
            "resumed_from_task_id_file": resumed_from_task_id_file,
        },
        "submit": submit_response,
        "check": check_result,
        "meta": {
            "auto_check_attempts_used": auto_check_attempts,
            "auto_check_max_attempts": auto_check_max_attempts,
            "generated_at_ms": now_ms,
            "task_id_stamp": task_id_stamp,
        },
    }


def main() -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=".env")
    pre_args, _ = pre_parser.parse_known_args()
    _load_env_file(pre_args.env_file)

    parser = argparse.ArgumentParser(description="Build and submit Kling OmniVideo requests.")
    parser.add_argument("--env-file", default=".env", help="Path to local .env file.")
    parser.add_argument("--api-token", default=None, help="Direct API token.")
    parser.add_argument("--access-key", default=None, help="Kling Access Key (AK).")
    parser.add_argument("--secret-key", default=None, help="Kling Secret Key (SK).")
    parser.add_argument("--token-expire-seconds", type=int, default=1800)

    parser.add_argument("--prompt", default=None)
    parser.add_argument("--video-urls", default=None, help="Comma-separated video URLs.")
    parser.add_argument("--image-urls", default=None, help="Comma-separated image URLs.")
    parser.add_argument("--refer-type", default=None, choices=sorted(ALLOWED_REFER_TYPES))
    parser.add_argument("--keep-original-sound", default=None)
    parser.add_argument("--element-ids", default="")
    parser.add_argument("--mode", default="pro", choices=sorted(ALLOWED_MODES))
    parser.add_argument("--aspect-ratio", default="16:9", choices=sorted(ALLOWED_ASPECT_RATIOS))
    parser.add_argument("--seconds", default=None)
    parser.add_argument("--callback-url", default=None)
    parser.add_argument("--external-task-id", default=None)

    parser.add_argument("--payload-json", default=None)
    parser.add_argument("--payload-file", default=None)

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--mock-output-url", default="https://example.com/mock-output.mp4")
    parser.add_argument("--mock-duration-seconds", type=float, default=5.0)

    parser.add_argument("--save-task-id-file", default=None)
    parser.add_argument("--resume-task-id-file", default=None)
    parser.add_argument("--clear-task-id-file-on-finish", action="store_true")

    parser.add_argument("--auto-check", action="store_true")
    parser.add_argument("--auto-check-max-attempts", type=int, default=10)
    parser.add_argument("--auto-check-retry-sleep-seconds", type=int, default=3)
    parser.add_argument("--check-interval", type=int, default=10)
    parser.add_argument("--check-max-wait", type=int, default=1800)
    parser.add_argument("--check-request-timeout", type=int, default=60)

    parser.add_argument("--result-json-file", default="kling_result.json")
    parser.add_argument("--result-dir", default="result")
    parser.add_argument("--prefer-callback", action="store_true", help="Prefer callback state over polling when available.")
    parser.add_argument("--callback-store-dir", default=os.path.join("result", "callback_state"))
    parser.add_argument("--pipe-output", action="store_true")
    args = parser.parse_args()

    resume_mode = bool(args.resume_task_id_file)

    api_token: str | None = None
    submit_result: dict[str, Any] | None = None
    check_result: dict[str, Any] | None = None
    task_id: str | None = None
    auto_check_attempts_used = 0

    if resume_mode:
        task_id = _load_task_id_from_file(args.resume_task_id_file)
    else:
        payload_from_json = _load_payload_from_args(args)
        if payload_from_json is not None:
            payload = _validate_payload_contract(payload_from_json)
        else:
            if not args.prompt:
                raise ValueError("--prompt is required in args mode.")
            if not args.video_urls:
                raise ValueError("--video-urls is required in args mode.")
            if not args.refer_type:
                raise ValueError("--refer-type is required in args mode and must be base/feature.")

            payload = build_omnivideo_payload(
                prompt=args.prompt,
                mode=args.mode,
                aspect_ratio=args.aspect_ratio,
                seconds=args.seconds,
                image_list=_parse_csv(args.image_urls),
                element_ids=_parse_csv(args.element_ids),
                video_list=_parse_csv(args.video_urls),
                refer_type=args.refer_type,
                keep_original_sound=args.keep_original_sound,
                callback_url=args.callback_url,
                external_task_id=args.external_task_id,
            )
            payload = _validate_payload_contract(payload)

        if not args.pipe_output:
            print("Payload:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        if args.dry_run:
            if args.pipe_output:
                print(json.dumps({"payload": payload}, ensure_ascii=False))
            return

        if args.mock:
            submit_result = _mock_submit_response()
        else:
            api_token = _resolve_api_token(args)
            submit_result = submit_omnivideo_task(api_token=api_token, payload=payload)

        task_id = extract_task_id_from_submit_response(submit_result)
        if args.save_task_id_file:
            _save_task_id_to_file(args.save_task_id_file, task_id)

        submit_stage_result = _build_modular_result(
            task_id=task_id,
            submit_response=submit_result,
            check_result=None,
            resumed_from_task_id_file=None,
            auto_check_attempts=0,
            auto_check_max_attempts=args.auto_check_max_attempts,
        )
        submit_path = _resolve_result_json_path(args.result_dir, args.result_json_file, task_id)
        _write_json_file(submit_path, submit_stage_result)
        if not args.pipe_output:
            print(f"Task submitted. task_id={task_id}")
            print(f"Submit-stage JSON saved to: {submit_path}")

    do_auto_check = args.auto_check or resume_mode
    if not do_auto_check:
        modular = _build_modular_result(
            task_id=task_id,
            submit_response=submit_result,
            check_result=None,
            resumed_from_task_id_file=args.resume_task_id_file if resume_mode else None,
            auto_check_attempts=0,
            auto_check_max_attempts=args.auto_check_max_attempts,
        )
        result_path = _resolve_result_json_path(args.result_dir, args.result_json_file, task_id)
        _write_json_file(result_path, modular)

        if args.pipe_output:
            print(json.dumps(modular, ensure_ascii=False))
        else:
            if submit_result is not None:
                print("Response:")
                print(json.dumps(submit_result, ensure_ascii=False, indent=2))
            else:
                print("No submit result. Use --auto-check or remove resume mode.")
            print(f"Result JSON saved to: {result_path}")
        return

    if not task_id:
        raise ValueError("Missing task_id for polling.")

    max_attempts = max(1, int(args.auto_check_max_attempts))
    for attempt in range(1, max_attempts + 1):
        auto_check_attempts_used = attempt

        if args.prefer_callback:
            event = load_callback_event(task_id, args.callback_store_dir)
            if event:
                callback_check = callback_event_to_check_result(event)
                callback_state = str(callback_check.get("state", "")).lower()
                if callback_state in {"succeed", "failed"}:
                    check_result = callback_check
                    break

        if args.mock:
            check_result = _mock_check_result(task_id, args.mock_output_url, args.mock_duration_seconds)
        else:
            if not api_token:
                api_token = _resolve_api_token(args)
            check_result = poll_task_until_done(
                api_token=api_token,
                task_id=task_id,
                poll_interval_seconds=args.check_interval,
                max_wait_seconds=args.check_max_wait,
                timeout_per_request=args.check_request_timeout,
            )

        state = str((check_result or {}).get("state", "")).lower()
        if state in {"succeed", "failed"}:
            break
        if attempt < max_attempts:
            time.sleep(max(0, int(args.auto_check_retry_sleep_seconds)))

    if check_result is None:
        check_result = {
            "state": "error",
            "task_id": task_id,
            "task_status": "unknown",
            "error": "No check result generated.",
            "raw": None,
        }
    elif str(check_result.get("state", "")).lower() not in {"succeed", "failed"}:
        check_result = {
            **check_result,
            "state": "error",
            "task_id": task_id,
            "error": (
                f"Auto-check did not succeed after {auto_check_attempts_used} attempts. "
                "You can continue later with --resume-task-id-file."
            ),
        }

    if args.clear_task_id_file_on_finish and args.resume_task_id_file and check_result.get("state") in {"succeed", "failed"}:
        try:
            os.remove(args.resume_task_id_file)
        except OSError:
            pass

    merged = _build_modular_result(
        task_id=task_id,
        submit_response=submit_result,
        check_result=check_result,
        resumed_from_task_id_file=args.resume_task_id_file if resume_mode else None,
        auto_check_attempts=auto_check_attempts_used,
        auto_check_max_attempts=max_attempts,
    )
    result_path = _resolve_result_json_path(args.result_dir, args.result_json_file, task_id)
    _write_json_file(result_path, merged)

    if args.pipe_output:
        print(json.dumps(merged, ensure_ascii=False))
        return

    print("Submit Response:")
    print(json.dumps(submit_result, ensure_ascii=False, indent=2))
    print("Auto Check Result:")
    print(json.dumps(check_result, ensure_ascii=False, indent=2))
    print(f"Result JSON saved to: {result_path}")
    if check_result.get("state") == "succeed" and check_result.get("final_video_url"):
        print(f"Final video URL: {check_result['final_video_url']}")


if __name__ == "__main__":
    main()
