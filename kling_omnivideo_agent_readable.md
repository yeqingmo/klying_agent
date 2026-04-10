# Kling OmniVideo API（Agent 可读版）

> 来源说明：本文件根据公开可访问的二手镜像与搜索抓取结果整理而成，因为官方页面当前无法被直接抓取。建议你把它当作 **给 Agent 生成调用代码的工作草稿**，真正上线前再和官方页面逐项核对。
>
> 参考来源：
> - 官方页面搜索抓取结果：`https://kling.ai/document-api/apiReference/model/OmniVideo`
> - N1N 镜像页：`https://docs.n1n.ai/kling-omni-video`
> - AI Ping 整理页：`https://www.aiping.cn/docs/API/VideoAPI/KLING_VIDEO_API_DOC`

---

## 1. 能力概览

`Kling-Video-O1`（也常见写作 OmniVideo / Omni-Video）是可灵的多模态视频生成模型，支持：

- 文生视频
- 首帧 / 首尾帧图生视频
- 多参考图视频生成
- 主体参考（element）
- 视频参考 / 视频编辑
- 视频续写 / 前后镜头扩展

提示词里可以引用不同模态占位符：

- `<<<image_1>>>`
- `<<<image_2>>>`
- `<<<element_1>>>`
- `<<<video_1>>>`

这些占位符用于把文字 prompt 和输入素材绑定起来。

---

## 2. 已知接口信息

### 2.1 官方模型页面

- 官方文档入口（搜索结果可见）：`https://kling.ai/document-api/apiReference/model/OmniVideo`

### 2.2 镜像中可见的请求方式

N1N 镜像展示的是一个代理平台转发接口：

```http
POST https://api.n1n.ai/kling/v1/videos/omni-video
Authorization: Bearer <token>
Content-Type: application/json
```

注意：**这不是可灵官方原始域名接口**，而是兼容包装层。它能帮助我们恢复参数结构，但你接入可灵官方时，应该优先以官方接口路径与认证方式为准。

---

## 3. 核心请求字段（整理版）

下面是从镜像文档和公开抓取片段中恢复出的 `Kling-Video-O1` 主要字段。

### 3.1 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `model` / `model_name` | string | 是 | 模型名。公开资料里出现过 `Kling-Video-O1` 和 `kling-video-o1` 两种写法。接官方时以官方示例为准。 |
| `prompt` | string | 是 | 文本提示词。可包含 `<<<image_N>>>`、`<<<element_N>>>`、`<<<video_1>>>` 等引用。已知上限约 2500 字符。 |
| `mode` | string | 否 | 生成模式。已知值：`std`、`pro`。默认通常为 `pro`。 |
| `aspect_ratio` | string | 条件必填 | 画面比例。已知值：`16:9`、`9:16`、`1:1`。无首帧输入或做某些编辑场景时通常需要传。 |
| `seconds` | string / number | 否 | 视频时长。公开资料显示范围 `3`-`10` 秒，纯文生视频常见只支持 `5` / `10`。 |
| `callback_url` | string | 否 | 异步结果回调 URL。 |
| `external_task_id` | string | 否 | 业务侧自定义任务 ID，通常要求单用户唯一。 |

### 3.2 图片相关字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `first_frame_url` | string | 否 | 首帧图片 URL 或 Base64。 |
| `last_frame_url` | string | 否 | 尾帧图片 URL 或 Base64。 |
| `reference_images` | array | 否 | 参考图列表，常用于风格 / 角色 / 服装 / 构图参考。 |
| `image_list` | array | 否 | 原生格式图片输入字段。优先级通常高于平铺字段。 |

### 3.3 主体 / 视频相关字段（原生格式）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `element_list` | array | 否 | 主体引用列表。每项类似 `{ "element_id": "123" }`。 |
| `video_list` | array | 否 | 视频引用列表。每项类似 `{ "video_url": "...", "refer_type": "base" }`。 |

---

## 4. `image_list` / `reference_images` 的已知格式

### 4.1 平铺格式（兼容写法）

```json
{
  "first_frame_url": "https://example.com/first.jpg",
  "last_frame_url": "https://example.com/last.jpg",
  "reference_images": [
    { "image_url": "https://example.com/ref1.jpg" },
    { "image_url": "https://example.com/ref2.jpg" }
  ]
}
```

### 4.2 原生 `image_list` 格式

```json
{
  "image_list": [
    "https://example.com/a.jpg",
    "https://example.com/b.jpg"
  ]
}
```

