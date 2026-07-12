"""全云端实时人物对话 Agent：豆包 ASR 2.0 → DeepSeek V4 Flash → 豆包 TTS。"""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobExecutorType,
    cli,
    llm,
    utils,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN

from worker.energy_vad import EnergyVAD
from worker.llm_factory import DeepSeekChatStream
from worker.persona import build_system_prompt
from worker.runtime_env import configure_local_no_proxy, local_service_env
from worker.stt_factory import build_stt
from worker.tts_factory import build_tts


PROJECT_ROOT = Path(__file__).resolve().parent.parent
for env_name in (".env.local", ".env"):
    env_file = PROJECT_ROOT / env_name
    if env_file.exists():
        load_dotenv(env_file)
        break

configure_local_no_proxy()

AGENT_NAME = os.getenv("AGENT_NAME", "talk-to-persona-cloud").strip()
os.environ["AGENT_NAME"] = AGENT_NAME


class OpenAICompatLLM(llm.LLM):
    """把项目的轻量 DeepSeek SSE 客户端接到 LiveKit LLM 协议。"""

    def __init__(self, chat_stream: DeepSeekChatStream) -> None:
        super().__init__()
        self._chat_stream = chat_stream

    @property
    def model(self) -> str:
        return self._chat_stream.model

    @property
    def provider(self) -> str:
        return "deepseek"

    def chat(
        self,
        *,
        chat_ctx,
        tools=None,
        conn_options=None,
        parallel_tool_calls=NOT_GIVEN,
        tool_choice=NOT_GIVEN,
        extra_kwargs=NOT_GIVEN,
    ):
        messages: list[dict[str, str]] = []
        chat_messages = chat_ctx.messages() if hasattr(chat_ctx, "messages") else []
        if callable(chat_messages):
            chat_messages = chat_messages()
        for item in chat_messages:
            role = str(getattr(item, "role", "user"))
            if "." in role:
                role = role.rsplit(".", 1)[-1]
            content = getattr(item, "text_content", None) or getattr(item, "content", "")
            if callable(content):
                content = content()
            if isinstance(content, list):
                content = "\n".join(part for part in content if isinstance(part, str))
            if content:
                messages.append({"role": role, "content": str(content)})
        return DeepSeekLLMStream(
            self,
            messages=messages,
            chat_ctx=chat_ctx,
            conn_options=conn_options or DEFAULT_API_CONNECT_OPTIONS,
        )

    async def aclose(self) -> None:
        await self._chat_stream.aclose()


class DeepSeekLLMStream(llm.LLMStream):
    """将 DeepSeek token 增量推入 LiveKit，并保留短语音上下文。"""

    def __init__(self, provider, *, messages, chat_ctx, conn_options) -> None:
        super().__init__(
            llm=provider,
            chat_ctx=chat_ctx,
            tools=[],
            conn_options=conn_options,
        )
        self._messages = messages

    async def _run(self) -> None:
        request_id = utils.shortuuid()
        system = [m for m in self._messages if m["role"] == "system"]
        turns = [m for m in self._messages if m["role"] != "system"][-16:]
        messages = system + turns
        started = time.monotonic()
        first = True
        try:
            async for piece in self._llm._chat_stream.chat(
                messages,
                temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.65")),
            ):
                if not piece:
                    continue
                if first:
                    print(
                        f"[timing] deepseek_ttfb={(time.monotonic() - started) * 1000:.0f}ms",
                        flush=True,
                    )
                    first = False
                self._event_ch.send_nowait(
                    llm.ChatChunk(
                        id=request_id,
                        delta=llm.ChoiceDelta(role="assistant", content=piece),
                    )
                )
        except Exception as exc:
            raise llm.APIConnectionError(f"DeepSeek stream failed: {exc}") from exc


def build_llm() -> OpenAICompatLLM:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")
    return OpenAICompatLLM(
        DeepSeekChatStream(
            api_key=api_key,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "100")),
        )
    )


class CloudPersonaAgent(Agent):
    def __init__(self, instructions: str) -> None:
        stt = build_stt()
        llm_provider = build_llm()
        tts, tts_label = build_tts()
        tts.prewarm()
        vad = EnergyVAD(
            speech_threshold=int(os.getenv("VAD_SPEECH_THRESHOLD", "500")),
            silence_threshold=int(os.getenv("VAD_SILENCE_THRESHOLD", "200")),
            min_speech_duration=float(os.getenv("VAD_MIN_SPEECH_S", "0.20")),
            min_silence_duration=float(os.getenv("VAD_MIN_SILENCE_S", "0.35")),
        )
        print(
            f"[agent] cloud pipeline: ASR={stt.model} "
            f"LLM={llm_provider.model} TTS={tts_label}",
            flush=True,
        )
        super().__init__(instructions=instructions, stt=stt, llm=llm_provider, tts=tts, vad=vad)


server = AgentServer(
    job_executor_type=JobExecutorType.THREAD,
    initialize_process_timeout=60.0,
    port=int(os.getenv("LIVEKIT_WORKER_PORT", "8081")),
)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    with local_service_env():
        await ctx.connect()

    persona_name = os.getenv("PERSONA_NAME", "fengge").strip().lower()
    instructions = build_system_prompt(persona_name)
    runtime_prompt = os.getenv("AGENT_INSTRUCTIONS", "").strip()
    if runtime_prompt:
        instructions += f"\n\n## 本次会话补充要求\n{runtime_prompt}"

    session = AgentSession(
        turn_handling={
            "interruption": {"enabled": True},
            "preemptive_generation": {"enabled": False},
        }
    )
    timings: dict[str, float] = {}

    @session.on("agent_state_changed")
    def on_state(ev) -> None:
        now = time.monotonic()
        old, new = str(ev.old_state), str(ev.new_state)
        if "listening" in old and "thinking" in new:
            timings["thinking"] = now
        elif "thinking" in old and "speaking" in new and "thinking" in timings:
            print(f"[timing] think_to_audio={(now - timings['thinking']) * 1000:.0f}ms", flush=True)

    @session.on("user_input_transcribed")
    def on_transcript(ev) -> None:
        if ev.is_final:
            print(f"[transcript] {ev.transcript}", flush=True)

    @session.on("error")
    def on_error(ev) -> None:
        print(f"[agent] error source={ev.source}: {ev.error}", flush=True)

    await session.start(agent=CloudPersonaAgent(instructions), room=ctx.room)


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
