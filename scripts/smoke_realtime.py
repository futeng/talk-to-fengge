"""通过真实 LiveKit 房间发布音频，并验证 Agent 返回非静音音频。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave

import httpx
import numpy as np
from livekit import rtc


async def run(audio_path: str, web_url: str, timeout: float) -> None:
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        response = await client.post(
            f"{web_url}/token",
            json={"room": "ttm-realtime-smoke", "identity": "e2e-client", "name": "E2E"},
        )
        response.raise_for_status()
        auth = response.json()

    room = rtc.Room()
    voiced = asyncio.Event()
    stats = {"active_frames": 0, "first_voice": None, "peak": 0}
    consume_tasks: list[asyncio.Task] = []

    @room.on("track_subscribed")
    def on_track(track, publication, participant) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        async def consume() -> None:
            stream = rtc.AudioStream(track)
            try:
                async for event in stream:
                    samples = np.asarray(event.frame.data, dtype=np.int16)
                    peak = int(np.max(np.abs(samples))) if samples.size else 0
                    stats["peak"] = max(stats["peak"], peak)
                    if peak > 100:
                        stats["active_frames"] += 1
                        if stats["first_voice"] is None:
                            stats["first_voice"] = time.monotonic()
                            voiced.set()
                    if stats["active_frames"] >= 10:
                        break
            finally:
                await stream.aclose()

        consume_tasks.append(asyncio.create_task(consume()))

    await room.connect(auth["livekit_url"], auth["token"])
    source = rtc.AudioSource(16000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    await room.local_participant.publish_track(track, options)

    # 先连接并发布麦克风，再 dispatch，避免豆包 ASR 空闲 8 秒超时。
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        response = await client.post(f"{web_url}/dispatch", json={"room": auth["room"]})
        response.raise_for_status()

    await asyncio.sleep(1)
    with wave.open(audio_path, "rb") as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError("输入必须是 16kHz、mono、16-bit WAV")
        while data := audio.readframes(320):
            await source.capture_frame(
                rtc.AudioFrame(
                    data=data,
                    sample_rate=16000,
                    num_channels=1,
                    samples_per_channel=len(data) // 2,
                )
            )
            await asyncio.sleep(0.02)

    endpoint = time.monotonic()
    silence = bytes(640)
    for _ in range(50):
        await source.capture_frame(
            rtc.AudioFrame(
                data=silence,
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=320,
            )
        )
        await asyncio.sleep(0.02)

    try:
        await asyncio.wait_for(voiced.wait(), timeout=timeout)
        await asyncio.sleep(0.5)
        print(
            json.dumps(
                {
                    "endpoint_to_voiced_audio_ms": round(
                        (stats["first_voice"] - endpoint) * 1000
                    ),
                    "active_audio_frames": stats["active_frames"],
                    "peak_pcm": stats["peak"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await room.disconnect()
        for task in consume_tasks:
            if not task.done():
                task.cancel()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="与当前人物语言一致的 16kHz mono 16-bit WAV")
    parser.add_argument("--web-url", default="http://127.0.0.1:8766")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    asyncio.run(run(args.audio, args.web_url.rstrip("/"), args.timeout))


if __name__ == "__main__":
    main()
