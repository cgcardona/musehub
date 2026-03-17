"""Musical elicitation schemas for MCP 2025-11-25 form-mode elicitation.

Defines the restricted JSON Schema objects (flat, primitive properties only)
used by MuseHub's elicitation-powered tools. Each schema conforms to the
subset allowed by the MCP spec:
  - Object with primitive (string, number, boolean, enum) properties only.
  - No nested objects or arrays of objects.
  - String arrays allowed only as enum multi-selects.

Musical context for each schema is captured in ``title`` and ``description``
fields so that AI agent clients can generate appropriate UI or prompts.

Usage:
    from musehub.mcp.elicitation import SCHEMAS, build_form_elicitation

    # In a tool executor:
    elicitation_params = build_form_elicitation(
        "compose_preferences",
        "Tell me about the piece you want to compose.",
        request_id="elicit-1",
    )
"""
from __future__ import annotations

import secrets
from typing import Final

from musehub.contracts.json_types import JSONObject, JSONValue

# ── Musical key signatures ────────────────────────────────────────────────────

_KEYS: list[JSONValue] = [
    "C major", "G major", "D major", "A major", "E major", "B major",
    "F# major", "Db major", "Ab major", "Eb major", "Bb major", "F major",
    "A minor", "E minor", "B minor", "F# minor", "C# minor", "G# minor",
    "D# minor", "Bb minor", "F minor", "C minor", "G minor", "D minor",
]

_MOODS: list[JSONValue] = [
    "joyful", "melancholic", "tense", "peaceful", "energetic",
    "mysterious", "romantic", "triumphant", "nostalgic", "ethereal",
]

_GENRES: list[JSONValue] = [
    "ambient", "jazz", "classical", "electronic", "hip-hop",
    "folk", "film score", "lo-fi", "neo-soul", "experimental",
]

_DAWS: list[JSONValue] = [
    "Logic Pro", "Ableton Live", "FL Studio", "Pro Tools", "Bitwig Studio",
    "Reaper", "GarageBand", "Cubase", "Studio One", "Other",
]

_PLATFORMS: list[JSONValue] = [
    "Spotify", "SoundCloud", "Bandcamp", "YouTube Music", "Apple Music",
    "TIDAL", "Amazon Music", "Deezer",
]

_DAW_CLOUDS: list[JSONValue] = [
    "LANDR", "Splice", "Soundtrap", "BandLab", "Audiotool",
]

_REVIEW_DIMENSIONS: list[JSONValue] = [
    "all", "melodic", "harmonic", "rhythmic", "structural", "dynamic",
]

_REVIEW_DEPTHS: list[JSONValue] = ["quick", "standard", "thorough"]

_TIME_SIGNATURES: list[JSONValue] = [
    "4/4", "3/4", "6/8", "5/4", "7/8", "12/8", "2/4",
]

# ── Schema catalogue ──────────────────────────────────────────────────────────

