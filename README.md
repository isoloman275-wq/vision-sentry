# Vision Sentry

**Agent vision for any RTSP camera.** Your camera app detects motion and pings
you. Vision Sentry makes your agent *see*: every scene event is classified by a
vision model, stored in a queryable event memory, and — when something notable
happens — Hermes tells **you** what it saw, unprompted, in its next turn.

```
📷 SENTRY EVENT [front-door]: vehicle — A vehicle with bright headlights is
approaching the house at night. (snapshot: .../thumbs/motion_0304.jpg, event #7)
```

That alert rides Hermes' `pre_llm_call` hook — it is injected into the agent's
next turn in whatever chat is active (CLI, Telegram, Desktop). No polling, no
app. The camera becomes something your agent can report on, answer questions
about, and act on.

## What it does

- **Watches any RTSP camera** with ffmpeg scene detection (reconnects forever,
  cooldown + arm/disarm at runtime, no cloud dependency).
- **Classifies every event** with a vision model via any OpenAI-compatible
  endpoint — local Ollama / llama.cpp / llama-server, or a cloud API. Run the
  brains on your own hardware (data sovereignty) or in the cloud; it's a config
  field, not a fork.
- **Remembers everything**: SQLite event memory (`kind`, summary, confidence,
  details, snapshot path) that survives updates and follows the active profile.
- **Answers questions**: "when did the courier come?", "has anyone been at the
  gate since Tuesday?" — natural-language time filters over the event store.
- **Live checks**: `sentry_snap` grabs and classifies a frame right now.
- **Notifies anywhere**: Telegram (photo + verdict) and/or a generic webhook —
  optional; the agent-injection channel needs no configuration.
- **Safe by design**: camera URL and API keys are `.env` secrets, never config;
  runtime settings are hot-editable by the agent through `sentry_set_mode`.

## The demo (why a plugin, not a skill)

A skill can describe a photo. It cannot hold a persistent RTSP watcher open for
weeks, inject an alert into the agent's next turn, remember every event, or
notify Telegram at 3am while you sleep. Vision Sentry is the full loop:
**perceive → classify → remember → tell → act.**

## Tools

| Tool | What it does |
|---|---|
| `sentry_status` | watcher state, camera reachability, configured channels |
| `sentry_events` | query events (`kind` / `since` — "2 hours ago", ISO) |
| `sentry_snap` | grab + classify a live frame now |
| `sentry_describe` | classify any image with the same pipeline |
| `sentry_simulate` | feed any image through the full pipeline (demo/testing) |
| `sentry_set_mode` | arm/disarm, sensitivity, cooldown, alert push — at runtime |

## Setup

1. Install: `hermes plugins install isoloman275-wq/vision-sentry --enable`
2. Set your camera URL (secret, lands in `.env`):
   `SENTRY_RTSP_URL=rtsp://user:pass@cam-ip:554/stream1`
3. Point it at a vision model (any OpenAI-compatible endpoint):
   ```
   hermes config set plugins.entries.vision-sentry.settings.vision_base_url http://localhost:11434/v1
   hermes config set plugins.entries.vision-sentry.settings.vision_model qwen2.5vl:7b
   ```
4. (Optional) Telegram snapshots: `SENTRY_TELEGRAM_BOT_TOKEN` + `telegram_chat_id`.

Requires `ffmpeg` on PATH. Python deps: `requests` only.

## Vision model notes

- 640px evidence frames are classified (~15–40 s per verdict on a mid-range
  GPU with a CPU vision projector). Full-resolution frames can stall
  projector-based models — the plugin grabs 640px on purpose.
- Works with any model that accepts `image_url` content parts: Qwen2.5-VL,
  Qwen3-VL, LLaVA, GPT-4o-mini, Gemini, etc.

## Design notes

- **Single-watcher guard**: a heartbeat lockfile (`watcher.lock`) means gateway
  reloads and extra Hermes processes never spawn duplicate RTSP watchers.
- **Reload-safe teardown**: `on_unload` kills the ffmpeg reader so plugin
  updates never orphan a stream.
- **Runtime-only duplicate rejection** is belt-and-braces with the guard:
  duplicate events from a second loop are still rejected at the store.

## Privacy

Frames stay on the machine that runs Hermes: snapshots are written to the
plugin's data directory, and classification goes to whatever endpoint **you**
configured — a fully local stack (local camera + local model + local SQLite)
never sends a pixel off your LAN.

## License

MIT
