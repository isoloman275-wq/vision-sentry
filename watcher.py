"""Vision Sentry watcher: ffmpeg scene detection -> vision classification ->
event store -> notifications -> agent alert queue.

Adapted from a production-proven ffmpeg scene-detect loop (select='gt(scene,X)').
The watcher thread defers its first tick so `hermes plugins doctor` (which
blocks sockets during registration) never sees network activity from register().
"""
import base64
import datetime
import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: events awaiting injection into the agent's next turn (pre_llm_call drains it)
ALERT_QUEUE: list[str] = []
_QUEUE_LOCK = threading.Lock()

#: runtime switches the tools mutate (armed, push_alerts, thresholds)
RUNTIME_LOCK = threading.Lock()
RUNTIME = {
    "armed": True,
    "push_alerts": True,
    "scene_threshold": None,  # None = use config default
    "cooldown_secs": None,
}

_SHUTDOWN = threading.Event()
_THREADS: list[threading.Thread] = []
_THUMB_DIR = Path(os.path.expanduser("~/.hermes/plugin-data/vision-sentry/thumbs"))
_LOCKFILE = _THUMB_DIR.parent / "watcher.lock"

#: the live ffmpeg reader process (terminated on unload so gateway reloads
#: never orphan a second scene-detect stream)
_PROC: subprocess.Popen | None = None
_PROC_LOCK = threading.Lock()

# ffmpeg showinfo prints one line per frame the select filter passes (a scene
# cut): "[Parsed_showinfo_1 @ ...] n: 3 pts_time:1234.56 ...". That pts_time
# line is the event signal (same pattern as the proven vacation sentinel).
# Some builds also emit a "scene_score," select line; if present we take the
# score, otherwise None.
_PTS_RE = re.compile(r"pts_time:([0-9.]+)")
_SCENE_RE = re.compile(r"scene_score[:]?\s*[,=]?\s*([0-9.]+)")


def settings(ctx=None) -> dict:
    """Read effective settings: config schema values + runtime overrides."""
    cfg = {}
    if ctx is not None:
        for key, default in [
            ("rtsp_url", ""), ("cam_name", "front-door"), ("scene_threshold", 0.08),
            ("cooldown_secs", 30), ("enabled", True), ("notify_webhook_url", ""),
            ("telegram_bot_token", ""), ("telegram_chat_id", ""),
            ("vision_base_url", ""), ("vision_model", ""), ("vision_api_key", ""),
            ("classify_timeout", 60),
        ]:
            try:
                cfg[key] = ctx.get_config(key, default=default)
            except Exception:
                cfg[key] = default
    with RUNTIME_LOCK:
        cfg["armed"] = RUNTIME["armed"]
        cfg["push_alerts"] = RUNTIME["push_alerts"]
        if RUNTIME["scene_threshold"] is not None:
            cfg["scene_threshold"] = RUNTIME["scene_threshold"]
        if RUNTIME["cooldown_secs"] is not None:
            cfg["cooldown_secs"] = RUNTIME["cooldown_secs"]
    # Secrets live in the .env secret scope, never in config.
    try:
        from agent.secret_scope import get_secret
        if not cfg.get("rtsp_url"):
            cfg["rtsp_url"] = get_secret("SENTRY_RTSP_URL", "") or ""
        if not cfg.get("telegram_bot_token"):
            cfg["telegram_bot_token"] = get_secret("SENTRY_TELEGRAM_BOT_TOKEN", "") or ""
        if not cfg.get("vision_api_key"):
            cfg["vision_api_key"] = get_secret("SENTRY_VISION_API_KEY", "") or ""
    except Exception:
        pass
    if cfg.get("rtsp_url") and "://" in cfg["rtsp_url"] and "@" in cfg["rtsp_url"]:
        # Also allow the raw URL to be passed directly via config/schema secret.
        pass
    cfg.setdefault("rtsp_url", "")
    if not cfg.get("rtsp_url"):
        # Schema-declared secret env is the primary source; peek the scoped env directly.
        cfg["rtsp_url"] = os.environ.get("SENTRY_RTSP_URL", "")
    if not cfg.get("telegram_bot_token"):
        cfg["telegram_bot_token"] = os.environ.get("SENTRY_TELEGRAM_BOT_TOKEN", "")
    if not cfg.get("vision_api_key"):
        cfg["vision_api_key"] = os.environ.get("SENTRY_VISION_API_KEY", "")
    cfg["vision_base_url"] = (cfg.get("vision_base_url") or "").rstrip("/")
    return cfg


