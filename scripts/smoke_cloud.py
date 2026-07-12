"""真实调用三段云 API，输出不含凭据的延迟与结果计数。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import wave
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import stt as livekit_stt
from livekit.agents.types import APIConnectOptions
from livekit.agents.utils import http_context

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from worker.llm_factory import DeepSeekChatStream
from worker.stt_factory import build_stt
from worker.tts_factory import build_tts


async def check_llm() -> dict:
    provider = DeepSeekChatStream(
        os.environ["DEEPSEEK_API_KEY"],
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        max_tokens=30,
    )
    started = time.monotonic()
    first: float | None = None
    chars = 0
    try:
        async for piece in provider.chat(
            [{"role": "user", "content": "Confirm this voice-agent smoke test in one short sentence."}],
            temperature=0.2,
        ):
            first = first or time.monotonic()
            chars += len(piece)
    finally:
        await provider.aclose()
    if not first or chars == 0:
        raise RuntimeError("DeepSeek returned no text")
    return {"ttfb_ms": round((first - started) * 1000), "chars": chars}


async def check_tts() -> dict:
    provider, label = build_tts()
    started = time.monotonic()
    first: float | None = None
    chunks = 0
    audio_s = 0.0
    try:
        async with provider.stream(
            conn_options=APIConnectOptions(max_retry=1, timeout=30)
        ) as stream:
            stream.push_text("The bidirectional cloud voice path is ready.")
            stream.end_input()
            async for event in stream:
                first = first or time.monotonic()
                chunks += 1
                audio_s += event.frame.duration
    finally:
        await provider.aclose()
    if not first or chunks == 0:
        raise RuntimeError("Doubao TTS returned no audio")
    return {
        "label": label,
        "first_audio_ms": round((first - started) * 1000),
        "chunks": chunks,
        "audio_s": round(audio_s, 2),
    }


async def check_asr(audio_path: Path, seconds: float) -> dict:
    provider = build_stt()
    stream = provider.stream()
    interims = 0
    finals: list[str] = []
    started = time.monotonic()

    async def send() -> None:
        with wave.open(str(audio_path), "rb") as source:
            if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (16000, 1, 2):
                raise ValueError("ASR 冒烟音频必须是 16kHz、mono、16-bit WAV")
            for _ in range(max(1, round(seconds / 0.2))):
                data = source.readframes(3200)
                if not data:
                    break
                stream.push_frame(
                    rtc.AudioFrame(
                        data=data,
                        sample_rate=16000,
                        num_channels=1,
                        samples_per_channel=len(data) // 2,
                    )
                )
                await asyncio.sleep(0.2)
        stream.end_input()

    async def receive() -> None:
        nonlocal interims
        async for event in stream:
            if event.type == livekit_stt.SpeechEventType.INTERIM_TRANSCRIPT:
                interims += 1
            elif event.type == livekit_stt.SpeechEventType.FINAL_TRANSCRIPT:
                text = event.alternatives[0].text.strip() if event.alternatives else ""
                if text:
                    finals.append(text)

    try:
        async with stream:
            await asyncio.gather(send(), receive())
    finally:
        await provider.aclose()
    if not finals:
        raise RuntimeError("Doubao ASR returned no final transcript")
    return {
        "elapsed_s": round(time.monotonic() - started, 2),
        "interims": interims,
        "finals": len(finals),
        "final_chars": sum(map(len, finals)),
    }


async def run(args) -> None:
    async with http_context.open():
        results = {
            "deepseek_v4_flash": await check_llm(),
            "doubao_tts_websocket": await check_tts(),
            "doubao_asr_2": await check_asr(args.audio, args.asr_seconds),
        }
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audio",
        type=Path,
        default=Path("assets/voice_samples/fengge_ref.wav"),
    )
    parser.add_argument("--asr-seconds", type=float, default=6.0)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
