# Talk to Persona：全云端实时人物对话

[English](README_EN.md)

把任意一组已获授权的人物资料，做成可打断、低延迟、具有稳定人格与声音的实时语音对话。当前运行链路固定为：

```text
浏览器麦克风
  → LiveKit WebRTC
  → 豆包流式语音识别模型 2.0（WebSocket）
  → DeepSeek V4 Flash（流式、非思考模式）
  → 豆包 V3 双向 WebSocket TTS（官方音色或声音复刻 2.0）
  → LiveKit 实时播放
```

没有本地 GPU、VoxCPM、MOSS，也没有跨供应商静默降级。配置错误会直接失败，便于稳定控制音色、延迟和成本。

## 已实现

- 豆包 ASR 2.0 优化双向流：`volc.seedasr.sauc.duration`，中间结果 + 服务端 VAD 二遍定稿。
- DeepSeek `deepseek-v4-flash`：SSE token 流，显式 `thinking.type=disabled`，口语回复默认最多 100 token。
- 豆包 TTS V3 双向 WebSocket：LLM 文本增量输入、PCM 音频流式输出、支持 `seed-icl-2.0` 克隆音色。
- 打断与低延迟端点检测：用户开口即可停止当前播放，VAD 参数可调。
- 文件化人物包：`personas/<name>/persona.md`，无需改 Python 即可新增人物。
- Steve Jobs 教育性 AI 重建示例：`personas/steve_jobs/`，明确标注为合成内容，不冒充本人或真实录音。
- 安全密钥导入与声音复刻 CLI；密钥只进入 gitignored 的 `.env.local`。

## 快速开始

要求：Python 3.11+、[uv](https://docs.astral.sh/uv/)、[LiveKit Server](https://docs.livekit.io/home/self-hosting/local/)。

```bash
uv sync

# 从本机 key.txt 生成权限为 0600 的 .env.local，不回显密钥
uv run python scripts/bootstrap_cloud_env.py \
  --key-file ~/Documents/key.txt \
  --persona steve_jobs \
  --speaker en_male_tim_uranus_bigtts \
  --tts-resource seed-tts-2.0 \
  --tts-language en

./Talk-to-Me-V3.6.command
```

打开 [http://127.0.0.1:8766](http://127.0.0.1:8766)。默认 App ID 示例是 `7446114798`；真实 Token 和 DeepSeek Key 不得提交到仓库。

若使用声音复刻音色，把 `.env.local` 改为：

```bash
DOUBAO_TTS_RESOURCE_ID=seed-icl-2.0
DOUBAO_TTS_MODEL=seed-tts-2.0-expressive
DOUBAO_TTS_SPEAKER=<训练返回的 speaker_id>
```

## 注册已授权声音

仅在你拥有声音样本和声音复刻所需授权时执行：

```bash
uv run python scripts/clone_voice.py /path/to/clean-sample.wav \
  --language en \
  --persona your_person \
  --output personas/your_person/your_person.speaker.json \
  --demo-text "Your sample transcript" \
  --i-have-rights
```

旧控制台 App ID + Access Token 模式还必须传入控制台已开通的 `--speaker-id S_xxx`；新版 API Key 后付费模式可省略。命令只输出 `speaker_id`、训练状态、试听地址和排错 `log_id`，并把人物级配置安全写入权限为 0600 的 `.env.local`，不会输出凭据。首次正式合成克隆音色可能触发豆包音色槽位计费，请先试听并确认效果。

## 切换人物

```text
personas/
└── your_person/
    ├── persona.md          # 身份、事实边界、思维模型、口语风格、few-shot
    └── persona.env.example # 推荐音色与 TTS 风格参数
```

运行 `uv run python scripts/select_persona.py your_person`，或设置 `PERSONA_NAME=your_person`。可在同一个 `.env.local` 中用 `PERSONA_<ID>_TTS_*` 分别绑定音色；没有对应文件时系统会明确报错，不会误用峰哥人格。

完整资料准备、蒸馏、声音训练、验收与上线流程见 [人物实时对话复刻 SOP](docs/PERSONA_CLONING_SOP.md)。

## 实测基线

在本项目开发机与给定账号上完成真实云 API 冒烟测试：

| 环节 | 结果 |
|---|---|
| 豆包 ASR 2.0 | 6 秒真实音频返回 17 次中间结果、1 次最终结果 |
| DeepSeek V4 Flash | 首 token 约 0.47–0.9 秒 |
| 豆包双向 WebSocket TTS | 首音频约 0.46–0.61 秒，持续分块输出 |
| 完整 LiveKit → ASR → LLM → TTS → LiveKit | 测试问题结束后约 2.68 秒收到非静音回复 |
| 峰哥人物（中文官方近似音色） | 2026-07-12 实测约 2.53 秒收到非静音回复 |
| Steve Jobs 人格（英文官方近似音色） | 2026-07-12 实测约 2.26 秒收到非静音回复；LLM 首 token 674 ms |

后两项验证的是全云实时功能与人物 prompt；官方近似音色不是本人声音，不能作为声音相似度验收。以上均为单次开发环境观测，不是 SLA。端到端体感还受说话判停、网络、地域、音色模型和句长影响；生产环境应持续记录 p50/p95。

## 测试

```bash
uv run pytest -q tests/test_cloud_pipeline.py tests/test_energy_vad.py tests/test_runtime_env.py

# 真实调用三段云 API，输出不含凭据的延迟指标
uv run python scripts/smoke_cloud.py

# 服务栈启动后，通过真实 LiveKit 房间发布音频并验证非静音回复
uv run python scripts/smoke_realtime.py /path/to/16k-mono.wav
```

## 官方协议参考

- [豆包流式语音识别 WebSocket](https://www.volcengine.com/docs/6561/1354869)
- [豆包双向流式语音合成 WebSocket](https://www.volcengine.com/docs/6561/1329505)
- [豆包声音复刻训练 HTTP](https://www.volcengine.com/docs/6561/2534906)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion)
- [DeepSeek V4 模型与价格](https://api-docs.deepseek.com/quick_start/pricing)

## 合规边界

只复刻你有权使用的声音和资料；始终向听众披露这是 AI 合成；不得用于冒充、诈骗、虚假背书或伪造历史录音。对在世或已故公众人物，优先使用明确标注的教育、评论或致敬场景，并保留来源与授权记录。

Apache-2.0，详见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