# ---------------------------------------------------------------- classification

_CLASSIFY_PROMPT = (
    "You are a security camera analyst. Look at this frame from a fixed "
    "security camera and answer with STRICT JSON only, no markdown:\n"
    '{"subject": "<one of: person, person_known, courier, vehicle, package, '
    'animal, weather, empty_scene, other>",\n'
    ' "summary": "<one factual sentence: what is visible>",\n'
    ' "person_count": <int>,\n'
    ' "details": "<short observations: clothing, direction of movement, '
    'vehicles, parcels, anything notable>",\n'
    ' "attention": "<low|medium|high — high only for unknown persons at '
    'doors/windows, distress, or property damage>",\n'
    ' "confidence": <0.0-1.0>}\n'
    "If the frame is empty scenery, say empty_scene with low attention. "
    "The camera may look out through a window — glass reflections are not "
    "objects. Never invent people or objects that are not visible."
)


def classify_image(image_path: str, cfg: dict) -> dict:
    """Send a frame to the configured OpenAI-compatible vision endpoint."""
    base = cfg.get("vision_base_url") or ""
    model = cfg.get("vision_model") or ""
    if not base or not model:
        return {"error": "vision endpoint not configured (set vision_base_url + vision_model)"}
    p = Path(image_path)
    if not p.exists():
        return {"error": f"image not found: {image_path}"}
    b64 = base64.b64encode(p.read_bytes()).decode()
    url = base + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _CLASSIFY_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ],
        }],
        "max_tokens": 400,
        "temperature": 0.1,
    }
    headers = {"Content-Type": "application/json"}
    if cfg.get("vision_api_key"):
        headers["Authorization"] = "Bearer " + cfg["vision_api_key"]
    import requests
    try:
        r = requests.post(url, json=payload, headers=headers,
                          timeout=int(cfg.get("classify_timeout") or 60))
    except Exception as exc:
        return {"error": f"vision endpoint unreachable: {exc}"}
    if r.status_code != 200:
        return {"error": f"vision endpoint {r.status_code}: {r.text[:300]}"}
    try:
        text = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return {"error": f"unexpected vision response shape: {exc}"}
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"error": "vision model did not return JSON", "raw": text[:300]}
    try:
        verdict = json.loads(m.group(0))
    except Exception:
        return {"error": "vision JSON unparseable", "raw": text[:300]}
    verdict["model"] = model
    return verdict


def _notify(cfg: dict, event: dict) -> None:
    """Fire-and-forget notifications: Telegram sendPhoto and/or generic webhook."""
    text = f"📷 Vision Sentry [{event.get('cam', '')}] — {event.get('kind', 'motion')}\n{event.get('summary', '')}"
    snap = event.get("snapshot") or ""
    token, chat = cfg.get("telegram_bot_token") or "", cfg.get("telegram_chat_id") or ""
    if token and chat:
        try:
            import requests
            method = "sendPhoto" if snap and Path(snap).exists() else "sendMessage"
            files = {"photo": open(snap, "rb")} if method == "sendPhoto" else None
            data = {"chat_id": chat, "caption": text[:1000]}
            r = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                              data=data, files=files, timeout=30)
            if files:
                files["photo"].close()
            if r.status_code != 200:
                logger.warning("sentry telegram notify %s: %s", r.status_code, r.text[:200])
        except Exception as exc:
            logger.warning("sentry telegram notify failed: %s", exc)
    hook = cfg.get("notify_webhook_url") or ""
    if hook:
        try:
            import requests
            requests.post(hook, json={"event": event}, timeout=10)
        except Exception as exc:
            logger.warning("sentry webhook notify failed: %s", exc)


