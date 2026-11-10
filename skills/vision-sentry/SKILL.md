---
name: vision-sentry
description: Operating the Vision Sentry camera watcher — arm/disarm, querying events, live checks, alert behavior, and troubleshooting
---

# Vision Sentry Operations

Vision Sentry watches RTSP cameras with ffmpeg scene detection, classifies each
event with a vision model, stores events locally, and (when armed + push enabled)
injects a short alert line into your next turn — that is how you "hear" the
camera without being asked.

## Daily use

- **Unprompted alerts**: when you see a "📷 SENTRY EVENT" line in your context,
  mention it to the user in one line. Do not re-analyze it unless asked; the
  snapshot path is included if they want more.
- **What's happening now?** → `sentry_snap` (grabs a live frame + classifies).
- **When did the courier come?** / **Anyone at the door since Tuesday?** →
  `sentry_events` with `since` ("2 hours ago", ISO) and optional `kind`
  (person / person_known / courier / vehicle / package / animal / motion /
  empty_scene / other).
- **Going out / coming home** → `sentry_set_mode` with `armed: true/false`.
- **Too chatty / missing events** → `sentry_set_mode` with
  `scene_threshold` (higher = less sensitive; default 0.08) or `cooldown_secs`.

## Modes

- `armed=false` — watcher idles; live `sentry_snap` still works.
- `push_alerts=false` — events still stored + notified, but no turn injection.
- No vision endpoint configured — events store as kind "motion" with no verdict;
  ask the user to set `vision_base_url` + `vision_model` (any OpenAI-compatible
  endpoint: local Ollama/llama.cpp/llama-server or a cloud API).

## Troubleshooting

- `sentry_status` shows `cam_configured: false` → the RTSP URL secret
  (SENTRY_RTSP_URL) is not set. It lives in the profile .env, never in config.
- `watcher_running: false` + enabled → check ffmpeg is on PATH and the RTSP
  URL/port; the watcher reconnects with backoff on stream drops.
- Snapshots land in `~/.hermes/plugin-data/vision-sentry/thumbs/`.
- Event history is SQLite at `~/.hermes/plugin-data/vision-sentry/data.db`.
- To demo without waiting for motion: `sentry_simulate` with any image path.
