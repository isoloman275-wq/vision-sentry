# Vision Sentry — 90-second demo script

Goal: show the loop no consumer camera app can do — perceive → classify →
remember → TELL (unprompted) → answer → act. Judges score usefulness,
reliability, polish, creativity, and "more than a skill".

## Cast / setup
- Hermes Desktop app, chat open, plugin installed + armed.
- Real RTSP camera (Tapo, front-door window view).
- Local vision: llama.cpp llama-server, Qwen3-VL-8B Q4 on the M1 GPU.
- ffmpeg gdigrab recording 1920x1080 @30fps.

## Beats (target ≤90s)

| t | Action | What it proves |
|---|---|---|
| 0-10s | Intro line over status: `sentry_status` result on screen — watcher running, armed, local vision model | Real, configured system |
| 10-30s | **Hux walks past the window.** Camera fires; snapshot grabbed; Qwen3-VL classifies "person"; `pre_llm_call` injects the alert → Hermes announces it in the chat WITHOUT being asked: "📷 SENTRY EVENT: person — ..." | The core differentiator: agent announces, app pings |
| 30-45s | Ask: "What did you just see? Show me." → agent answers with the verdict and renders the actual snapshot in chat (MEDIA path) | Queryable memory + agent-visible evidence |
| 45-60s | Ask: "Has anyone been at the house since yesterday?" → `sentry_events since="1 day ago"` → natural-language history query | SQLite memory, NL time filters |
| 60-75s | Say: "I'm home — stand down." → `sentry_set_mode armed=false` → status shows disarmed; then re-arm | Runtime control in one sentence |
| 75-90s | Close: "Works with any RTSP camera and any OpenAI-compatible vision model — fully local, frames never leave your LAN. Install: vision-sentry." | Positioning + CTA |

## Recording checklist
- [ ] ffmpeg.exe working: `ffprobe -f gdigrab -i desktop` test frame
- [ ] Chat window clean (close sidebars), font zoom comfortable at 1080p
- [ ] Walk-past rehearsed once (slow, full body in frame)
- [ ] One take ≤90s; if the alert misses, use `sentry_simulate` fallback shot
- [ ] Export mp4 (h264), ≤1080p, verify audio/none needed (silent + captions OK)

## Fallback footage
Live person event preferred. If the scene-change threshold misses a slow walk,
raise sensitivity first (`sentry_set_mode scene_threshold 0.05`), re-take.
`sentry_simulate` with a captured snapshot is the honest last resort — label it
in the video as "injected for pacing".
