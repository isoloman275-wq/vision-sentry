"""Vision Sentry tool handlers — code that runs when the LLM calls each tool.

Handlers receive (args, **kwargs) where kwargs are signature-inspected context
keywords (task_id/session_id/user_task) — NOT the plugin ctx. Config access
goes through the module-global captured at register() (same pattern as
phone-harness and other bundled plugins).
"""
import json
from pathlib import Path

from . import store, watcher

_plugin_ctx = None


def set_ctx(ctx) -> None:
    global _plugin_ctx
    _plugin_ctx = ctx


def _ctx():
    return _plugin_ctx


def _ok(**kw) -> str:
    return json.dumps({"ok": True, **kw})


def _err(msg: str, **kw) -> str:
    return json.dumps({"ok": False, "error": msg, **kw})


def sentry_status(args: dict, **kwargs) -> str:
    cfg = watcher.settings(_ctx())
    running = watcher.is_running()
    vision_ok = bool(cfg.get("vision_base_url") and cfg.get("vision_model"))
    return _ok(
        watcher_running=running,
        enabled=cfg.get("enabled", True),
        armed=cfg.get("armed", True),
        push_alerts=cfg.get("push_alerts", True),
        cam=cfg.get("cam_name", "front-door"),
        cam_configured=bool(cfg.get("rtsp_url")),
        scene_threshold=cfg.get("scene_threshold"),
        cooldown_secs=cfg.get("cooldown_secs"),
        vision_configured=vision_ok,
        vision_model=cfg.get("vision_model") or None,
        telegram_configured=bool(cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id")),
        webhook_configured=bool(cfg.get("notify_webhook_url")),
        total_events=store.count(),
    )


def sentry_events(args: dict, **kwargs) -> str:
    try:
        events = store.list_events(
            limit=args.get("limit") or 10,
            kind=args.get("kind"),
            since=args.get("since"),
        )
        return _ok(count=len(events), events=events)
    except Exception as exc:
        return _err(f"event query failed: {exc}")


def sentry_snap(args: dict, **kwargs) -> str:
    cfg = watcher.settings(_ctx())
    url = cfg.get("rtsp_url")
    if not url:
        return _err("no RTSP url configured (set SENTRY_RTSP_URL in .env or the plugin settings)")
    watcher._THUMB_DIR.mkdir(parents=True, exist_ok=True)
    import datetime as _dt
    snap = watcher._THUMB_DIR / f"snap_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    if not watcher._snapshot_frame(url, snap):
        return _err("could not grab a frame — camera unreachable or ffmpeg missing")
    verdict = watcher.classify_image(str(snap), cfg)
    if verdict.get("error"):
        return _ok(snapshot=str(snap), classification=None, note=verdict["error"])
    return _ok(snapshot=str(snap), classification=verdict)


def sentry_describe(args: dict, **kwargs) -> str:
    cfg = watcher.settings(_ctx())
    path = str(args.get("path") or "").strip()
    if not path:
        return _err("need an image path")
    verdict = watcher.classify_image(path, cfg)
    if verdict.get("error"):
        return _err(verdict["error"])
    return _ok(path=path, classification=verdict)


def sentry_simulate(args: dict, **kwargs) -> str:
    cfg = watcher.settings(_ctx())
    image_path = str(args.get("image_path") or "").strip() or store.latest_snapshot()
    if not image_path:
        return _err("no image: pass image_path, or grab one first with sentry_snap")
    p = Path(image_path)
    if not p.exists():
        return _err(f"image not found: {image_path}")
    verdict = watcher.classify_image(str(p), cfg)
    if verdict.get("error"):
        verdict = {}
    note = str(args.get("note") or "simulated event")
    event = watcher.record_event(_ctx(), str(p), verdict, note=note)
    return _ok(event=event)


def sentry_set_mode(args: dict, **kwargs) -> str:
    changed = []
    with watcher.RUNTIME_LOCK:
        if "armed" in args and args["armed"] is not None:
            watcher.RUNTIME["armed"] = bool(args["armed"])
            changed.append(f"armed={watcher.RUNTIME['armed']}")
        if args.get("scene_threshold") is not None:
            try:
                watcher.RUNTIME["scene_threshold"] = float(args["scene_threshold"])
                changed.append(f"scene_threshold={watcher.RUNTIME['scene_threshold']}")
            except (TypeError, ValueError):
                return _err("scene_threshold must be a number 0-1")
        if args.get("cooldown_secs") is not None:
            try:
                watcher.RUNTIME["cooldown_secs"] = int(args["cooldown_secs"])
                changed.append(f"cooldown_secs={watcher.RUNTIME['cooldown_secs']}")
            except (TypeError, ValueError):
                return _err("cooldown_secs must be an integer")
        if args.get("push_alerts") is not None:
            watcher.RUNTIME["push_alerts"] = bool(args["push_alerts"])
            changed.append(f"push_alerts={watcher.RUNTIME['push_alerts']}")
    if not changed:
        return _err("nothing to change: pass armed / scene_threshold / cooldown_secs / push_alerts")
    return _ok(changed=changed, status=json.loads(sentry_status({})))