```json
{
  "image_list": [
    { "image_url": "https://example.com/a.jpg" },
    { "image_url": "https://example.com/b.jpg" }
  ]
}
```

```json
{
  "image_list": [
    { "image_url": "https://example.com/first.jpg", "type": "first_frame" },
    { "image_url": "https://example.com/last.jpg", "type": "last_frame" },
    { "image_url": "https://example.com/ref.jpg" }
  ]
}
```

### 4.3 图片约束（公开资料可见）

- 支持 URL 或 Base64
- 支持 `jpg` / `jpeg` / `png`
- 单图大小通常不超过 `10MB`
- 宽高不小于 `300px`
- 宽高比需在 `1:2.5` 到 `2.5:1` 之间

---

## 5. `video_list` 的已知格式

```json
{
  "video_list": [
    {
      "video_url": "https://example.com/input.mp4",
      "refer_type": "base",
      "keep_original_sound": "yes"
    }
  ]
}
```

### 5.1 已知字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `video_url` | string | 输入视频 URL |
| `refer_type` | string | 公开示例里出现过 `base` |
| `keep_original_sound` | string / bool | 是否保留原声；公开示例出现 `"yes"` |

> `video_list` 主要用于视频编辑、视频参考、视频续写等场景。

---

## 6. `element_list` 的已知格式

```json
{
  "element_list": [
    { "element_id": "146" },
    { "element_id": "145" }
  ]
}
```

### 6.1 用法理解

- `element` 可以理解为官方主体库中的“角色 / 物体 / 主体素材引用”。
- 在 prompt 里通过 `<<<element_1>>>`、`<<<element_2>>>` 绑定。
- 当 prompt 里写 `<<<image_1>>>在东京街头漫步，偶遇<<<element_1>>>和<<<element_2>>>` 时，模型会联合参考输入图与主体库对象。

---

## 7. 常见任务模式模板

### 7.1 文生视频

```json
{
  "model": "Kling-Video-O1",
  "prompt": "一个宇航员在月球上行走，背景是地球",
  "mode": "pro",
  "aspect_ratio": "16:9",
  "seconds": "5"
}
```

### 7.2 首帧 / 首尾帧图生视频

```json
{
  "model": "Kling-Video-O1",
  "prompt": "让花被风吹动",
  "first_frame_url": "https://example.com/flower.jpg",
  "seconds": 5
}
```

更完整的首尾帧写法可整理为：

```json
{
  "model": "Kling-Video-O1",
  "prompt": "镜头从平静过渡到人物转身微笑",
  "first_frame_url": "https://example.com/start.jpg",
  "last_frame_url": "https://example.com/end.jpg",
  "mode": "pro",
  "seconds": 5,
  "aspect_ratio": "16:9"
}
```

### 7.3 图片 + 主体参考生成

```json
{
  "model": "Kling-Video-O1",
  "prompt": "<<<image_1>>>在东京街头漫步，偶遇<<<element_1>>>和<<<element_2>>>",
  "reference_images": [
    {
      "image_url": "https://example.com/ref-character.jpg"
    }
  ],
  "element_list": [
    { "element_id": "146" },
    { "element_id": "145" }
  ],
  "mode": "pro",
  "aspect_ratio": "1:1",
  "seconds": "5"
}
```

### 7.4 视频编辑 / 指令变换

```json
{
  "model": "Kling-Video-O1",
  "prompt": "给<<<video_1>>>中的女孩，拿上<<<image_1>>>中的花",
  "reference_images": [
    { "image_url": "https://example.com/flower.jpg" }
  ],
  "video_list": [
    {
      "video_url": "https://example.com/input.mp4",
      "refer_type": "base",
      "keep_original_sound": "yes"
    }
  ],
  "mode": "pro"
}
```

### 7.5 视频续写 / 镜头延长（推断模板）

```json
{
  "model": "Kling-Video-O1",
  "prompt": "延续<<<video_1>>>的运动趋势，镜头继续向前推进，人物走入霓虹街区",
  "video_list": [
    {
      "video_url": "https://example.com/clip.mp4",
      "refer_type": "base"
    }
  ],
  "mode": "pro",
  "seconds": "5"
}
```

> 这一段是依据公开“支持视频延长/前后镜头生成”的说明整理出的 agent 模板；真实可用参数组合需要以官方页面再核对一次。

---

## 8. Agent 编码时建议使用的统一数据模型

