"""Vision Sentry tool schemas — what the LLM reads to decide when to call."""

SENTRY_STATUS = {
    "name": "sentry_status",
    "description": (
        "Vision Sentry camera watcher status: whether the watcher thread is "
        "running, cameras configured/reachable, armed state, event counts, "
        "vision-classification endpoint health, and notification channels. "
        "Use when the user asks about their camera, security, or sentry state."
    ),
    "parameters": {"type": "object", "properties": {}},
}

SENTRY_EVENTS = {
    "name": "sentry_events",
    "description": (
        "Query Vision Sentry's stored camera events: what was seen, when, the "
        "vision-model verdict (subject, summary, confidence) and the snapshot "
        "file path. Filter by event kind or time. Use for questions like "
        "'when did the courier come?', 'has anyone been at the door since "
        "Tuesday?', 'show me the last camera events'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max events to return (default 10, max 50)",
            },
            "kind": {
                "type": "string",
                "description": (
                    "Optional verdict filter: person, courier, vehicle, "
                    "package, animal, motion, unknown"
                ),
            },
            "since": {
                "type": "string",
                "description": (
                    "Optional: only events after this ISO timestamp "
                    "(e.g. '2026-11-05T08:00:00') or a plain phrase like "
                    "'2 hours ago'"
                ),
            },
        },
    },
}

SENTRY_SNAP = {
    "name": "sentry_snap",
    "description": (
        "Grab a live frame from the camera right now and classify it with the "
        "vision model. Returns the verdict, summary and snapshot path. Use "
        "when the user wants to see/understand what the camera sees at this "
        "moment ('what's happening at the front door?')."
    ),
    "parameters": {"type": "object", "properties": {}},
}

SENTRY_DESCRIBE = {
    "name": "sentry_describe",
    "description": (
        "Classify a specific image file (any path on disk) with the same "
        "vision pipeline the sentry uses. Useful to re-analyze a stored "
        "event snapshot, or to identify what is in any image in the "
        "security/household context."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the image file to classify",
            },
        },
        "required": ["path"],
    },
}

SENTRY_SIMULATE = {
    "name": "sentry_simulate",
    "description": (
        "Inject a synthetic Vision Sentry event for testing or demo: runs the "
        "image through the full classification pipeline, stores the event, "
        "sends notifications and queues an agent alert exactly like a real "
        "camera event. Pass an existing image path, or omit it to use the "
        "latest stored snapshot."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Optional image path to feed the pipeline",
            },
            "note": {
                "type": "string",
                "description": "Optional label stored with the event",
            },
        },
    },
}

SENTRY_SET_MODE = {
    "name": "sentry_set_mode",
    "description": (
        "Change Vision Sentry watcher settings at runtime: arm/disarm the "
        "watcher, adjust sensitivity (scene threshold), event cooldown, or "
        "toggle whether events are pushed into the agent's next turn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "armed": {
                "type": "boolean",
                "description": "Arm (true) or disarm (false) the watcher",
            },
            "scene_threshold": {
                "type": "number",
                "description": "Scene-change threshold 0-1 (lower = more sensitive)",
            },
            "cooldown_secs": {
                "type": "integer",
                "description": "Minimum seconds between stored events",
            },
            "push_alerts": {
                "type": "boolean",
                "description": "Push new events into the agent's next turn",
            },
        },
    },
}
