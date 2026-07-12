"""安全切换 .env.local 中的当前人物；音色由人物级变量自动解析。"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from dotenv import set_key


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="切换实时对话人物")
    parser.add_argument("persona")
    parser.add_argument("--env-file", type=Path, default=root / ".env.local")
    parser.add_argument("--speaker", default="", help="可选：为人物绑定豆包音色")
    parser.add_argument("--resource", default="", help="可选：音色对应 resource ID")
    parser.add_argument("--model", default="", help="可选：TTS 模型")
    parser.add_argument("--language", default="", help="可选：TTS 语言")
    parser.add_argument("--context", default="", help="可选：TTS 风格上下文")
    args = parser.parse_args()

    persona = args.persona.strip().lower()
    if persona != "fengge" and not (root / "personas" / persona / "persona.md").is_file():
        raise SystemExit(f"未知人物: {persona}")
    if not args.env_file.is_file():
        raise SystemExit(f"找不到环境文件: {args.env_file}")
    set_key(str(args.env_file), "PERSONA_NAME", persona)
    prefix = re.sub(r"[^A-Z0-9]+", "_", persona.upper()).strip("_")
    for suffix, value in {
        "SPEAKER": args.speaker,
        "RESOURCE_ID": args.resource,
        "MODEL": args.model,
        "LANGUAGE": args.language,
        "CONTEXT": args.context,
    }.items():
        if value:
            set_key(str(args.env_file), f"PERSONA_{prefix}_TTS_{suffix}", value)
    os.chmod(args.env_file, 0o600)
    print(f"已切换到 {persona}；重启服务后生效")


if __name__ == "__main__":
    main()