为了让 Agent 更容易自动写代码，建议先把业务输入规范成统一结构，再渲染为 API 请求。

```json
{
  "model": "Kling-Video-O1",
  "prompt": "string",
  "mode": "pro",
  "aspect_ratio": "16:9",
  "seconds": 5,
  "callback_url": "https://your-domain.com/webhook/kling",
  "external_task_id": "biz-order-001",
  "images": [
    {
      "url": "https://example.com/first.jpg",
      "role": "first_frame"
    },
    {
      "url": "https://example.com/last.jpg",
      "role": "last_frame"
    },
    {
      "url": "https://example.com/ref1.jpg",
      "role": "reference"
    }
  ],
  "elements": [
    { "element_id": "146" }
  ],
  "videos": [
    {
      "url": "https://example.com/input.mp4",
      "refer_type": "base",
      "keep_original_sound": true
    }
  ]
}
```

然后由适配器把它转换成 API body：

### 8.1 规范化到请求体的建议规则

1. `images` 中 `role=first_frame` -> `first_frame_url` 或 `image_list[].type = first_frame`
2. `images` 中 `role=last_frame` -> `last_frame_url` 或 `image_list[].type = last_frame`
3. `images` 中 `role=reference` -> `reference_images[]` 或 `image_list[]`
4. `elements[]` -> `element_list[]`
5. `videos[]` -> `video_list[]`
6. prompt 中自动校验占位符是否和素材数量一致
7. 若同时使用平铺图片字段和原生 `image_list`，优先保留 `image_list`

---

## 9. Agent 写代码时可直接依赖的规则

### 9.1 任务类型判定规则

可让 Agent 先判断任务类型，再决定字段组合：

```text
if videos 非空:
  task_type = "video_edit_or_extend"
elif elements 非空 and images 非空:
  task_type = "image_plus_element_reference"
elif first_frame 或 last_frame 非空:
  task_type = "image_to_video"
else:
  task_type = "text_to_video"
```

### 9.2 参数组合建议

#### 文生视频

- 必传：`model`, `prompt`
- 常传：`mode`, `aspect_ratio`, `seconds`

#### 图生视频

- 必传：`model`, `prompt`, 至少一张图
- 常传：`first_frame_url`
- 可选：`last_frame_url`, `seconds`, `mode`, `aspect_ratio`

#### 图片参考 + 主体参考

- 必传：`model`, `prompt`
- 参考图：`reference_images` 或 `image_list`
- 主体：`element_list`

#### 视频编辑

- 必传：`model`, `prompt`, `video_list`
- 常见补充：`reference_images`

---

## 10. 建议的错误处理与校验

Agent 生成代码时，建议内置如下校验：

### 10.1 请求前校验

- `prompt` 非空
- `prompt` 长度 <= 2500
- 图片 URL / 视频 URL 必须是外网可访问地址
- 图片格式必须是 jpg/jpeg/png
- 图片体积 <= 10MB
- `aspect_ratio` 只允许 `16:9` / `9:16` / `1:1`
- `mode` 只允许 `std` / `pro`
- `seconds` 转成字符串或整数前先做白名单校验（推荐 `3/5/10`，文本场景优先 `5/10`）
- 如果 prompt 包含 `<<<image_3>>>`，则至少应提供 3 张图片
- 如果 prompt 包含 `<<<element_2>>>`，则至少应提供 2 个 element
- 如果 prompt 包含 `<<<video_1>>>`，则必须提供 `video_list`

### 10.2 响应后处理

通常这类视频接口是异步任务制，建议统一处理为：

```json
{
  "request_id": "string",
  "task_id": "string",
  "task_status": "submitted | processing | completed | failed",
  "created_at": 0,
  "updated_at": 0,
  "raw": {}
}
```

---

## 11. 代码生成时可复用的伪规范

下面这段最适合直接喂给 Agent：

```md
You are writing client code for Kling OmniVideo.

Assume these facts:
- Model name may appear as `Kling-Video-O1` or `kling-video-o1`.
- Prompt supports placeholders like `<<<image_1>>>`, `<<<element_1>>>`, `<<<video_1>>>`.
- Images can be passed as `first_frame_url`, `last_frame_url`, `reference_images`, or native `image_list`.
- Elements must be passed as `element_list`.
- Videos must be passed as `video_list`.
- Preferred mode values: `std`, `pro`.
- Preferred aspect_ratio values: `16:9`, `9:16`, `1:1`.
- Video duration is usually 3-10 seconds, and text-to-video commonly uses 5 or 10 seconds.
- If both flat image fields and native `image_list` are present, prefer `image_list`.
- The API is likely asynchronous and may return task metadata such as `task_id` and `task_status`.

When writing code:
1. Build a JSON request body.
2. Validate placeholder counts against provided assets.
3. Validate image size/format when local files are uploaded first.
4. Support callback_url and external_task_id.
5. Return normalized task info.
6. Keep transport logic separated from request-body assembly.
```

