# Vision Sentry — submission review pack

**For:** Hux + second reviewer
**Gate:** NOTHING below is published/submitted until both sign off.
**Deadline:** hackathon submissions close 5PM EST Nov 11 = 12:00pm NZDT Nov 12.

## 1. What to review

| Artifact | Where |
|---|---|
| Plugin source | this repo (`~/repos/vision-sentry`, git history is the audit trail) |
| Manifest + deps | `plugin.yaml` (v1 schema), `pyproject.toml` (requests only) |
| Tool surface | `schemas.py` (LLM-facing), `tools.py` (handlers) |
| Watcher pipeline | `watcher.py` (ffmpeg → classify → store → notify → alert queue) |
| Event memory | `store.py` (SQLite via `plugin_db()`) |
| Bundled skill | `skills/vision-sentry/SKILL.md` |
| Docs | `README.md`, `DEMO-SCRIPT.md`, `PR-DESCRIPTION.md`, `plugin-catalog-entry.yaml` |

## 2. Verification evidence (live, measured)

- `hermes plugins validate` PASS · `hermes plugins doctor --ci` PASS (6 tools, 1 hook)
- Real RTSP cam (Tapo :554, window view): frame grab ~4s; live events #2-4
  classified and stored; alert injection verified into a real chat turn
  (pre_llm_call hook — no polling)
- Agent-driven end-to-end: `sentry_simulate` in a live `hermes chat` session →
  DB row byte-verified
- Full-res vs 640px frame classification: >90s stall vs ~16s (projector limit)
- Duplicate-watcher bug: found in soak (two loops from reload churn), fixed
  with on_unload teardown + heartbeat lock + store-level dedupe; re-validated

## 3. Review checklist

- [ ] Secrets: RTSP URL / Telegram token / vision key are `secret` schema
      fields only — grep the repo for hard-coded creds (should be zero)
- [ ] Rule-13 disclosure in `PR-DESCRIPTION.md` matches code reality
- [ ] Demo video ≤90s, shows the unprompted alert + query + control
- [ ] You approve the repo push (public, under isoloman275-wq)
- [ ] You approve the catalog PR (one-file `plugin-catalog/vision-sentry.yaml`,
      pinned SHA)
- [ ] You approve the typeform submission

## 4. Post-approval runbook (execute only on both go)

1. `git push` repo to github.com/isoloman275-wq/vision-sentry (public)
2. Record SHA → fill `plugin-catalog-entry.yaml` → PR to NousResearch/hermes-agent
3. Screenshot attachments on the PR (settings page + injected alert)
4. Typeform: PR link + X demo video link
5. Post demo video on X tagging @NousResearch (Hux's account — needs his go)