#: Ready-to-use JSON Schema objects for MuseHub elicitations.
SCHEMAS: Final[dict[str, JSONObject]] = {
    # ── Composition preferences ───────────────────────────────────────────────
    "compose_preferences": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "title": "Key Signature",
                "description": "The tonal center of the piece",
                "enum": _KEYS,
                "default": "C major",
            },
            "tempo_bpm": {
                "type": "number",
                "title": "Tempo (BPM)",
                "description": "Target tempo in beats per minute",
                "minimum": 40,
                "maximum": 300,
                "default": 120,
            },
            "time_signature": {
                "type": "string",
                "title": "Time Signature",
                "description": "Metric feel of the composition",
                "enum": _TIME_SIGNATURES,
                "default": "4/4",
            },
            "mood": {
                "type": "string",
                "title": "Emotional Mood",
                "description": "Primary emotional character you want to evoke",
                "enum": _MOODS,
                "default": "peaceful",
            },
            "genre": {
                "type": "string",
                "title": "Genre / Style",
                "description": "Musical genre or stylistic reference",
                "enum": _GENRES,
                "default": "ambient",
            },
            "reference_artist": {
                "type": "string",
                "title": "Reference Artist",
                "description": "Artist or album whose style to reference (optional)",
                "maxLength": 100,
            },
            "duration_bars": {
                "type": "number",
                "title": "Target Duration (bars)",
                "description": "Approximate number of bars for the piece",
                "minimum": 8,
                "maximum": 512,
                "default": 64,
            },
            "include_modulation": {
                "type": "boolean",
                "title": "Include Key Modulation",
                "description": "Should the piece include a modulation section?",
                "default": False,
            },
        },
        "required": ["key", "tempo_bpm", "mood", "genre"],
    },

    # ── Repo creation preferences ─────────────────────────────────────────────
    "repo_creation": {
        "type": "object",
        "properties": {
            "daw": {
                "type": "string",
                "title": "Primary DAW",
                "description": "Which DAW will you use to create this project?",
                "enum": _DAWS,
                "default": "Logic Pro",
            },
            "primary_genre": {
                "type": "string",
                "title": "Primary Genre",
                "description": "Genre label for discovery and search",
                "enum": _GENRES,
                "default": "ambient",
            },
            "key_signature": {
                "type": "string",
                "title": "Key Signature",
                "description": "Starting key of the project",
                "enum": _KEYS,
                "default": "C major",
            },
            "tempo_bpm": {
                "type": "number",
                "title": "Tempo (BPM)",
                "description": "Starting tempo",
                "minimum": 40,
                "maximum": 300,
                "default": 120,
            },
            "is_collab": {
                "type": "boolean",
                "title": "Open for Collaboration",
                "description": "Will you be inviting collaborators?",
                "default": False,
            },
            "collaborator_handles": {
                "type": "string",
                "title": "Collaborator Handles",
                "description": "Comma-separated MuseHub handles to invite (optional)",
                "maxLength": 500,
            },
            "initial_readme": {
                "type": "string",
                "title": "Project Description",
                "description": "A brief description of what you're building",
                "maxLength": 2000,
            },
        },
        "required": ["daw", "primary_genre"],
    },

    # ── PR review focus ───────────────────────────────────────────────────────
    "pr_review_focus": {
        "type": "object",
        "properties": {
            "dimension_focus": {
                "type": "string",
                "title": "Musical Dimension Focus",
                "description": "Which dimension should the review concentrate on?",
                "enum": _REVIEW_DIMENSIONS,
                "default": "all",
            },
            "review_depth": {
                "type": "string",
                "title": "Review Depth",
                "description": "How thorough should the review be?",
                "enum": _REVIEW_DEPTHS,
                "default": "standard",
            },
            "check_harmonic_tension": {
                "type": "boolean",
                "title": "Check Harmonic Tension",
                "description": "Include analysis of unresolved tension and voice-leading issues?",
                "default": True,
            },
            "check_rhythmic_consistency": {
                "type": "boolean",
                "title": "Check Rhythmic Consistency",
                "description": "Flag tempo drift or inconsistent groove patterns?",
                "default": True,
            },
            "reviewer_note": {
                "type": "string",
                "title": "Reviewer Note",
                "description": "Any specific concerns or guidance for the review (optional)",
                "maxLength": 500,
            },
        },
        "required": ["dimension_focus", "review_depth"],
    },

    # ── Release metadata ──────────────────────────────────────────────────────
    "release_metadata": {
        "type": "object",
        "properties": {
            "tag": {
                "type": "string",
                "title": "Release Tag",
                "description": "Semantic version tag, e.g. v1.0.0",
                "pattern": r"^v?\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?$",
                "minLength": 2,
                "maxLength": 32,
            },
            "title": {
                "type": "string",
                "title": "Release Title",
                "description": "Short descriptive name for this release",
                "minLength": 2,
                "maxLength": 120,
            },
            "release_notes": {
                "type": "string",
                "title": "Release Notes",
                "description": "Changelog / what's new in this version",
                "maxLength": 4000,
            },
            "is_prerelease": {
                "type": "boolean",
                "title": "Pre-release",
                "description": "Mark as a pre-release (alpha, beta, RC)?",
                "default": False,
            },
            "highlight": {
                "type": "string",
                "title": "Highlight (one sentence)",
                "description": "Single sentence describing the most exciting change",
                "maxLength": 280,
            },
        },
        "required": ["tag", "title"],
    },

    # ── Platform connection ────────────────────────────────────────────────────
    "platform_connect_confirm": {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "title": "Streaming Platform",
                "description": "Which platform to connect",
                "enum": _PLATFORMS,
            },
            "confirm": {
                "type": "boolean",
                "title": "Confirm Connection",
                "description": "I understand this will redirect me to the platform's OAuth page",
                "default": False,
            },
        },
        "required": ["platform", "confirm"],
    },
}

