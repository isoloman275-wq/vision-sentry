# Catalog PR description (paste into the PR body)

## Plugin: vision-sentry

**What it does:** Agent vision for any RTSP camera. Watches RTSP feeds with
ffmpeg scene detection, classifies every event with a vision model (any
OpenAI-compatible endpoint — local llama.cpp/Ollama or cloud), stores events
in local SQLite, and injects fresh alerts into the agent's next turn via the
`pre_llm_call` hook so Hermes *tells the user* what it saw — with verdict,
snapshot path and event id — unprompted. Six tools cover status, history
queries (natural-language time filters), live snapshot classification, image
description, demo injection, and runtime arm/disarm/sensitivity/cooldown
control. Ships with an operations skill.

**Why a plugin (more than a skill):** a skill cannot hold a persistent RTSP
watcher open for weeks, cannot inject an alert into the agent's next turn, and
cannot keep cross-restart event memory. The watcher loop, the
`pre_llm_call` alert channel, the SQLite store behind `plugin_db()`, and
runtime state are all plugin-surface machinery.

## Surfaces used
- Tools: `ctx.register_tool()` ×6 (toolset `vision-sentry`)
- Hook: `ctx.register_hook("pre_llm_call")` — drains an in-process alert queue
  into the user message (bounded, max 20 pending, oversized spill respected)
- Lifecycle: `ctx.on_unload()` — terminates the ffmpeg reader on reload
- State: `plugins.plugin_storage.plugin_db()` (SQLite WAL) + plugin data dir
- Config: `config_schema` (incl. three `secret` fields resolved through the
  `.env` secret scope; RTSP URL, Telegram token, vision API key never touch
  config.yaml)
- Skill: bundled `skills/vision-sentry/SKILL.md`

## Disclosure (catalog rule 13)
- Requires `ffmpeg` on PATH (system dependency; the plugin shells out to it
  for RTSP scene detection and snapshot grabs).
- Optional network calls from tool/watcher code:
  - the configured vision endpoint (`vision_base_url`, user-configured host)
    — OpenAI-compatible `/chat/completions` with base64 image content;
  - Telegram Bot API `api.telegram.org` (only if bot token + chat id set);
  - the configured webhook URL (only if set).
- No other hosts. Frames are written to the plugin data dir; classification
  goes only to the user-configured endpoint.

## Reliability work (validated live on a 3-node home lab)
- Single-watcher heartbeat lock: gateway reloads / extra Hermes processes
  never spawn duplicate RTSP watchers (measured: duplicate loops from reload
  churn — fixed and regression-tested).
- `on_unload` teardown kills the ffmpeg reader so updates never orphan a
  stream (observed orphan pre-fix, clean post-fix).
- Store-level cross-process dedupe collapses overlapping events.
- 640px evidence frames: full-resolution frames can stall CPU vision
  projectors for minutes (measured >90s vs ~16s).
- Vision-endpoint outages degrade gracefully: events store unclassified.
- `hermes plugins validate` and `hermes plugins doctor --ci` both pass.

## Screenshots
(screenshots of the Desktop plugin settings page + an injected alert in chat
will be attached to the PR)
