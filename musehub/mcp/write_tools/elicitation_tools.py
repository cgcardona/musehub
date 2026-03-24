"""Elicitation-powered tool executors for MCP 2025-11-25.

These tools use ``ToolCallContext.elicit_form()`` and ``elicit_url()`` to
collect structured input from users mid-tool-call. They require an active
session (``Mcp-Session-Id``) and a client that has declared elicitation
capability. When running without a session they degrade gracefully.

Tools in this module:

  musehub_create_with_preferences  (formerly musehub_compose_with_preferences)
    Form-mode: collects key, tempo, mood, genre, then generates a full
    composition plan (chord progressions, structure, tempo map) as a Muse
    project scaffold. Currently implements the MIDI domain workflow.

  musehub_review_pr_interactive
    Form-mode: collects dimension focus and review depth before running a
    deep musical divergence analysis of the PR.

  musehub_connect_streaming_platform
    URL-mode: OAuth-connects a streaming platform (Spotify, SoundCloud, etc.)
    for agent-triggered release distribution.

  musehub_connect_daw_cloud
    URL-mode: OAuth-connects a cloud DAW service (LANDR, Splice, etc.) to
    enable cloud renders and mastering jobs.

  musehub_create_release_interactive
    Chained: form-mode collects release metadata, URL-mode optionally connects
    streaming platforms, then creates the release.
"""
from __future__ import annotations


import logging
from typing import TYPE_CHECKING

from musehub.contracts.json_types import JSONValue
from musehub.mcp.elicitation import (
    SCHEMAS,
    AVAILABLE_PLATFORMS,
    AVAILABLE_DAW_CLOUDS,
    oauth_connect_url,
    daw_cloud_connect_url,
)
from musehub.services.musehub_mcp_executor import MusehubToolResult, _check_db_available

if TYPE_CHECKING:
    from musehub.mcp.context import ToolCallContext

logger = logging.getLogger(__name__)


# ── Composition with preferences ─────────────────────────────────────────────