# Expose key lists for use in tool definitions.
AVAILABLE_KEYS: list[JSONValue] = _KEYS
AVAILABLE_MOODS: list[JSONValue] = _MOODS
AVAILABLE_GENRES: list[JSONValue] = _GENRES
AVAILABLE_DAWS: list[JSONValue] = _DAWS
AVAILABLE_PLATFORMS: list[JSONValue] = _PLATFORMS
AVAILABLE_DAW_CLOUDS: list[JSONValue] = _DAW_CLOUDS
AVAILABLE_REVIEW_DIMS: list[JSONValue] = _REVIEW_DIMENSIONS


# ── Builder helpers ───────────────────────────────────────────────────────────


def build_form_elicitation(
    schema_key: str,
    message: str,
    *,
    request_id: str | None = None,
) -> JSONObject:
    """Build a complete ``elicitation/create`` params dict for form mode.

    Args:
        schema_key: Key into :data:`SCHEMAS` (e.g. ``"compose_preferences"``).
        message: Human-readable message to display to the user.
        request_id: Optional JSON-RPC request ID for the elicitation request.
            Auto-generated if not provided.

    Returns:
        Params dict ready to pass to ``sse_request("elicitation/create", ...)``.

    Raises:
        KeyError: If ``schema_key`` is not in :data:`SCHEMAS`.
    """
    schema = SCHEMAS[schema_key]
    return {
        "mode": "form",
        "message": message,
        "requestedSchema": schema,
    }


def build_url_elicitation(
    url: str,
    message: str,
    *,
    elicitation_id: str | None = None,
) -> tuple[JSONObject, str]:
    """Build a complete ``elicitation/create`` params dict for URL mode.

    Also returns the elicitation ID so callers can match it against
    ``notifications/elicitation/complete``.

    Args:
        url: Target URL for out-of-band interaction (must be HTTPS in prod).
        message: Human-readable message shown to the user.
        elicitation_id: Stable identifier. Auto-generated if not provided.

    Returns:
        Tuple of (params_dict, elicitation_id).
    """
    eid = elicitation_id or secrets.token_urlsafe(16)
    params: JSONObject = {
        "mode": "url",
        "message": message,
        "url": url,
        "elicitationId": eid,
    }
    return params, eid


def oauth_connect_url(platform: str, elicitation_id: str, base_url: str = "") -> str:
    """Build the MuseHub URL for a platform OAuth start page.

    Args:
        platform: Platform name (e.g. ``"Spotify"``).
        elicitation_id: Stable elicitation ID embedded as a query param so the
            callback can correlate back to the session.
        base_url: Override base URL (defaults to musehub.app production).

    Returns:
        Fully-qualified URL for the elicitation landing page.
    """
    base = base_url.rstrip("/") or "https://musehub.app"
    slug = platform.lower().replace(" ", "-")
    return f"{base}/musehub/ui/mcp/connect/{slug}?elicitation_id={elicitation_id}"


def daw_cloud_connect_url(service: str, elicitation_id: str, base_url: str = "") -> str:
    """Build the MuseHub URL for a cloud DAW OAuth start page."""
    base = base_url.rstrip("/") or "https://musehub.app"
    slug = service.lower().replace(" ", "-")
    return f"{base}/musehub/ui/mcp/connect/daw/{slug}?elicitation_id={elicitation_id}"
