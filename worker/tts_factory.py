"""豆包 V3 双向 WebSocket TTS 工厂。

这里故意不做本地或跨供应商降级：全云端部署一旦配置错误应立即失败，
否则线上日志显示“豆包”而实际悄悄落到本地 TTS，会让延迟和音色不可控。
"""

from __future__ import annotations

import os
import re


def _persona_env_name(persona_name: str, suffix: str) -> str:
    prefix = re.sub(r"[^A-Z0-9]+", "_", persona_name.upper()).strip("_")
    return f"PERSONA_{prefix}_TTS_{suffix}"


def _persona_setting(suffix: str, default: str = "") -> str:
    persona_name = os.getenv("PERSONA_NAME", "fengge").strip() or "fengge"
    scoped = os.getenv(_persona_env_name(persona_name, suffix), "").strip()
    return scoped or os.getenv(f"DOUBAO_TTS_{suffix}", default).strip()


def build_tts():
    """构造豆包 V3 双向流式 TTS。

    支持旧控制台的 App ID + Access Token，也支持新版控制台 API Key。
    克隆音色使用 ``seed-icl-2.0``；官方音色可切到 ``seed-tts-2.0``。
    """
    from livekit.plugins import bytedance

    api_key = os.getenv("DOUBAO_TTS_API_KEY", "").strip() or None
    app_id = os.getenv("DOUBAO_TTS_APP_ID", "").strip() or None
    access_token = os.getenv("DOUBAO_TTS_ACCESS_TOKEN", "").strip() or None
    if not api_key and not (app_id and access_token):
        raise RuntimeError(
            "豆包 TTS 凭据缺失：设置 DOUBAO_TTS_API_KEY，或同时设置 "
            "DOUBAO_TTS_APP_ID 与 DOUBAO_TTS_ACCESS_TOKEN"
        )

    speaker = _persona_setting("SPEAKER")
    if not speaker:
        raise RuntimeError(
            "DOUBAO_TTS_SPEAKER 未设置；声音复刻后填入 speaker_id，"
            "或先使用一个已开通的豆包官方音色"
        )

    resource_id = _persona_setting("RESOURCE_ID", "seed-icl-2.0")
    model = _persona_setting("MODEL") or None
    # V3 官方音色由 resource_id 选模型；把同名 resource 再传进 model 会触发
    # InvalidModel。克隆音色的 expressive 模型名仍按配置透传。
    if resource_id.startswith("seed-tts-") and model == resource_id:
        model = None
    sample_rate = int(os.getenv("DOUBAO_TTS_SAMPLE_RATE", "24000"))
    speech_rate = int(os.getenv("DOUBAO_TTS_SPEECH_RATE", "0"))
    loudness_rate = int(os.getenv("DOUBAO_TTS_LOUDNESS_RATE", "0"))
    context = _persona_setting("CONTEXT")

    tts = bytedance.TTS(
        api_key=api_key,
        app_key=app_id,
        access_key=access_token,
        resource_id=resource_id,
        model=model,
        speaker=speaker,
        audio_format="pcm",
        sample_rate=sample_rate,
        speech_rate=speech_rate,
        loudness_rate=loudness_rate,
        context_texts=[context] if context else None,
        explicit_language=_persona_setting("LANGUAGE") or None,
    )
    return tts, f"doubao-ws:{resource_id}/{speaker[:12]}"


__all__ = ["build_tts", "_persona_env_name"]