def record_event(ctx, snapshot: str, verdict: dict | None, note: str = "",
                 cam: str = "") -> dict:
    """Full pipeline tail shared by watcher and tools: store -> notify -> alert."""
    cfg = settings(ctx)
    verdict = verdict or {}
    kind = verdict.get("subject") or "motion"
    summary = note or verdict.get("summary") or "motion detected"
    event = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "cam": cam or cfg.get("cam_name", "front-door"),
        "kind": kind,
        "summary": summary,
        "confidence": verdict.get("confidence"),
        "snapshot": snapshot,
        "attention": verdict.get("attention", ""),
        "details": verdict.get("details", ""),
    }
    from . import store as _store
    # Cross-process dedupe: if the same camera recorded an event moments ago
    # (a second watcher loop somewhere), collapse this one into it.
    try:
        recent = _store.list_events(limit=1, kind=None, since=None)
        if recent:
            import datetime as _dt
            age = (_dt.datetime.now().astimezone()
                   - _dt.datetime.fromisoformat(recent[0]["ts"])).total_seconds()
            cooldown = int(cfg.get("cooldown_secs") or 30)
            if recent[0].get("cam") == event["cam"] and 0 <= age < max(cooldown - 3, 3):
                event["id"] = recent[0]["id"]
                event["deduped"] = True
                return event
    except Exception:
        logger.debug("sentry dedupe check failed; storing event", exc_info=True)
    event["id"] = _store.add_event(
        cam=event["cam"], kind=kind, summary=summary,
        confidence=verdict.get("confidence"), snapshot=snapshot,
        extra={"attention": event["attention"], "details": event["details"],
               "note": note} if (note or event["attention"] or event["details"]) else None,
    )
    _notify(cfg, event)
    if cfg.get("push_alerts", True) and RUNTIME.get("push_alerts", True):
        line = (f"📷 SENTRY EVENT [{event['cam']}]: {kind} — {summary} "
                f"(snapshot: {snapshot or 'none'}, event #{event['id']}). "
                f"Use sentry_events to review; mention it briefly to the user unless asked otherwise.")
        with _QUEUE_LOCK:
            ALERT_QUEUE.append(line)
            if len(ALERT_QUEUE) > 20:
                del ALERT_QUEUE[:-20]
    return event


# ---------------------------------------------------------------- watcher loop

