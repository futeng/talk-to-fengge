"""前端 HTTP 服务 + 用 livekit API 包创建房间、分发 token、显式 dispatch agent。"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv  # 阶段 20 修复：web 进程独立拉起时也读到 AGENT_NAME
from livekit import api as lk_api
from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest
from livekit.protocol.room import CreateRoomRequest

from worker.runtime_env import (
    configure_local_no_proxy,
    local_service_env,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"

# 阶段 20 修复：web 是 nohup 后台拉，**不继承 shell env**，必须自己 load_dotenv
# 否则 AGENT_NAME 走默认值 "talk-to-me-agent"，跟 worker 的 "talk-to-me-dev3" 不匹配，
# dispatch 不会路由到这个 worker → 客户端进房没 agent。
for env_name in (".env.local", ".env"):
    env_file = PROJECT_ROOT / env_name
    if env_file.exists():
        load_dotenv(env_file)
        break

API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
AGENT_NAME = os.getenv("AGENT_NAME", "talk-to-persona-cloud")
assert AGENT_NAME, "AGENT_NAME is required"

configure_local_no_proxy()


def create_room_and_token(room_base: str, identity: str, name: str) -> dict:
    """创建房间并生成用户 token；等麦克风发布后再 dispatch Agent。"""
    host = LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")
    room_name = f"{room_base}-{secrets.token_hex(4)}"

    print(f"[web] 创建 room='{room_name}'", flush=True)

    async def ensure_room() -> None:
        with local_service_env():
            lk = lk_api.LiveKitAPI(host, API_KEY, API_SECRET)
            try:
                await lk.room.create_room(CreateRoomRequest(name=room_name))
                print(f"[web] ✅ 房间 '{room_name}' 已创建")
            except Exception as e:
                err_str = str(e)
                if "already" not in err_str.lower() and "409" not in err_str:
                    print(f"[web] 创建房间异常（非致命）: {e}")
                else:
                    print(f"[web] 房间 '{room_name}' 已存在，复用")

            finally:
                await lk.aclose()

    asyncio.run(ensure_room())

    user_token = (
        lk_api.AccessToken(API_KEY, API_SECRET)
        .with_identity(identity)
        .with_name(name)
        .with_grants(lk_api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

    return {
        "token": user_token,
        "room": room_name,
        "identity": identity,
        "livekit_url": LIVEKIT_URL,
    }


def dispatch_agent(room_name: str) -> None:
    """用户已进房并发布麦克风后，再启动 Agent，避免 ASR 空闲超时。"""
    if not room_name.startswith("ttm-") or len(room_name) > 128:
        raise ValueError("invalid room name")
    host = LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")

    async def dispatch() -> None:
        with local_service_env():
            lk = lk_api.LiveKitAPI(host, API_KEY, API_SECRET)
            try:
                await lk.agent_dispatch.create_dispatch(
                    CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room_name)
                )
                print(f"[web] ✅ 已 dispatch agent: {AGENT_NAME} -> {room_name}")
            finally:
                await lk.aclose()

    asyncio.run(dispatch())


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_POST(self):
        if self.path == "/token":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid json"})
                return

            room = data.get("room", "talk-to-me-room")
            identity = data.get("identity", f"user-{secrets.token_hex(4)}")
            name = data.get("name", identity)

            result = create_room_and_token(room, identity, name)
            self._send_json(200, result)
        elif self.path == "/dispatch":
            content_length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(content_length))
                dispatch_agent(str(data.get("room", "")))
            except (json.JSONDecodeError, ValueError) as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, {"ok": True})
        else:
            self._send_json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self._cors_headers()
        self.send_response(204)
        self.end_headers()

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        print(f"[web] {args[0]}")


def main():
    port = int(os.getenv("WEB_PORT", "8766"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[web] http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[web] 已停止")
        server.server_close()


if __name__ == "__main__":
    main()
