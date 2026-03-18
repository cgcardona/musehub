"""Canonical type definitions for JSON data and music-domain dicts.

This module is the **single source of truth for every named data shape** in
MuseHub. Import from here; do not redefine shapes ad hoc.

## When to use which type

Use ``JSONValue`` / ``JSONObject`` only when the shape is genuinely unknown
(e.g. an arbitrary external payload). For every known structure, use the
named TypedDict below.

Do **not** use ``JSONValue`` or ``JSONObject`` in Pydantic ``BaseModel``
fields — Pydantic v2 cannot resolve the recursive forward references and
raises ``RecursionError`` at schema generation time. Use
``musehub.contracts.pydantic_types.PydanticJson`` instead.

## Conversion helpers

- ``json_list(items)`` — coerce a ``list[TypedDict]`` to ``list[JSONValue]``
  at list-insertion boundaries (Python list invariance workaround).
- ``jint(v)`` / ``jfloat(v)`` — safe numeric extraction from ``JSONValue``.
- ``is_note_dict(v)`` — ``TypeGuard`` narrowing from ``JSONValue`` → ``NoteDict``.

## Entity catalog

JSON primitives:
  JSONScalar — str | int | float | bool | None
  JSONValue — recursive JSON value (use sparingly; not in Pydantic)
  JSONObject — dict[str, JSONValue] (use sparingly; not in Pydantic)

MIDI note types:
  NoteDict — a single MIDI note (camelCase + snake_case fields, total=False)
  InternalNoteDict — alias for NoteDict (snake_case storage path)
  CCEventDict — a MIDI Control Change event (cc, beat, value)
  PitchBendDict — a MIDI pitch bend event (beat, value)
  AftertouchDict — a MIDI aftertouch event (beat, value[, pitch])

Composition types:
  SectionDict — a composition section (verse, chorus, bridge…)

Region event map aliases (region_id → list of events):
  RegionNotesMap — dict[str, list[NoteDict]]
  RegionCCMap — dict[str, list[CCEventDict]]
  RegionPitchBendMap — dict[str, list[PitchBendDict]]
  RegionAftertouchMap — dict[str, list[AftertouchDict]]

Protocol introspection aliases:
  EventJsonSchema — dict[str, JSONValue] (single event JSON Schema)
  EventSchemaMap — dict[str, EventJsonSchema] (event_type → JSON Schema)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Required, TypedDict, TypeGuard, overload

from musehub.contracts.midi_types import (
    BeatDuration,
    BeatPosition,
    MidiAftertouchValue,
    MidiCC,
    MidiCCValue,
    MidiChannel,
    MidiPitch,
    MidiPitchBend,
    MidiVelocity,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Generic JSON types — use ONLY when the shape is truly unknown
#
# PYDANTIC COMPATIBILITY RULE
# ───────────────────────────
# JSONValue and JSONObject are *mypy-only* type aliases. JSONValue is
# recursive: it contains ``list["JSONValue"]`` and ``dict[str, "JSONValue"]``
# string forward references. Pydantic v2 must resolve those strings at runtime
# against the importing module's namespace, and fails when they cross module
# boundaries — producing a ``PydanticUserError: not fully defined`` at
# instantiation time.
#
# Rule: **never use JSONValue or JSONObject in a Pydantic BaseModel field.**
#
# Where to use each:
# JSONValue / JSONObject — TypedDicts, dataclasses, function signatures.
# Pure mypy land; Pydantic never sees them.
# dict[str, object] — Pydantic BaseModel fields that must hold opaque
# external JSON. ``object`` is not ``Any`` — mypy requires
# explicit narrowing before use.
# ═══════════════════════════════════════════════════════════════════════════════

JSONScalar = str | int | float | bool | None
"""A JSON leaf value with no recursive structure."""

JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
"""Recursive JSON value — the most precise mypy-safe alternative to ``Any``.

Use this type for JSON payloads whose shape is not statically known.

**Pydantic restriction:** Do NOT use in Pydantic ``BaseModel`` fields.
Use ``PydanticJson`` from ``musehub.contracts.pydantic_types`` instead.

**Mypy usage:** Use ``isinstance`` guards, ``jint()``, ``jfloat()``, or
``is_note_dict()`` to narrow ``JSONValue`` before dereferencing fields.
"""

JSONObject = dict[str, JSONValue]
"""A JSON object with unknown key set.

