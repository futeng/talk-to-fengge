"""把用户私有 key.txt 安全转换为 gitignored 的 .env.local。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _parse_key_file(path: Path) -> dict[str, str]:
    sections: dict[str, str] = {}
    access_tokens: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or "：" not in line:
            continue
        label, value = (part.strip() for part in line.split("：", 1))
        if label.lower() == "access token":
            access_tokens.append(value)
        else:
            sections[label.lower()] = value

    if not access_tokens:
        raise ValueError("key.txt 中缺少 ASR Access token")
    return {
        "DEEPSEEK_BASE_URL": sections.get("deepseek api endpoint", "https://api.deepseek.com"),
        "DEEPSEEK_API_KEY": sections.get("api key", ""),
        "DEEPSEEK_MODEL": sections.get("model name", "deepseek-v4-flash"),
        "DOUBAO_ASR_APP_ID": sections.get("火山引擎 app id", ""),
        "DOUBAO_ASR_ACCESS_TOKEN": access_tokens[0],
        "DOUBAO_TTS_APP_ID": sections.get("火山引擎语音合成 appid", ""),
        "DOUBAO_TTS_ACCESS_TOKEN": access_tokens[1] if len(access_tokens) > 1 else "",
        "DOUBAO_TTS_API_KEY": sections.get("火山引擎 api key", ""),
    }


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".env.local"))
    parser.add_argument("--persona", default="fengge")
    parser.add_argument("--speaker", default="")
    parser.add_argument("--tts-resource", default="seed-icl-2.0")
    parser.add_argument("--tts-model", default="")
    parser.add_argument("--tts-language", default="zh-cn")
    args = parser.parse_args()

    values = _parse_key_file(args.key_file.expanduser())
    values.update(
        {
            "LIVEKIT_URL": "ws://127.0.0.1:7880",
            "LIVEKIT_API_KEY": "devkey",
            "LIVEKIT_API_SECRET": "local-dev-secret-change-me-32-bytes",
            "AGENT_NAME": "talk-to-persona-cloud",
            "PERSONA_NAME": args.persona,
            "DEEPSEEK_MAX_TOKENS": "100",
            "DOUBAO_ASR_RESOURCE_ID": "volc.seedasr.sauc.duration",
            "DOUBAO_TTS_RESOURCE_ID": args.tts_resource,
            "DOUBAO_TTS_MODEL": args.tts_model,
            "DOUBAO_TTS_SPEAKER": args.speaker,
            "DOUBAO_TTS_LANGUAGE": args.tts_language,
        }
    )
    required = {
        "DEEPSEEK_API_KEY",
        "DOUBAO_ASR_APP_ID",
        "DOUBAO_ASR_ACCESS_TOKEN",
    }
    missing = [key for key in required if not values.get(key)]
    if not values.get("DOUBAO_TTS_API_KEY") and not (
        values.get("DOUBAO_TTS_APP_ID") and values.get("DOUBAO_TTS_ACCESS_TOKEN")
    ):
        missing.append("DOUBAO_TTS_API_KEY 或 TTS APP_ID+ACCESS_TOKEN")
    if missing:
        raise ValueError(f"key.txt 缺少必要配置项: {', '.join(missing)}")

    output = args.output.expanduser()
    output.write_text("\n".join(f"{key}={_quote(value)}" for key, value in values.items()) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    print(f"已生成 {output}（权限 0600，未输出任何密钥）")


if __name__ == "__main__":
    main()
