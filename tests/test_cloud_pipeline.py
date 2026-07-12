from __future__ import annotations

import json

import pytest

from scripts.bootstrap_cloud_env import _parse_key_file
from scripts.select_persona import main as select_persona_main
from worker.llm_factory import DeepSeekChatStream
from worker.persona import build_system_prompt
from worker.stt_factory import ASR_2_RESOURCE_ID, build_stt
from worker.tts_factory import _persona_env_name, build_tts


def test_stt_factory_uses_asr_2_resource(monkeypatch):
    monkeypatch.delenv("DOUBAO_ASR_API_KEY", raising=False)
    monkeypatch.setenv("DOUBAO_ASR_APP_ID", "test-app")
    monkeypatch.setenv("DOUBAO_ASR_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("DOUBAO_ASR_RESOURCE_ID", raising=False)
    provider = build_stt()
    assert provider.model == ASR_2_RESOURCE_ID
    assert provider.capabilities.streaming is True
    assert provider.capabilities.interim_results is True


def test_tts_factory_uses_bidirectional_clone_resource(monkeypatch):
    monkeypatch.delenv("DOUBAO_TTS_API_KEY", raising=False)
    monkeypatch.setenv("DOUBAO_TTS_APP_ID", "test-app")
    monkeypatch.setenv("DOUBAO_TTS_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("DOUBAO_TTS_SPEAKER", "S_test_voice")
    monkeypatch.delenv("DOUBAO_TTS_RESOURCE_ID", raising=False)
    provider, label = build_tts()
    assert provider.model == "seed-icl-2.0"
    assert provider.capabilities.streaming is True
    assert "doubao-ws:seed-icl-2.0" in label


def test_tts_fails_fast_without_speaker(monkeypatch):
    monkeypatch.setenv("DOUBAO_TTS_APP_ID", "test-app")
    monkeypatch.setenv("DOUBAO_TTS_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("DOUBAO_TTS_SPEAKER", raising=False)
    with pytest.raises(RuntimeError, match="DOUBAO_TTS_SPEAKER"):
        build_tts()


def test_tts_uses_persona_scoped_voice(monkeypatch):
    monkeypatch.setenv("DOUBAO_TTS_APP_ID", "test-app")
    monkeypatch.setenv("DOUBAO_TTS_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("PERSONA_NAME", "steve_jobs")
    monkeypatch.setenv("DOUBAO_TTS_SPEAKER", "fallback")
    monkeypatch.setenv("PERSONA_STEVE_JOBS_TTS_SPEAKER", "S_jobs")
    monkeypatch.setenv("PERSONA_STEVE_JOBS_TTS_LANGUAGE", "en")
    provider, label = build_tts()
    assert provider._speaker == "S_jobs"
    assert "S_jobs" in label
    assert _persona_env_name("Steve Jobs", "SPEAKER") == "PERSONA_STEVE_JOBS_TTS_SPEAKER"


def test_official_tts_resource_is_not_repeated_as_model(monkeypatch):
    monkeypatch.setenv("DOUBAO_TTS_APP_ID", "test-app")
    monkeypatch.setenv("DOUBAO_TTS_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("DOUBAO_TTS_SPEAKER", "en_male_tim_uranus_bigtts")
    monkeypatch.setenv("DOUBAO_TTS_RESOURCE_ID", "seed-tts-2.0")
    monkeypatch.setenv("DOUBAO_TTS_MODEL", "seed-tts-2.0")
    provider, _ = build_tts()
    assert provider._model is None


@pytest.mark.asyncio
async def test_deepseek_v4_disables_thinking():
    captured = {}

    class Response:
        status_code = 200

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
            yield "data: [DONE]"

    class Context:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *_):
            return False

    class Client:
        is_closed = False

        def stream(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return Context()

    provider = DeepSeekChatStream("secret", model="deepseek-v4-flash")
    provider._client = Client()
    chunks = [piece async for piece in provider.chat([{"role": "user", "content": "hi"}])]
    assert chunks == ["hello"]
    assert captured["json"]["model"] == "deepseek-v4-flash"
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert "secret" not in json.dumps(captured["json"])


def test_steve_jobs_persona_is_disclosed_and_voice_optimized():
    prompt = build_system_prompt("steve_jobs")
    assert "AI recreation" in prompt
    assert "Never claim to be the real person" in prompt
    assert "Always speak in concise American English" in prompt
    assert "1–4 sentences" in prompt


def test_key_file_parser_separates_asr_and_tts_tokens(tmp_path):
    key_file = tmp_path / "key.txt"
    key_file.write_text(
        "DeepSeek API Endpoint：https://api.deepseek.com\n"
        "API Key：ds-secret\n"
        "model name：deepseek-v4-flash\n\n"
        "火山引擎 App ID：asr-app\n"
        "Access token：asr-token\n\n"
        "火山引擎语音合成 AppID：tts-app\n"
        "Access token：tts-token\n"
        "secret token：unused-secret\n",
        encoding="utf-8",
    )
    parsed = _parse_key_file(key_file)
    assert parsed["DOUBAO_ASR_ACCESS_TOKEN"] == "asr-token"
    assert parsed["DOUBAO_TTS_ACCESS_TOKEN"] == "tts-token"
    assert parsed["DEEPSEEK_MODEL"] == "deepseek-v4-flash"


def test_select_persona_updates_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("PERSONA_NAME=fengge\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["select_persona.py", "steve_jobs", "--env-file", str(env_file)]
    )
    select_persona_main()
    assert "PERSONA_NAME='steve_jobs'" in env_file.read_text(encoding="utf-8")
    assert env_file.stat().st_mode & 0o777 == 0o600
