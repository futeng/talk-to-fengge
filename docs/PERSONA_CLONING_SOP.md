# 任意人物实时对话复刻 SOP

这份 SOP 的目标不是“让模型背一份传记”，而是稳定复刻四层体验：事实边界、判断方式、口语表达和声音韵律。四层应分别准备、评估和迭代。

## 0. 先确定用途与权利

在采集资料前写清楚用途、受众、保存周期和发布渠道。确认你有权使用文本、音频、姓名与形象，并取得声音复刻所需授权。所有界面、录音和导出内容都应标明“AI 合成/AI 重建”。禁止把生成音频包装成真实通话、真实背书或历史录音。

建议建立一份来源表：`source_id / URL或文件 / 权利状态 / 获取日期 / 可用范围 / 是否允许训练 / 删除日期`。

## 1. 准备人物资料

按价值排序采集：

1. 本人自然长对话、访谈、直播转写：最能反映即时判断与口语节奏。
2. 本人演讲、文章、邮件：用于价值观、概念体系和稳定事实。
3. 可信传记与时间线：只补事实，不作为说话风格样本。
4. 第三方评价：单独标记为外部观点，不能写成第一人称记忆。

最低可用资料包建议包含 30–100 个真实问答、10–30 个关键事件、5–10 个反复出现的心智模型，以及“不知道/不该回答”的边界案例。

## 2. 准备声音样本

选择 10–30 秒单人干声，16 kHz 或更高、16 bit、无音乐、无混响、无重叠说话。内容应覆盖自然陈述、重音、停顿和目标语言常见音素。不要用情绪极端、电话窄带或经过强降噪的素材作为唯一样本。

保留准确 transcript；训练 API 可利用参考文本检查音频与文字差异。先做试听，不要立刻用于正式合成，因为首次正式合成可能触发音色槽位费用。

## 3. 蒸馏人格，不堆传记

把资料整理为 `personas/<id>/persona.md`，按下面结构写：

- `Identity`：明确是 AI 重建、默认语言、不可冒充真人。
- `Stable facts`：只放高置信、对话中常用的事实。
- `Mental models`：人物如何做判断，而不是只列观点结论。
- `Conversational character`：句长、节奏、反问、幽默、情绪强度。
- `Boundaries`：隐私、未知事实、专业高风险话题和禁止虚构项。
- `Style examples`：至少 20 个“用户输入 → 理想短回复”，覆盖正常、挑战、纠错和不知道。

口语 prompt 要短而硬。把低频资料放到检索层，不要把整本传记塞进 system prompt。默认回答控制在 1–4 句，首句先给判断，以便 LLM 尽快产出可合成文本。

## 4. 注册声音复刻 2.0

```bash
uv run python scripts/clone_voice.py sample.wav \
  --language zh \
  --persona your_person \
  --output personas/your_person/your_person.speaker.json \
  --demo-text "与样本完全一致的文字" \
  --i-have-rights
```

旧控制台凭据必须先在控制台开通声音复刻 2.0/音色服务，并把获配的音色槽位作为 `--speaker-id S_xxx` 传入；新版 API Key 后付费流程可不传。注册工具会拒绝把普通 TTS 官方音色误当复刻槽位。

保存返回的 `speaker_id`、训练时间、样本哈希、授权记录和试听结果，不保存或传播访问 Token。配置：

```bash
PERSONA_YOUR_PERSON_TTS_RESOURCE_ID=seed-icl-2.0
PERSONA_YOUR_PERSON_TTS_MODEL=seed-tts-2.0-expressive
PERSONA_YOUR_PERSON_TTS_SPEAKER=<speaker_id>
PERSONA_YOUR_PERSON_TTS_LANGUAGE=zh
```

## 5. 低延迟参数

- ASR：优化双向流 `bigmodel_async`，ASR 2.0 resource ID，16 kHz mono PCM；开启中间结果、ITN、标点和二遍识别。
- 分包：遵循官方建议使用约 200 ms 音频包。
- 判停：从 `DOUBAO_ASR_END_WINDOW_MS=500`、`VAD_MIN_SILENCE_S=0.35` 起步；安静环境可降低，嘈杂环境应提高。
- LLM：`deepseek-v4-flash`、关闭 thinking、限制口语输出 token；保留 system prompt + 最近 8 轮。
- TTS：V3 双向 WebSocket，让 LLM token 直接流向 TTS；输出 PCM，避免 MP3 句首静音。
- 打断：用户一开口就取消当前生成与播放；不要等待 TTS 整句结束。

不要只看总耗时。分别记录：VAD 判停、ASR final、LLM TTFB、TTS 首包、首音频播放、打断停止耗时，并统计 p50/p95。

## 6. 五类验收

每类至少 30 条固定测试题，版本间做盲测：

| 维度 | 通过标准示例 |
|---|---|
| 事实 | 高置信事实正确；不知道时不编 |
| 人格 | 盲测者能从判断方式识别人物，而非只靠口头禅 |
| 口语 | 无列表腔、客服腔；默认 1–4 句 |
| 声音 | 音色、韵律、重音、跨语言稳定，无明显伪影 |
| 实时性 | p95 首音频与打断耗时达到产品目标，无串话或重复播放 |

加入对抗题：诱导编造私事、要求声称是真人、伪造背书、越权专业建议、长篇朗读、连续快速打断。任何一次“冒充真人”都应阻断发布。

## 7. 上线与回滚

生产配置由密钥管理系统注入，不把 `.env.local`、样本或授权文件放进镜像。按人物隔离 speaker ID、资料库和会话日志。日志只记录 provider request/log ID、耗时和错误码，不记录 Token；用户可请求删除音频、资料和克隆音色。

保留一个已验收的官方音色作为显式降级选项，但降级必须向用户显示，不能在服务端静默换声。每次修改 persona、音色、模型或 VAD 参数都应重新跑固定评测集，并能一键回退到上一版本。

## Steve Jobs 示例

`personas/steve_jobs/persona.md` 已实现教育性 AI 重建的人格层：第一原则、产品体验、专注、设计与工程协作、短句 keynote 节奏，以及禁止虚构私人记忆和冒充本人。

仓库默认可用豆包官方英文男声 `en_male_tim_uranus_bigtts` 验证完整实时链路。它不是 Steve Jobs 本人音色。`personas/steve_jobs/SOURCES.md` 记录了人格研究的一手公开来源，但公开可访问不等于自动获得声音复刻权。若要精确声音复刻，必须确认具体素材与合成声音用途的权利，再用上面的声音注册步骤取得独立 `speaker_id`；界面仍须持续显示 AI 合成标识。
