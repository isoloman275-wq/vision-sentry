"""Vision Sentry — agent vision for any RTSP camera.

register(ctx) wires tools, the pre_llm_call alert-injection hook, and starts
the background watcher (deferred 2s so `hermes plugins doctor`, which blocks
sockets during registration, never sees network activity from register()).
"""
import logging
import threading

from . import schemas, tools, watcher

logger = logging.getLogger(__name__)


def _on_pre_llm_call(**kwargs):
    """Inject queued sentry events into the agent's next turn (user message)."""
    with watcher._QUEUE_LOCK:
        if not watcher.ALERT_QUEUE:
            return None
        pending = watcher.ALERT_QUEUE[:]
        watcher.ALERT_QUEUE.clear()
    return {"context": "\n".join(pending)}


def _deferred_start(ctx) -> None:
    try:
        watcher.start(ctx)
    except Exception:
        logger.exception("vision-sentry watcher failed to start")


def register(ctx) -> None:
    tools.set_ctx(ctx)

    def tool(name, schema, handler, description, emoji="📷"):
        ctx.register_tool(name=name, toolset="vision-sentry", schema=schema,
                          handler=handler, description=description, emoji=emoji)

    tool("sentry_status", schemas.SENTRY_STATUS, tools.sentry_status,
         "Camera watcher status: running, armed, event counts, configured channels")
    tool("sentry_events", schemas.SENTRY_EVENTS, tools.sentry_events,
         "Query stored camera events with vision verdicts and snapshot paths")
    tool("sentry_snap", schemas.SENTRY_SNAP, tools.sentry_snap,
         "Grab a live frame and classify it now")
    tool("sentry_describe", schemas.SENTRY_DESCRIBE, tools.sentry_describe,
         "Classify any image with the sentry vision pipeline")
    tool("sentry_simulate", schemas.SENTRY_SIMULATE, tools.sentry_simulate,
         "Feed an image through the full event pipeline (demo/testing)")
    tool("sentry_set_mode", schemas.SENTRY_SET_MODE, tools.sentry_set_mode,
         "Arm/disarm, sensitivity, cooldown, alert push at runtime")

    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.on_unload(watcher.stop)  # teardown: kill the ffmpeg reader on reload

    threading.Timer(2.0, _deferred_start, args=(ctx,)).start()
    logger.info("vision-sentry registered: 6 tools, pre_llm_call hook, watcher deferred-start")