Use when the object's keys are not statically known.

**Pydantic restriction:** Do NOT use in Pydantic ``BaseModel`` fields.
See ``JSONValue`` for the full explanation.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# MIDI note types
# ═══════════════════════════════════════════════════════════════════════════════


class NoteDict(TypedDict, total=False):
    """A single MIDI note — accepts both camelCase (wire) and snake_case (internal).

    Notes flow through many layers in both naming conventions.
    Using a single dict with all valid keys avoids friction.

    Field ranges (enforced by Pydantic models at system boundaries):
        pitch 0–127 MIDI note number
        velocity 0–127 note-off at 0; audible range 1–127
        channel 0–15 MIDI channel (drums = 9)
        startBeat ≥ 0.0 beat position (fractional allowed)
        durationBeats > 0.0 beat duration (fractional allowed)
    """

    pitch: MidiPitch
    velocity: MidiVelocity
    channel: MidiChannel
    # camelCase (wire format from DAW / to DAW)
    startBeat: BeatPosition # noqa: N815
    durationBeats: BeatDuration # noqa: N815
    noteId: str # noqa: N815
    trackId: str # noqa: N815
    regionId: str # noqa: N815
    # snake_case (internal storage after normalization)
    start_beat: BeatPosition
    duration_beats: BeatDuration
    note_id: str
    track_id: str
    region_id: str
    # drum renderer layer tag (core, timekeepers, fills, ghost_layer, …)
    layer: str


InternalNoteDict = NoteDict


# ═══════════════════════════════════════════════════════════════════════════════
# MIDI expression event types
# ═══════════════════════════════════════════════════════════════════════════════


class CCEventDict(TypedDict):
    """A single MIDI Control Change event.

    Field ranges:
        cc 0–127 controller number
        beat ≥ 0.0 beat position (fractional allowed)
        value 0–127 controller value
    """

    cc: MidiCC
    beat: BeatPosition
    value: MidiCCValue


class PitchBendDict(TypedDict):
    """A single MIDI pitch bend event.

    Field ranges:
        beat ≥ 0.0 beat position (fractional allowed)
        value −8192–8191 14-bit signed; 0 = centre, ±8192 = full deflection
    """

    beat: BeatPosition
    value: MidiPitchBend


class AftertouchDict(TypedDict, total=False):
    """A MIDI aftertouch event (channel pressure or poly key pressure).

    ``beat`` and ``value`` are always present.
    ``pitch`` is present only for polyphonic (per-key) aftertouch.

    Field ranges:
        beat ≥ 0.0 beat position (fractional allowed)
        value 0–127 pressure value
        pitch 0–127 note number (poly aftertouch only)
    """

    beat: Required[BeatPosition]
    value: Required[MidiAftertouchValue]
    pitch: MidiPitch


# ═══════════════════════════════════════════════════════════════════════════════
# Composition section types
# ═══════════════════════════════════════════════════════════════════════════════


class SectionDict(TypedDict, total=False):
    """A composition section — verse, chorus, bridge, etc.

    ``name``, ``start_beat``, and ``length_beats`` are always present;
    ``description`` and ``per_track_description`` are added by the
    section planner but omitted in some internal paths.
    """

    name: str
    start_beat: float
    length_beats: float
    description: str
    per_track_description: dict[str, str]


# ═══════════════════════════════════════════════════════════════════════════════
# Region event map aliases
#
# These replace the repeated pattern ``dict[str, list[XxxDict]]`` across the
# analysis and export layers. The key is always a region_id string; the value
# is the ordered list of events for that region.
# ═══════════════════════════════════════════════════════════════════════════════

RegionNotesMap = dict[str, list[NoteDict]]
"""Maps region_id → ordered list of MIDI notes for that region."""

RegionCCMap = dict[str, list[CCEventDict]]
"""Maps region_id → ordered list of MIDI CC events for that region."""

RegionPitchBendMap = dict[str, list[PitchBendDict]]
"""Maps region_id → ordered list of MIDI pitch bend events for that region."""

RegionAftertouchMap = dict[str, list[AftertouchDict]]
"""Maps region_id → ordered list of MIDI aftertouch events for that region."""