def _grab_rtsp(rtsp_url: str, threshold: float, on_motion) -> None:
    """Run ffmpeg scene detection; call on_motion(pts, score) per scene cut."""
    global _PROC
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-rtsp_transport", "tcp", "-timeout", "15000000",
        "-i", rtsp_url,
        "-vf", f"scale=640:360,select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            text=True, errors="replace")
    with _PROC_LOCK:
        _PROC = proc
    try:
        for line in proc.stderr:  # type: ignore[union-attr]
            if "pts_time" not in line:
                continue
            pm = _PTS_RE.search(line)
            sm = _SCENE_RE.search(line)
            on_motion(float(sm.group(1)) if sm else None,
                      float(pm.group(1)) if pm else None)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _snapshot_frame(rtsp_url: str, out_path: Path, timeout=15) -> bool:
    # 640px evidence frames: large frames can stall vision-projector encoding
    # for minutes on CPU projectors (measured: 1080p hung >90s, 640px = ~38s).
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", "-timeout", "15000000",
        "-i", rtsp_url, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4",
        "-y", str(out_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return out_path.exists() and out_path.stat().st_size > 1000
    except Exception as exc:
        logger.warning("sentry snapshot failed: %s", exc)
        return False


def _watcher_loop(ctx, cfg: dict) -> None:
    """One camera's watch loop. Reconnects forever, respects armed/cooldown."""
    cam = cfg.get("cam_name", "front-door")
    url = cfg.get("rtsp_url")
    last_event = 0.0
    backoff = 5
    while not _SHUTDOWN.is_set():
        _heartbeat()
        if not RUNTIME.get("armed", True):
            time.sleep(2)
            continue
        cur = settings(ctx)
        url = cur.get("rtsp_url") or url
        if not url:
            time.sleep(5)
            continue
        threshold = float(cur.get("scene_threshold") or 0.08)
        cooldown = int(cur.get("cooldown_secs") or 30)
        _THUMB_DIR.mkdir(parents=True, exist_ok=True)

        def on_motion(score, pts):
            nonlocal last_event
            now = time.time()
            if now - last_event < cooldown:
                return
            last_event = now
            stamp = datetime.datetime.now().strftime("motion_%H%M%S")
            snap_path = _THUMB_DIR / f"{stamp}.jpg"
            # grab the actual frame for the snapshot (detection frame is lost to the pipe)
            if not _snapshot_frame(url, snap_path):
                snap_path = _THUMB_DIR / f"{stamp}.png"
                if not _snapshot_frame(url, snap_path):
                    snap_path = None
            cfg_now = settings(ctx)
            verdict = {}
            if snap_path:
                verdict = classify_image(str(snap_path), cfg_now)
                if verdict.get("error"):
                    logger.info("sentry classify skipped: %s", verdict["error"])
                    verdict = {}
            record_event(ctx, str(snap_path) if snap_path else "", verdict, cam=cam)

        try:
            _grab_rtsp(url, threshold, on_motion)
            # ffmpeg exited (stream dropped) — retry with backoff
            if _SHUTDOWN.is_set():
                return
            logger.info("sentry stream ended; reconnecting in %ss", backoff)
            _SHUTDOWN.wait(backoff)
            backoff = min(backoff * 2, 120)
        except Exception as exc:
            logger.warning("sentry watcher loop error: %s", exc)
            _SHUTDOWN.wait(backoff)


def _heartbeat_fresh(max_age=75) -> bool:
    """True when another watcher loop (this or a previous process) pinged recently."""
    try:
        if not _LOCKFILE.exists():
            return False
        ts = float(_LOCKFILE.read_text().strip().split("|")[0])
        if time.time() - ts > max_age:
            return False
        pid = int(_LOCKFILE.read_text().strip().split("|")[1])
        os.kill(pid, 0)  # raises if the owner is dead
        return True
    except (ProcessLookupError, PermissionError, ValueError, IndexError):
        return False
    except OSError:
        return False


def _heartbeat() -> None:
    try:
        _LOCKFILE.write_text(f"{time.time()}|{os.getpid()}")
    except OSError:
        pass


def start(ctx) -> None:
    """Start the watcher thread(s). Idempotent across reloads AND processes;
    doctor-safe (deferred tick)."""
    if _THREADS:
        return
    cfg = settings(ctx)
    if not cfg.get("enabled", True):
        logger.info("vision-sentry watcher disabled by config")
        return
    if not cfg.get("rtsp_url"):
        logger.info("vision-sentry: no RTSP url configured; watcher idle")
        return
    if _heartbeat_fresh():
        logger.info("vision-sentry: another watcher loop is alive; not starting a duplicate")
        return
    _SHUTDOWN.clear()  # a previous unload may have set it in this process
    _heartbeat()
    t = threading.Thread(target=_watcher_loop, args=(ctx, cfg),
                         name="vision-sentry-watcher", daemon=True)
    _THREADS.append(t)
    t.start()
    hb = threading.Thread(target=_heartbeat_loop, name="vision-sentry-heartbeat",
                          daemon=True)
    hb.start()


def _heartbeat_loop() -> None:
    """Keep the watcher.lock fresh even while the loop is blocked inside a
    long-quiet _grab_rtsp read — the cross-process duplicate guard depends on it."""
    while not _SHUTDOWN.is_set() and any(t.is_alive() for t in _THREADS):
        _heartbeat()
        _SHUTDOWN.wait(20)


def stop() -> None:
    """Stop all watcher loops and the ffmpeg reader (unload/reload teardown)."""
    _SHUTDOWN.set()
    with _PROC_LOCK:
        proc = _PROC
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def is_running() -> bool:
    return any(t.is_alive() for t in _THREADS)
