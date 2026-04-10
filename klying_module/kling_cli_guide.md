# Kling CLI 使用手册（当前版本）

本文覆盖当前仓库新增能力：
- 自动轮询 + 最多重试次数
- 断点续查
- 结果文件自动按 `task_id` 命名并写入 `result/`
- 回调服务接入（callback）
- 回调优先 + 轮询兜底
- mock 联调

---

## 1. 常用命令

### 1.1 纯轮询（已有 task_id）

```cmd
python Klyingcheck.py --api-token "你的token" --task-id 你的task_id --pipe-output
```

### 1.2 提交 + 自动轮询（推荐）

```cmd
python Klyingrequest.py --payload-file request_base.json --auto-check --auto-check-max-attempts 10 --result-json-file kling_result.json --pipe-output
```

### 1.3 断点续查（不重复提交）

```cmd
python Klyingrequest.py --resume-task-id-file last_task.json --auto-check --pipe-output
```

---

## 2. 结果文件规则（新增）

`Klyingrequest.py` 会把结果写进 `result/` 目录，文件名自动拼 `task_id`：

- 目录：`result/`
- 命名：`{result-json-file去后缀}_{task_id}.json`
- 示例：`result/kling_result_871261538660278331.json`

相关参数：

- `--result-json-file kling_result.json`：结果文件基础名
- `--result-dir result`：结果目录

---

## 3. 自动轮询与重试（新增）

当你开启 `--auto-check` 后：

- 脚本会自动查任务状态
- 如果没到终态，会按设置重试
- 默认最多重试 10 轮

相关参数：

- `--auto-check`
- `--auto-check-max-attempts 10`
- `--auto-check-retry-sleep-seconds 3`
- `--check-interval 10`
- `--check-max-wait 1800`
- `--check-request-timeout 60`

---

## 4. 断点续查（新增）

### 4.1 首次提交保存 task_id

```cmd
python Klyingrequest.py --payload-file request_base.json --auto-check --save-task-id-file last_task.json --pipe-output
```

### 4.2 后续从文件恢复

```cmd
python Klyingrequest.py --resume-task-id-file last_task.json --auto-check --pipe-output
```

### 4.3 完成后自动清理断点文件

```cmd
python Klyingrequest.py --resume-task-id-file last_task.json --auto-check --clear-task-id-file-on-finish --pipe-output
```

---

## 5. 回调服务接入（新增）

### 5.1 启动回调服务

```cmd
python Klyingcallback_server.py --host 0.0.0.0 --port 8080 --path /kling/callback
```

可选 token 校验：

```cmd
python Klyingcallback_server.py --host 0.0.0.0 --port 8080 --path /kling/callback --token "你的回调token"
```

### 5.2 请求里设置 callback_url

在 payload JSON 中增加：

```json
"callback_url": "https://你的公网域名/kling/callback"
```

### 5.3 回调优先（有回调先用回调）

```cmd
python Klyingrequest.py --payload-file request_base.json --auto-check --prefer-callback --pipe-output
```

说明：
- 开了 `--prefer-callback` 时，脚本会先读回调落盘状态
- 若回调没到，再走轮询兜底

回调落盘目录：`result/callback_state/`

- 任务最新状态：`{task_id}.json`
- 事件日志：`events_{task_id}.jsonl`

---

## 6. 认证方式

支持三种：

1. 直接 token：`--api-token`
2. AK/SK：`--access-key` + `--secret-key`
3. `.env` 自动读取（默认）

`.env` 示例：

```env
KLING_ACCESS_KEY=你的AK
KLING_SECRET_KEY=你的SK
```

如果不是默认 `.env`，可指定：

```cmd
python Klyingrequest.py --env-file "D:\path\custom.env" --payload-file request_base.json --auto-check
```

---

## 7. Mock 联调（不扣费）

```cmd
python Klyingrequest.py --payload-file request_base.json --auto-check --mock --pipe-output
```

可自定义 mock 输出视频地址：

```cmd
python Klyingrequest.py --payload-file request_base.json --auto-check --mock --mock-output-url "https://example.com/demo.mp4" --pipe-output
```

---

## 8. 常见错误

### 8.1 `400 Client Error`

说明请求已到可灵，但参数不合法。优先检查：

- 占位符必须是 `<<<video_1>>>` / `<<<image_1>>>`
- `video_list` 必填
- `refer_type` 只能 `base` / `feature`
- `base` 模式不要传 `seconds`
- JSON 不能写 `//` 注释

### 8.2 `401 Client Error`

token 无效或过期。重生成 token 或检查 AK/SK。

### 8.3 `SSLEOFError`

网络/TLS 抖动。优先用已有 `task_id` 续查，不要重复提交。