async def execute_compose_with_preferences(
    repo_id: str | None,
    *,
    preferences: dict[str, JSONValue] | None = None,
    ctx: "ToolCallContext",
) -> MusehubToolResult:
    """Compose a musical piece, optionally eliciting preferences via MCP.

    Bypass path (no session needed): pass ``preferences`` directly to skip
    elicitation and receive a composition plan immediately.  Missing fields
    fall back to sensible defaults.

    Elicitation path (session required): when ``preferences`` is omitted and
    an active MCP session exists, a form is presented to collect preferences
    interactively.

    No-session, no-preferences path: returns a structured guide listing every
    available field so the caller can populate ``preferences`` and call again.

    Args:
        repo_id: Optional target repository for the composition scaffold.
        preferences: Pre-filled preference dict (bypasses elicitation).
        ctx: Tool call context (session required for elicitation).
    """
    # ── Bypass: preferences provided directly ─────────────────────────────────
    if preferences is not None:
        key = str(preferences.get("key_signature") or preferences.get("key") or "C major")
        _tempo = preferences.get("tempo_bpm", 120)
        tempo = int(_tempo) if isinstance(_tempo, (int, float)) else 120
        time_sig = str(preferences.get("time_signature") or "4/4")
        mood = str(preferences.get("mood") or "peaceful")
        genre = str(preferences.get("genre") or "ambient")
        reference = str(preferences.get("reference_artist") or "")
        _duration = preferences.get("duration_bars", 64)
        duration = int(_duration) if isinstance(_duration, (int, float)) else 64
        modulate = bool(preferences.get("include_modulation", False))
        plan = _build_composition_plan(
            key=key, tempo=tempo, time_sig=time_sig, mood=mood, genre=genre,
            reference=reference, duration_bars=duration, modulate=modulate,
        )
        if repo_id:
            plan["repo_id"] = repo_id
            plan["scaffold_hint"] = (
                f"Create a commit in repo {repo_id} with a 'composition.json' file "
                "containing the above plan. Use musehub_create_issue to track each "
                "section as a task."
            )
        return MusehubToolResult(ok=True, data=plan)

    # ── No session and no preferences: return field guide ─────────────────────
    if not ctx.has_session:
        return MusehubToolResult(
            ok=True,
            data={
                "mode": "schema_guide",
                "message": (
                    "No active MCP session — pass 'preferences' directly to bypass elicitation. "
                    "Call musehub_create_with_preferences(preferences={...}) with the fields below."
                ),
                "fields": {
                    "key_signature": {"type": "string", "example": "C major", "options": [
                        "C major", "G major", "D major", "A major", "E major",
                        "F major", "Bb major", "Eb major",
                        "A minor", "E minor", "D minor", "G minor",
                    ]},
                    "tempo_bpm": {"type": "integer", "example": 120, "range": "40–240"},
                    "time_signature": {"type": "string", "example": "4/4", "options": ["4/4", "3/4", "6/8", "5/4"]},
                    "mood": {"type": "string", "example": "peaceful", "options": [
                        "joyful", "melancholic", "tense", "peaceful", "energetic",
                        "mysterious", "romantic", "triumphant", "nostalgic", "ethereal",
                    ]},
                    "genre": {"type": "string", "example": "jazz", "options": [
                        "ambient", "jazz", "classical", "electronic", "hip-hop",
                        "folk", "film score", "pop", "r&b", "lo-fi",
                    ]},
                    "reference_artist": {"type": "string", "example": "Bill Evans"},
                    "duration_bars": {"type": "integer", "example": 64, "range": "8–256"},
                    "include_modulation": {"type": "boolean", "example": False},
                },
            },
        )

    # ── Elicitation path: active session ──────────────────────────────────────
    await ctx.progress("compose", 0, 4, "Requesting composition preferences from user…")

    prefs = await ctx.elicit_form(
        SCHEMAS["compose_preferences"],
        message=(
            "Let's build your composition! Tell me about the piece you want to create. "
            "These preferences will shape the chord progressions, structure, and feel."
        ),
    )

    if prefs is None:
        return MusehubToolResult(
            ok=False,
            error_code="elicitation_declined",
            error_message="User declined or cancelled the composition preferences form.",
        )

    await ctx.progress("compose", 1, 4, "Generating harmonic framework…")

    key = str(prefs.get("key", "C major"))
    _tempo = prefs.get("tempo_bpm", 120)
    tempo = int(_tempo) if isinstance(_tempo, (int, float)) else 120
    time_sig = str(prefs.get("time_signature", "4/4"))
    mood = str(prefs.get("mood", "peaceful"))
    genre = str(prefs.get("genre", "ambient"))
    reference = str(prefs.get("reference_artist", ""))
    _duration = prefs.get("duration_bars", 64)
    duration = int(_duration) if isinstance(_duration, (int, float)) else 64
    modulate = bool(prefs.get("include_modulation", False))

    plan = _build_composition_plan(
        key=key,
        tempo=tempo,
        time_sig=time_sig,
        mood=mood,
        genre=genre,
        reference=reference,
        duration_bars=duration,
        modulate=modulate,
    )

    await ctx.progress("compose", 2, 4, "Designing section structure…")

    if repo_id:
        plan["repo_id"] = repo_id
        plan["scaffold_hint"] = (
            f"Create a commit in repo {repo_id} with a 'composition.json' file "
            f"containing the above plan. Use musehub_create_issue to track each "
            f"section as a task."
        )

    await ctx.progress("compose", 4, 4, "Composition plan ready.")

    return MusehubToolResult(ok=True, data=plan)


