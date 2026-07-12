# Talk to Persona: Cloud Realtime Character Conversations

[中文](README.md)

This project turns authorized character materials into an interruptible realtime voice conversation using one fixed cloud pipeline:

```text
LiveKit WebRTC → Doubao Streaming ASR 2.0 → DeepSeek V4 Flash → Doubao V3 Bidirectional WebSocket TTS
```

It requires no local GPU and never silently falls back to a different provider. Character profiles live in `personas/<name>/persona.md`. An explicitly disclosed, educational Steve Jobs-inspired example is included in `personas/steve_jobs/`.

```bash
uv sync
uv run python scripts/bootstrap_cloud_env.py \
  --key-file ~/Documents/key.txt \
  --persona steve_jobs \
  --speaker en_male_tim_uranus_bigtts \
  --tts-resource seed-tts-2.0 \
  --tts-language en
./Talk-to-Me-V3.6.command
```

See [README.md](README.md) for configuration and [the cloning SOP](docs/PERSONA_CLONING_SOP.md) for material preparation, voice enrollment, evaluation, and disclosure requirements.

Only clone voices and use source materials you are authorized to use. Always disclose synthetic output; never use it for impersonation, fraud, fabricated endorsements, or fake archival recordings.