---

## 12. 可直接给 Agent 的调用代码模板

### 12.1 cURL 模板

```bash
curl --request POST "$KLING_BASE_URL" \
  --header "Authorization: Bearer $KLING_API_KEY" \
  --header "Content-Type: application/json" \
  --data-raw '{
    "model": "Kling-Video-O1",
    "prompt": "<<<image_1>>>在雨夜街头缓慢回头",
    "reference_images": [
      { "image_url": "https://example.com/hero.jpg" }
    ],
    "mode": "pro",
    "aspect_ratio": "16:9",
    "seconds": "5",
    "callback_url": "https://your-domain.com/api/kling/callback",
    "external_task_id": "demo-001"
  }'
```

### 12.2 Python 模板

```python
import requests


def create_kling_omnivideo_task(
    base_url: str,
    api_key: str,
    body: dict,
    timeout: int = 60,
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(base_url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return {
        "request_id": data.get("request_id"),
        "task_id": data.get("data", {}).get("task_id") or data.get("task_id"),
        "task_status": data.get("data", {}).get("task_status") or data.get("task_status"),
        "raw": data,
    }


body = {
    "model": "Kling-Video-O1",
    "prompt": "一个宇航员在月球上行走，背景是地球",
    "mode": "pro",
    "aspect_ratio": "16:9",
    "seconds": "5",
}

result = create_kling_omnivideo_task(
    base_url="https://your-kling-endpoint",
    api_key="YOUR_API_KEY",
    body=body,
)
print(result)
```

### 12.3 Node.js 模板

```js
async function createKlingOmniVideoTask({ baseUrl, apiKey, body }) {
  const resp = await fetch(baseUrl, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${text}`);
  }

  const data = await resp.json();
  return {
    requestId: data.request_id,
    taskId: data?.data?.task_id ?? data.task_id,
    taskStatus: data?.data?.task_status ?? data.task_status,
    raw: data
  };
}

const body = {
  model: "Kling-Video-O1",
  prompt: "<<<video_1>>>延续原镜头运动，人物进入地铁站",
  video_list: [
    {
      video_url: "https://example.com/input.mp4",
      refer_type: "base"
    }
  ],
  mode: "pro",
  seconds: "5"
};
```

---

## 13. 我建议你下一步怎么用这个 md

你可以把这份 md 直接喂给 Agent，并附上一段固定系统指令：

```md
请基于这份 Kling OmniVideo API 说明生成调用代码。
要求：
- 默认输出 Python / Node.js / cURL 三种版本
- 自动补齐请求头
- 自动做参数校验
- 如果是异步任务接口，再补一个查询任务状态的方法
- 代码要把“参数组装”和“HTTP 发送”分层
- 未确认的字段要在代码注释里标为 TODO: verify with official docs
```

---

## 14. 风险与待核对项

以下项目在当前公开抓取条件下 **无法 100% 从官方页面逐行校验**，上线前应再次核对：

1. 官方真实创建任务接口路径
2. 官方查询任务状态接口路径
3. `model` 与 `model_name` 的最终字段名
4. `seconds` 是字符串还是数字更严格
5. `keep_original_sound` 是否允许布尔值
6. `video_list` 里是否还有其他 `refer_type`
7. `image_list.type` 的完整枚举值
8. 返回体完整结构、错误码、失败原因字段
9. 官方限流、重试、幂等规则
10. callback 签名校验机制

---

## 15. 最小可用结论

如果你的目标是“让 Agent 能先写出大部分调用代码”，最小可信集合是：

- 用 `model = Kling-Video-O1`
- 用 `prompt` 作为主描述
- 图像输入先按 `first_frame_url` / `last_frame_url` / `reference_images`
- 复杂输入按 `element_list` / `video_list`
- 常用参数补 `mode`, `aspect_ratio`, `seconds`
- 按异步任务接口设计客户端
- 代码里把未确认字段标为 `TODO: verify with official docs`