def _build_composition_plan(
    *,
    key: str,
    tempo: int,
    time_sig: str,
    mood: str,
    genre: str,
    reference: str,
    duration_bars: int,
    modulate: bool,
) -> dict[str, JSONValue]:
    """Generate a structured composition plan from user preferences."""
    # Key → relative minor / parallel minor / subdominant / dominant
    _chords_by_key: dict[str, list[JSONValue]] = {
        "C major": ["Cmaj7", "Am7", "Fmaj7", "G7"],
        "G major": ["Gmaj7", "Em7", "Cmaj7", "D7"],
        "D major": ["Dmaj7", "Bm7", "Gmaj7", "A7"],
        "A major": ["Amaj7", "F#m7", "Dmaj7", "E7"],
        "E major": ["Emaj7", "C#m7", "Amaj7", "B7"],
        "F major": ["Fmaj7", "Dm7", "Bbmaj7", "C7"],
        "Bb major": ["Bbmaj7", "Gm7", "Ebmaj7", "F7"],
        "Eb major": ["Ebmaj7", "Cm7", "Abmaj7", "Bb7"],
        "A minor": ["Am7", "Fmaj7", "G7", "Em7b5"],
        "E minor": ["Em7", "Cmaj7", "D7", "Bm7b5"],
        "D minor": ["Dm7", "Bbmaj7", "C7", "Am7b5"],
        "G minor": ["Gm7", "Ebmaj7", "F7", "Dm7b5"],
    }
    chords: list[JSONValue] = _chords_by_key.get(key, ["Imaj7", "vim7", "IVmaj7", "V7"])

    # Mood → harmonic tension profile
    tension_map: dict[str, str] = {
        "joyful": "consonant — favour I, IV, V; avoid diminished",
        "melancholic": "suspended — favour vi, ii, bVII; resolve gently",
        "tense": "dissonant — favour #IVdim, bII7; delay resolution",
        "peaceful": "open — favour Iadd9, IVmaj9; long sustain",
        "energetic": "driving — power chords, fast harmonic rhythm (2 bars)",
        "mysterious": "modal — borrow from Dorian / Phrygian; tritone substitutions",
        "romantic": "lush — Imaj9, VImaj7, ii7, V13; rich voicings",
        "triumphant": "epic — I, V/V, bVII, I; orchestral swell",
        "nostalgic": "bittersweet — I, vi, IV, V with added 9ths",
        "ethereal": "ambient — suspended 2nds, no clear root; wash of colour",
    }
    tension_profile = tension_map.get(mood, "balanced — standard diatonic motion")

    # Genre → texture hint
    texture_map: dict[str, str] = {
        "ambient": "slow harmonic rhythm, long reverb tails, minimal percussion",
        "jazz": "walking bass, shell voicings (3rd+7th), improvised melody",
        "classical": "counterpoint, voice-leading priority, no percussion",
        "electronic": "side-chain compression, synth pads, 808 bass",
        "hip-hop": "boom-bap drums, sample chops, 8-bar loops",
        "folk": "acoustic guitar strums, simple melody, lyrical phrasing",
        "film score": "orchestral strings, ostinato, dynamic swells",
        "lo-fi": "vinyl crackle, detuned piano, laid-back swing",
        "neo-soul": "Rhodes piano, syncopated bass, lush background vocals",
        "experimental": "atonal passages, prepared piano, field recordings",
    }
    texture = texture_map.get(genre, "balanced — choose instrumentation freely")

    # Structure (bars allocation)
    sections: list[JSONValue] = []
    remaining = duration_bars
    parts = [
        ("intro", max(4, duration_bars // 8)),
        ("verse_a", max(8, duration_bars // 4)),
        ("chorus", max(8, duration_bars // 4)),
        ("verse_b", max(8, duration_bars // 4)),
        ("chorus_2", max(8, duration_bars // 4)),
    ]
    if modulate:
        parts.append(("bridge_modulation", 8))
        parts.append(("chorus_final", max(8, duration_bars // 4)))
    parts.append(("outro", max(4, duration_bars // 8)))

    for section_name, section_bars in parts:
        sections.append({"name": section_name, "bars": section_bars, "chords": chords})
        remaining -= section_bars
        if remaining <= 0:
            break

    intro_bars = parts[0][1]
    return {
        "composition_plan": {
            "key": key,
            "tempo_bpm": tempo,
            "time_signature": time_sig,
            "mood": mood,
            "genre": genre,
            "reference_artist": reference or None,
            "duration_bars": duration_bars,
            "modulation": modulate,
            "primary_chords": chords,
            "harmonic_tension_profile": tension_profile,
            "texture_guidance": texture,
            "sections": sections,
            "workflow": [
                "1. Create a new Muse project with these settings.",
                f"2. Start with a {intro_bars}-bar intro using {chords[0]} → {chords[2]}.",
                "3. Build each section in order; use musehub_create_issue per section.",
                "4. Commit after each section: 'feat: add [section] in [key]'.",
                "5. Open a PR for review once the full structure is in place.",
            ],
        }
    }


# ── Interactive PR review ─────────────────────────────────────────────────────


async def execute_review_pr_interactive(
    repo_id: str,
    pr_id: str,
    *,
    dimension: str | None = None,
    depth: str | None = None,
    ctx: "ToolCallContext",
) -> MusehubToolResult:
    """Review a PR interactively by eliciting the reviewer's focus and depth.

    Bypass path (no session needed): supply ``dimension`` and ``depth`` directly
    to run the divergence analysis without any elicitation round-trip.

    Elicitation path (session required): when bypass params are omitted and an
    active session exists, a form collects dimension focus, review depth, and
    optional reviewer notes.

    Collects: dimension focus (melodic / harmonic / rhythmic / structural /
    dynamic / all), review depth (quick / standard / thorough).

    Args:
        repo_id: Repository ID containing the PR.
        pr_id: Pull request ID to review.
        dimension: Bypass param — one of: melodic, harmonic, rhythmic, structural, dynamic, all.
        depth: Bypass param — one of: quick, standard, thorough.
        ctx: Tool call context (session required only when bypass params are absent).
    """
    check_harmonic = True
    check_rhythmic = True
    note = ""

    # ── Bypass: dimension + depth provided directly ───────────────────────────
    if dimension is not None or depth is not None:
        dimension = dimension or "all"
        depth = depth or "standard"
    elif not ctx.has_session:
        # No session and no bypass params — return actionable guide.
        return MusehubToolResult(
            ok=True,
            data={
                "mode": "schema_guide",
                "message": (
                    "No active MCP session. Pass dimension and depth to bypass elicitation: "
                    "musehub_review_pr_interactive(repo_id=..., pr_id=..., dimension='all', depth='standard')"
                ),
                "dimension_options": ["melodic", "harmonic", "rhythmic", "structural", "dynamic", "all"],
                "depth_options": ["quick", "standard", "thorough"],
            },
        )
    else:
        # ── Elicitation path: active session ──────────────────────────────────
        prefs = await ctx.elicit_form(
            SCHEMAS["pr_review_focus"],
            message=(
                f"I'll review PR {pr_id[:8]}. How would you like me to focus the review? "
                "Choose a musical dimension and depth level."
            ),
        )

        if prefs is None:
            return MusehubToolResult(
                ok=False,
                error_code="elicitation_declined",
                error_message="User declined the PR review focus form.",
            )

        dimension = str(prefs.get("dimension_focus", "all"))
        depth = str(prefs.get("review_depth", "standard"))
        check_harmonic = bool(prefs.get("check_harmonic_tension", True))
        check_rhythmic = bool(prefs.get("check_rhythmic_consistency", True))
        note = str(prefs.get("reviewer_note", ""))

    await ctx.progress("review", 0, 3, f"Analysing PR {pr_id[:8]}… ({dimension} / {depth})")

    # Run the divergence analysis via the existing executor.
    from musehub.services.musehub_mcp_executor import _check_db_available
    from musehub.db.database import AsyncSessionLocal
    from musehub.services import musehub_pull_requests, musehub_divergence

    db_ok = _check_db_available()
    if db_ok is not None:
        return MusehubToolResult(
            ok=False,
            error_code="db_unavailable",
            error_message="Database unavailable.",
        )

    async with AsyncSessionLocal() as db:
        pr = await musehub_pull_requests.get_pr(db, repo_id, pr_id)
        if pr is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"PR {pr_id} not found in repo {repo_id}.",
            )

        await ctx.progress("review", 1, 3, "Computing branch divergence…")

        try:
            div_result = await musehub_divergence.compute_hub_divergence(
                db, repo_id=repo_id, branch_a=pr.from_branch, branch_b=pr.to_branch
            )
        except ValueError as e:
            div_result = None
            div_error = str(e)

    await ctx.progress("review", 2, 3, "Building review report…")

    review: dict[str, JSONValue] = {
        "pr_id": pr_id,
        "repo_id": repo_id,
        "from_branch": pr.from_branch,
        "to_branch": pr.to_branch,
        "focus_dimension": dimension,
        "depth": depth,
        "reviewer_note": note or None,
    }

    if div_result:
        dims: list[JSONValue] = [
            {
                "dimension": d.dimension,
                "score": d.score,
                "level": d.level.value,
                "description": d.description,
            }
            for d in div_result.dimensions
            if dimension == "all" or d.dimension == dimension
        ]
        review["overall_score"] = div_result.overall_score
        review["common_ancestor"] = div_result.common_ancestor
        review["dimensions"] = dims

        findings: list[str] = []
        for d in div_result.dimensions:
            if d.score > 0.7 and (dimension == "all" or d.dimension == dimension):
                findings.append(
                    f"⚠️  HIGH {d.dimension} divergence ({d.score:.0%}): {d.description}"
                )
            elif d.score > 0.4 and depth == "thorough":
                findings.append(
                    f"ℹ️  Moderate {d.dimension} divergence ({d.score:.0%}): {d.description}"
                )
        if check_harmonic and div_result.overall_score > 0.5:
            findings.append(
                "🎵 Harmonic tension check: significant harmonic changes detected — "
                "verify voice-leading and resolution in the bridge/chorus."
            )
        if check_rhythmic:
            rhythmic = next((d for d in div_result.dimensions if d.dimension == "rhythmic"), None)
            if rhythmic and rhythmic.score > 0.3:
                findings.append(
                    f"🥁 Rhythmic consistency: score {rhythmic.score:.0%} — "
                    "check for tempo drift or conflicting groove patterns."
                )
        review["findings"] = list(findings) if findings else ["No significant issues detected."]
        review["recommendation"] = (
            "APPROVE" if div_result.overall_score < 0.3
            else "REQUEST_CHANGES" if div_result.overall_score > 0.6
            else "COMMENT"
        )
    else:
        review["divergence_error"] = div_error if "div_error" in dir() else "unknown"
        review["recommendation"] = "COMMENT"
        review["findings"] = ["Could not compute divergence — check that both branches have commits."]

    await ctx.progress("review", 3, 3, "Review complete.")
    return MusehubToolResult(ok=True, data=review)


# ── Connect streaming platform ────────────────────────────────────────────────


async def execute_connect_streaming_platform(
    platform: str | None,
    repo_id: str | None,
    *,
    ctx: "ToolCallContext",
) -> MusehubToolResult:
    """Connect a streaming platform account via URL-mode elicitation (OAuth).

    Directs the user to a MuseHub OAuth start page for the chosen platform.
    Once the OAuth flow completes, the agent can use the connection to
    distribute Muse releases directly to the platform.

    Supported platforms: Spotify, SoundCloud, Bandcamp, YouTube Music,
    Apple Music, TIDAL, Amazon Music, Deezer.

    Args:
        platform: Target platform name (optional; elicited if not provided).
        repo_id: Optional repository context for release distribution.
        ctx: Tool call context (must have active session for URL elicitation).
    """
    # ── Bypass: platform known + no session → return OAuth URL for manual use ──
    if platform and platform in AVAILABLE_PLATFORMS and not ctx.has_session:
        import secrets as _secrets
        elicitation_id = _secrets.token_urlsafe(16)
        connect_url = oauth_connect_url(platform, elicitation_id)
        return MusehubToolResult(
            ok=True,
            data={
                "platform": platform,
                "status": "pending_oauth",
                "oauth_url": connect_url,
                "elicitation_id": elicitation_id,
                "message": (
                    f"Open this URL to connect {platform} to MuseHub. "
                    "No active MCP session detected — manual browser navigation required."
                ),
            },
        )

    if not ctx.has_session:
        return MusehubToolResult(
            ok=True,
            data={
                "mode": "schema_guide",
                "message": (
                    "No active MCP session. Pass platform directly to get an OAuth URL: "
                    "musehub_connect_streaming_platform(platform='Spotify')"
                ),
                "platform_options": AVAILABLE_PLATFORMS,
            },
        )

    # If platform not supplied as argument, elicit it.
    if not platform or platform not in AVAILABLE_PLATFORMS:
        prefs = await ctx.elicit_form(
            SCHEMAS["platform_connect_confirm"],
            message=(
                "Which streaming platform would you like to connect? "
                "I'll redirect you to their OAuth page to authorise MuseHub."
            ),
        )
        if prefs is None:
            return MusehubToolResult(
                ok=False,
                error_code="elicitation_declined",
                error_message="User declined the platform selection form.",
            )
        platform = str(prefs.get("platform", ""))
        confirmed = bool(prefs.get("confirm", False))
        if not confirmed:
            return MusehubToolResult(
                ok=False,
                error_code="not_confirmed",
                error_message="User did not confirm the platform connection.",
            )

    import secrets
    elicitation_id = secrets.token_urlsafe(16)
    connect_url = oauth_connect_url(platform, elicitation_id)

    accepted = await ctx.elicit_url(
        connect_url,
        message=(
            f"To connect {platform}, please authorise MuseHub on the {platform} website. "
            f"Your browser will open to the MuseHub → {platform} OAuth page."
        ),
        elicitation_id=elicitation_id,
    )

    if not accepted:
        return MusehubToolResult(
            ok=False,
            error_code="elicitation_declined",
            error_message=f"User declined or cancelled the {platform} OAuth flow.",
        )

    return MusehubToolResult(
        ok=True,
        data={
            "platform": platform,
            "status": "connected",
            "elicitation_id": elicitation_id,
            "message": (
                f"{platform} connection initiated. Once the OAuth flow completes in your "
                f"browser, you can use musehub_create_release_interactive to distribute "
                f"releases to {platform}."
            ),
            "next_steps": [
                f"Call musehub_create_release_interactive with repo_id={repo_id or '<repo_id>'} "
                f"to publish your next release to {platform}.",
            ],
        },
    )


# ── Connect cloud DAW ─────────────────────────────────────────────────────────


async def execute_connect_daw_cloud(
    service: str | None,
    *,
    ctx: "ToolCallContext",
) -> MusehubToolResult:
    """Connect a cloud DAW / mastering service via URL-mode elicitation (OAuth).

    Enables agents to trigger cloud renders, stems exports, and mastering jobs
    directly from MuseHub. Supported services: LANDR, Splice, Soundtrap,
    BandLab, Audiotool.

    Args:
        service: Target cloud DAW service name (optional; elicited if absent).
        ctx: Tool call context (must have active session for URL elicitation).
    """
    # ── Bypass: service known + no session → return OAuth URL for manual use ───
    if service and service in AVAILABLE_DAW_CLOUDS and not ctx.has_session:
        import secrets as _secrets
        elicitation_id = _secrets.token_urlsafe(16)
        connect_url = daw_cloud_connect_url(service, elicitation_id)
        return MusehubToolResult(
            ok=True,
            data={
                "service": service,
                "status": "pending_oauth",
                "oauth_url": connect_url,
                "elicitation_id": elicitation_id,
                "capabilities": _daw_capabilities(service),
                "message": (
                    f"Open this URL to connect {service} to MuseHub. "
                    "No active MCP session — manual browser navigation required."
                ),
            },
        )

    if not ctx.has_session:
        return MusehubToolResult(
            ok=True,
            data={
                "mode": "schema_guide",
                "message": (
                    "No active MCP session. Pass service directly to get an OAuth URL: "
                    "musehub_connect_daw_cloud(service='LANDR')"
                ),
                "service_options": AVAILABLE_DAW_CLOUDS,
            },
        )

    if not service or service not in AVAILABLE_DAW_CLOUDS:
        # Elicit the service choice via a simple form.
        schema: dict[str, JSONValue] = {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "title": "Cloud DAW / Mastering Service",
                    "description": "Which service would you like to connect?",
                    "enum": AVAILABLE_DAW_CLOUDS,
                    "default": "LANDR",
                },
                "confirm": {
                    "type": "boolean",
                    "title": "Confirm Connection",
                    "description": "I understand this will redirect me to the service's OAuth page",
                    "default": False,
                },
            },
            "required": ["service", "confirm"],
        }
        prefs = await ctx.elicit_form(
            schema,
            message=(
                "Which cloud DAW or mastering service would you like to connect? "
                "Once connected, I can trigger renders, exports, and mastering jobs automatically."
            ),
        )
        if prefs is None:
            return MusehubToolResult(
                ok=False,
                error_code="elicitation_declined",
                error_message="User declined the DAW service selection.",
            )
        service = str(prefs.get("service", ""))
        if not bool(prefs.get("confirm", False)):
            return MusehubToolResult(
                ok=False,
                error_code="not_confirmed",
                error_message="User did not confirm the service connection.",
            )

    import secrets
    elicitation_id = secrets.token_urlsafe(16)
    connect_url = daw_cloud_connect_url(service, elicitation_id)

    accepted = await ctx.elicit_url(
        connect_url,
        message=(
            f"Authorise MuseHub to connect with {service}. "
            f"Your browser will open the MuseHub → {service} integration page."
        ),
        elicitation_id=elicitation_id,
    )

    if not accepted:
        return MusehubToolResult(
            ok=False,
            error_code="elicitation_declined",
            error_message=f"User declined the {service} OAuth flow.",
        )

    return MusehubToolResult(
        ok=True,
        data={
            "service": service,
            "status": "connected",
            "elicitation_id": elicitation_id,
            "capabilities": _daw_capabilities(service),
            "message": (
                f"{service} connected! You can now trigger cloud operations "
                f"directly from MuseHub agent workflows."
            ),
        },
    )


def _daw_capabilities(service: str) -> list[JSONValue]:
    caps: dict[str, list[JSONValue]] = {
        "LANDR": ["AI mastering", "stems export", "distribution to 150+ platforms"],
        "Splice": ["sample sync", "project backup", "stem download"],
        "Soundtrap": ["browser-based DAW", "real-time collaboration", "podcast tools"],
        "BandLab": ["free mastering", "social sharing", "version history"],
        "Audiotool": ["browser-based DAW", "sample library", "community publish"],
    }
    return caps.get(service, ["cloud integration"])


# ── Interactive release creation ──────────────────────────────────────────────


async def execute_create_release_interactive(
    repo_id: str,
    *,
    tag: str | None = None,
    title: str | None = None,
    notes: str | None = None,
    ctx: "ToolCallContext",
) -> MusehubToolResult:
    """Create a release interactively or directly via bypass params.

    Bypass path (no session needed): supply ``tag`` (required), plus optional
    ``title`` and ``notes`` to create the release without any elicitation.

    Elicitation path (session required): when bypass params are omitted and an
    active MCP session exists, a form collects tag, title, release notes, and
    pre-release flag, followed by an optional Spotify OAuth URL prompt.

    No-session, no-params path: returns a schema guide listing every field.

    Args:
        repo_id: Repository to tag the release against.
        tag: Bypass param — semantic version tag (e.g. "v1.2.0").
        title: Bypass param — human-readable release title.
        notes: Bypass param — release notes / changelog body.
        ctx: Tool call context (session required only when bypass params absent).
    """
    highlight = ""

    # ── Bypass: tag provided directly ────────────────────────────────────────
    if tag is not None:
        resolved_title = title or tag
        release_notes = notes or ""
        await ctx.progress("release", 0, 2, f"Creating release {tag}…")

        from musehub.mcp.write_tools.releases import execute_create_release

        result = await execute_create_release(
            repo_id=repo_id,
            tag=tag,
            title=resolved_title,
            body=release_notes,
            commit_id=None,
            channel="stable",
            actor=ctx.user_id or "",
        )

        await ctx.progress("release", 2, 2, "Done.")

        if not result.ok:
            return result

        release_data = result.data or {}
        return MusehubToolResult(
            ok=True,
            data={
                **release_data,
                "workflow_hint": (
                    "Release published! Call musehub_connect_streaming_platform to "
                    "distribute to Spotify, SoundCloud, Bandcamp, and more."
                ),
            },
        )

    # ── No session and no bypass params: return field guide ──────────────────
    if not ctx.has_session:
        return MusehubToolResult(
            ok=True,
            data={
                "mode": "schema_guide",
                "message": (
                    "No active MCP session. Pass 'tag' to bypass elicitation: "
                    "musehub_create_release_interactive(repo_id=..., tag='v1.0.0', title='...', notes='...')"
                ),
                "fields": {
                    "tag": {"type": "string", "required": True, "example": "v1.0.0"},
                    "title": {"type": "string", "required": False, "example": "First release"},
                    "notes": {"type": "string", "required": False, "example": "Bug fixes and improvements"},
                },
            },
        )

    # ── Elicitation path: active session ──────────────────────────────────────
    await ctx.progress("release", 0, 3, "Collecting release metadata…")

    # Step 1: collect release metadata via form elicitation.
    prefs = await ctx.elicit_form(
        SCHEMAS["release_metadata"],
        message=(
            f"Let's create a release for repo {repo_id}. "
            "Fill in the release details below."
        ),
    )

    if prefs is None:
        return MusehubToolResult(
            ok=False,
            error_code="elicitation_declined",
            error_message="User declined the release metadata form.",
        )

    tag = str(prefs.get("tag", "v1.0.0"))
    resolved_title = str(prefs.get("title", tag))
    release_notes = str(prefs.get("release_notes", ""))
    channel_raw = prefs.get("channel", "stable")
    channel = str(channel_raw) if isinstance(channel_raw, str) else "stable"
    highlight = str(prefs.get("highlight", ""))

    if highlight:
        release_notes = f"**Highlight:** {highlight}\n\n{release_notes}".strip()

    await ctx.progress("release", 1, 3, f"Creating release {tag}…")

    # Create the release using the existing executor.
    from musehub.mcp.write_tools.releases import execute_create_release

    result = await execute_create_release(
        repo_id=repo_id,
        tag=tag,
        title=resolved_title,
        body=release_notes,
        commit_id=None,
        channel=channel,
        actor=ctx.user_id or "",
    )

    if not result.ok:
        return result

    await ctx.progress("release", 2, 3, "Release created. Checking platform connections…")

    # Step 2: offer streaming platform connection (URL elicitation), non-blocking.
    if ctx.has_session and ctx.session and ctx.session.supports_elicitation_url():
        import secrets
        elicitation_id = secrets.token_urlsafe(16)
        spotify_url = oauth_connect_url("Spotify", elicitation_id)

        # Non-blocking: just offer it — tool returns success either way.
        await ctx.elicit_url(
            spotify_url,
            message=(
                "Release created! Would you like to distribute it to Spotify? "
                "Click through to connect your Spotify for Artists account."
            ),
            elicitation_id=elicitation_id,
        )

    release_data = result.data or {}
    release_data["highlight"] = highlight or None

    await ctx.progress("release", 3, 3, "Done.")

    return MusehubToolResult(
        ok=True,
        data={
            **release_data,
            "workflow_hint": (
                "Release published! Call musehub_connect_streaming_platform to "
                "distribute to Spotify, SoundCloud, Bandcamp, and more."
            ),
        },
    )
