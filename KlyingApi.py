"""
Kling API 鉴权 Token 生成工具。

作用：
- 使用 Access Key / Secret Key 生成 JWT token。
- 支持作为模块导入，也支持命令行单独运行。

推荐做法：
- 不要在代码里硬编码 AK/SK，优先使用环境变量：
  - KLING_ACCESS_KEY
  - KLING_SECRET_KEY
"""

import argparse
import os
import time

import jwt


def _load_env_file(file_path: str = ".env") -> None:
    """加载本地 .env 到环境变量（仅填充未设置变量）。"""
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
            if len(value) >= 2 and (
                (value[0] == '"' and value[-1] == '"')
                or (value[0] == "'" and value[-1] == "'")
            ):
                value = value[1:-1]
            os.environ.setdefault(key, value)


def encode_jwt_token(access_key: str, secret_key: str, expire_seconds: int = 1800) -> str:
    """
    生成可灵 API 使用的 JWT token。

    参数：
    - access_key: 发放给你的 AK（写入 payload.iss）
    - secret_key: 对应 SK（用于 HMAC 签名）
    - expire_seconds: token 有效期（默认 1800 秒）

    返回：
    - JWT 字符串，可用于 Authorization: Bearer <token>
    """
    now = int(time.time())
    headers = {
        "alg": "HS256",
        "typ": "JWT",
    }
    payload = {
        "iss": access_key,
        # 过期时间：当前时间 + expire_seconds
        "exp": now + expire_seconds,
        # 生效时间：给 5 秒回拨余量，减少时钟偏差导致的 nbf 校验失败
        "nbf": now - 5,
    }
    return jwt.encode(payload, secret_key, headers=headers)


def main() -> None:
    """
    命令行入口：打印 JWT token。
    """
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=".env")
    pre_args, _ = pre_parser.parse_known_args()
    _load_env_file(pre_args.env_file)

    parser = argparse.ArgumentParser(description="Generate Kling API JWT token.")
    parser.add_argument("--env-file", default=".env", help="Path to local .env file.")
    parser.add_argument("--access-key", default=os.getenv("KLING_ACCESS_KEY"))
    parser.add_argument("--secret-key", default=os.getenv("KLING_SECRET_KEY"))
    parser.add_argument("--expire-seconds", type=int, default=1800)
    args = parser.parse_args()

    if not args.access_key or not args.secret_key:
        raise ValueError(
            "Missing AK/SK. Pass --access-key/--secret-key or set "
            "KLING_ACCESS_KEY and KLING_SECRET_KEY."
        )

    token = encode_jwt_token(
        access_key=args.access_key,
        secret_key=args.secret_key,
        expire_seconds=args.expire_seconds,
    )
    print(token)


if __name__ == "__main__":
    main()
