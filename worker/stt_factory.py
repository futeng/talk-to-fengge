"""豆包流式语音识别 2.0 工厂。"""

from __future__ import annotations

import os


ASR_2_RESOURCE_ID = "volc.seedasr.sauc.duration"


def build_stt():
    """构造优化版双向流式 ASR 2.0。

    200ms 分包由插件完成；服务端 VAD + 二遍识别兼顾实时中间结果和最终准确率。
    """
    from livekit.plugins import bytedance

    api_key = os.getenv("DOUBAO_ASR_API_KEY", "").strip() or None
    app_id = os.getenv("DOUBAO_ASR_APP_ID", "").strip() or None
    access_token = os.getenv("DOUBAO_ASR_ACCESS_TOKEN", "").strip() or None
    if not api_key and not (app_id and access_token):
        raise RuntimeError(
            "豆包 ASR 凭据缺失：设置 DOUBAO_ASR_API_KEY，或同时设置 "
            "DOUBAO_ASR_APP_ID 与 DOUBAO_ASR_ACCESS_TOKEN"
        )

    return bytedance.STT(
        api_key=api_key,
        app_key=app_id,
        access_key=access_token,
        resource_id=os.getenv("DOUBAO_ASR_RESOURCE_ID", ASR_2_RESOURCE_ID).strip(),
        sample_rate=16000,
        enable_interim_results=True,
        enable_nonstream=True,
        enable_itn=True,
        enable_punc=True,
        show_utterances=True,
        enable_accelerate_text=True,
        end_window_size=int(os.getenv("DOUBAO_ASR_END_WINDOW_MS", "500")),
    )


__all__ = ["ASR_2_RESOURCE_ID", "build_stt"]