# ═══════════════════════════════════════════════════════════════════════════════
# Protocol introspection types
#
# Named aliases for the multi-dimensional collections returned by the protocol
# endpoints. Using explicit names instead of raw dict/list literals makes the
# contract between the endpoint, its response model, and callers self-evident.
# ═══════════════════════════════════════════════════════════════════════════════

EventJsonSchema = dict[str, JSONValue]
"""JSON Schema dict for a single event type, as produced by Pydantic's model_json_schema()."""

EventSchemaMap = dict[str, EventJsonSchema]
"""Maps event_type → its JSON Schema. Returned by the protocol /events.json endpoint."""


# ═══════════════════════════════════════════════════════════════════════════════
# TypeGuard narrowing helpers
#
# These live here because they narrow JSONValue / dicts-from-JSON into the
# music-domain TypedDicts defined above. Callers use them in list
# comprehensions to avoid cast() at the site where JSON is parsed.
# ═══════════════════════════════════════════════════════════════════════════════


def is_note_dict(v: JSONValue) -> TypeGuard[NoteDict]:
    """Narrow a ``JSONValue`` to ``NoteDict``.

    ``NoteDict`` is ``total=False`` — every field is optional — so any ``dict``
    that arrives from a trusted internal source (StateStore, SSE wire) can be
    safely treated as ``NoteDict`` once we confirm it is a dict.

    Use in list comprehensions to filter a ``list[JSONValue]`` into
    ``list[NoteDict]`` without ``cast()``::

        notes = [n for n in raw_list if is_note_dict(n)]
    """
    return isinstance(v, dict)


def jfloat(v: JSONValue, default: float = 0.0) -> float:
    """Safely extract a ``float`` from a ``JSONValue``.

    Returns *default* when *v* is not numeric::

        beat = jfloat(event.get("beat"))          # 0.0 if key absent or non-numeric
        value = jfloat(event.get("value"), 0.5)   # custom default
    """
    return float(v) if isinstance(v, (int, float)) else default


def jint(v: JSONValue, default: int = 0) -> int:
    """Safely extract an ``int`` from a ``JSONValue``.

    Returns *default* when *v* is not numeric::

        cc = jint(event.get("cc"))          # 0 if absent
        vel = jint(note.get("velocity"))    # 0 if absent
    """
    return int(v) if isinstance(v, (int, float)) else default


# ─── List coercion helper ──────────────────────────────────────────────────────
#
# Python lists are invariant and TypedDicts are not subtypes of
# ``dict[str, JSONValue]`` in mypy's type system even when all their value
# types are JSONValue-compatible. The principled solution (no ``cast()``, no
# per-call ``type: ignore``) is ``@overload`` declarations: enumerate every
# domain TypedDict explicitly so call sites are validated precisely. The
# single ``type: ignore[arg-type]`` lives only inside the implementation body
# — it is the designated coercion boundary for the whole codebase.
#
# To add a new TypedDict overload: add one ``@overload`` line here.


@overload
def json_list(items: Iterable[NoteDict]) -> list[JSONValue]: ...
@overload
def json_list(items: Iterable[CCEventDict]) -> list[JSONValue]: ...
@overload
def json_list(items: Iterable[PitchBendDict]) -> list[JSONValue]: ...
@overload
def json_list(items: Iterable[dict[str, JSONValue]]) -> list[JSONValue]: ...


def json_list(items: Iterable[object]) -> list[JSONValue]:
    """Coerce an iterable of music-domain TypedDicts to ``list[JSONValue]``.

    This is the **single designated list-coercion boundary** in the codebase.
    Each overload is typed precisely for a specific domain dict so call sites
    are statically verified without needing ``cast()`` or ``type: ignore``::

        params["notes"] = json_list(result.notes)       # list[NoteDict]
        params["cc_events"] = json_list(result.cc_events)  # list[CCEventDict]

    The implementation uses ``Iterable[object]`` so mypy validates call sites
    against the overloads, not the body. The ``type: ignore[arg-type]`` below
    is intentional: mypy cannot prove TypedDict ⊆ dict[str, JSONValue] due to
    dict invariance. This is the ONE place where that coercion is accepted.
    """
    result: list[JSONValue] = []
    for item in items:
        result.append(item)  # type: ignore[arg-type]
    return result
