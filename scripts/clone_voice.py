"""调用豆包声音复刻 2.0 API 注册一段已获授权的声音样本。"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key

VOICE_CLONE_URL = "https://openspeech.bytedance.com/api/v3/tts/voice_clone"
LANGUAGES = {"zh": 0, "en": 1, "ja": 2, "es": 3, "de": 6, "fr": 7, "ko": 8}


def _persona_env_name(persona_name: str, suffix: str) -> str:
    prefix = re.sub(r"[^A-Z0-9]+", "_", persona_name.upper()).strip("_")
    return f"PERSONA_{prefix}_TTS_{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(description="注册豆包声音复刻 2.0 音色")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--language", choices=sorted(LANGUAGES), default="zh")
    parser.add_argument("--speaker-id", default="", help="重训已有音色时填写")
    parser.add_argument("--demo-text", default="")
    parser.add_argument("--persona", default="", help="绑定到该人物（如 fengge、steve_jobs）")
    parser.add_argument("--output", type=Path, help="将安全结果写入本地 JSON（权限 600）")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".env.local",
        help="人物音色绑定写入的环境文件",
    )
    parser.add_argument(
        "--i-have-rights",
        action="store_true",
        help="确认已获得声音样本和声音复刻所需授权",
    )
    args = parser.parse_args()
    if not args.i_have_rights:
        parser.error("必须传 --i-have-rights，确认你有权使用并复刻该声音")
    if not args.audio.is_file():
        parser.error(f"找不到音频: {args.audio}")

    load_dotenv(args.env_file)
    api_key = os.getenv("DOUBAO_TTS_API_KEY", "").strip()
    app_id = os.getenv("DOUBAO_TTS_APP_ID", "").strip()
    token = os.getenv("DOUBAO_TTS_ACCESS_TOKEN", "").strip()
    headers = {
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Resource-Id": "seed-icl-2.0",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["X-Api-Key"] = api_key
    elif app_id and token:
        headers.update({"X-Api-App-Key": app_id, "X-Api-Access-Key": token})
    else:
        parser.error(".env.local 缺少豆包 TTS 凭据")
    if not api_key and not args.speaker_id:
        parser.error(
            "旧控制台 App ID + Access Token 模式必须用 --speaker-id 指定已开通的音色槽位；"
            "只有新版 API Key 的后付费流程可由服务端创建 speaker_id"
        )

    suffix = args.audio.suffix.lower().lstrip(".")
    if suffix not in {"wav", "mp3", "ogg", "m4a", "aac", "flac"}:
        parser.error(f"不支持的音频格式: {suffix}")
    extra = {"voice_clone_denoise_model_id": ""}
    if args.demo_text:
        extra["demo_text"] = args.demo_text
    body = {
        "audio": {
            "data": base64.b64encode(args.audio.read_bytes()).decode("ascii"),
            "format": suffix,
        },
        "language": LANGUAGES[args.language],
        "extra_params": extra,
    }
    if args.speaker_id:
        body["speaker_id"] = args.speaker_id
    response = httpx.post(VOICE_CLONE_URL, headers=headers, json=body, timeout=60)
    log_id = response.headers.get("X-Tt-Logid", "")
    if response.is_error:
        hint = ""
        if "resource ID is mismatched with speaker related resource" in response.text:
            hint = "；请在同一项目的开通管理中确认声音复刻2.0和音色槽位均已开通"
        raise SystemExit(
            f"声音复刻失败 HTTP {response.status_code}; X-Tt-Logid={log_id}; "
            f"{response.text[:500]}{hint}"
        )
    result = response.json()
    safe = {
        "speaker_id": result.get("speaker_id"),
        "status": result.get("status"),
        "available_training_times": result.get("available_training_times"),
        "demo_audio": [item.get("demo_audio") for item in result.get("speaker_status", []) if item.get("demo_audio")],
        "log_id": log_id,
    }
    speaker_id = str(safe.get("speaker_id") or "").strip()
    if not speaker_id:
        raise SystemExit(f"声音复刻返回中没有 speaker_id；X-Tt-Logid={log_id}")
    if args.persona:
        args.env_file.touch(mode=0o600, exist_ok=True)
        bindings = {
            "SPEAKER": speaker_id,
            "RESOURCE_ID": "seed-icl-2.0",
            "MODEL": "seed-tts-2.0-expressive",
            "LANGUAGE": "en" if args.language == "en" else args.language,
        }
        for suffix, value in bindings.items():
            set_key(str(args.env_file), _persona_env_name(args.persona, suffix), value)
        os.chmod(args.env_file, 0o600)
        safe["persona"] = args.persona
        safe["env_keys"] = [
            _persona_env_name(args.persona, suffix) for suffix in bindings
        ]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(args.output, 0o600)
    print(json.dumps(safe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
