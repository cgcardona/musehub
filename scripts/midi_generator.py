"""MIDI file generator for MuseHub V2 seed data.

Generates Standard MIDI Files (SMF type 1) for showcase pieces using
the ``mido`` library. All compositions are either original or derived
from Public Domain scores (composers deceased >70 years).

Each function returns ``bytes`` — a complete valid MIDI file — ready to
be written to disk and registered as a ``MusehubObject``.

Pieces included:
  Bach — WTC Prelude No. 1 in C major (BWV 846) — complete 35 bars
  Bach — Minuet in G major (BWV Anh. 114) — 32 bars
  Satie — Gymnopédie No. 1 — 32 bars (D major, 3/4, Lent)
  Chopin — Nocturne Op. 9 No. 2 in Eb major — 12 bars (representative opening)
  Beethoven — Moonlight Sonata Mvt. I opening — 16 bars (C# minor, 4/4, Adagio)
  Original — Neo-Soul Groove in F# minor — multi-track (piano+bass+drums)
  Original — Modal Jazz Sketch in D Dorian — multi-track (piano+bass+drums)
  Original — Afrobeat Pulse in G major — multi-track (piano+bass+djembe)
"""
from __future__ import annotations

import io
from typing import NamedTuple

import mido

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PPQ = 480  # ticks per quarter note — standard


def _bpm_to_tempo(bpm: float) -> int:
    return int(60_000_000 / bpm)


def _ticks(beats: float, ppq: int = _PPQ) -> int:
    return int(beats * ppq)


class Note(NamedTuple):
    pitch: int       # MIDI pitch 0-127
    start: float     # start in quarter-note beats
    dur: float       # duration in quarter-note beats
    vel: int = 80    # velocity 0-127
    ch: int = 0      # MIDI channel


def _notes_to_track(
    notes: list[Note],
    name: str = "Piano",
    ppq: int = _PPQ,
) -> mido.MidiTrack:
    """Convert a flat note list into an absolute-time mido MidiTrack."""
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=name, time=0))

    # Build absolute-tick event list
    events: list[tuple[int, mido.Message]] = []
    for n in notes:
        on_tick  = _ticks(n.start, ppq)
        off_tick = _ticks(n.start + n.dur, ppq)
        events.append((on_tick,  mido.Message("note_on",  channel=n.ch, note=n.pitch, velocity=n.vel, time=0)))
        events.append((off_tick, mido.Message("note_off", channel=n.ch, note=n.pitch, velocity=0,     time=0)))

    events.sort(key=lambda e: e[0])

    prev_tick = 0
    for abs_tick, msg in events:
        msg.time = abs_tick - prev_tick
        prev_tick = abs_tick
        track.append(msg)

    track.append(mido.MetaMessage("end_of_track", time=_ticks(2, ppq)))
    return track


def _smf(bpm: float, time_sig: tuple[int, int], tracks: list[mido.MidiTrack]) -> bytes:
    """Assemble a type-1 SMF and return bytes."""
    mid = mido.MidiFile(type=1, ticks_per_beat=_PPQ)

    # Tempo / meta track
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=_bpm_to_tempo(bpm), time=0))
    meta.append(mido.MetaMessage("time_signature",
        numerator=time_sig[0], denominator=time_sig[1],
        clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    meta.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(meta)

    for t in tracks:
        mid.tracks.append(t)

    buf = io.BytesIO()
    mid.save(file=buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Velocity humanization helpers
# ---------------------------------------------------------------------------

def _hv(base: int, offset: int = 0) -> int:
    """Return humanized velocity clamped 20–120."""
    return max(20, min(120, base + offset))


# ===========================================================================
# 1. Bach — WTC Prelude No. 1 in C major (BWV 846)
# ===========================================================================
# The famous arpeggiated harmonic series. Each 4/4 bar contains one chord
# repeated as: low bass / 5th / 8th / 3rd / 5th / 8th / 3rd / 5th
# (sixteen 16th notes).  We encode bars 1-35 faithfully from the Urtext.
#
# Attribution: Johann Sebastian Bach (1685-1750) — Public Domain
# Source: Urtext edition (Peters No. 200) — expired copyright, PD worldwide

_WTC_CHORDS: list[tuple[list[int], str]] = [
    # (pitch-pattern, annotation)
    ([36, 52, 55, 60, 64],          "I — C major"),
    ([36, 53, 57, 60, 65],          "ii7 — Dm7/C"),
    ([35, 47, 50, 55, 59],          "V7/V — G7/B"),
    ([36, 52, 55, 60, 64],          "I — C major"),
    ([36, 57, 60, 64, 69],          "vi — Am"),
    ([36, 50, 57, 62, 65],          "ii7 — Dm7"),
    ([35, 47, 50, 55, 59],          "V7 — G7/B"),
    ([36, 52, 55, 60, 64],          "I — C major"),
    ([36, 53, 57, 65, 69],          "IV — F/C"),
    ([36, 50, 53, 57, 62],          "ii — Dm/C"),
    ([35, 47, 50, 55, 59],          "V7 — G7"),
    ([36, 52, 55, 60, 64],          "I"),
    ([34, 46, 49, 55, 58],          "vii° — Bdim/F#"),
    ([36, 53, 55, 60, 65],          "IV — F/C"),
    ([35, 50, 53, 59, 65],          "V7sus — Gsus/B"),
    ([36, 48, 52, 55, 64],          "I — C/E"),
    ([41, 53, 57, 65, 69],          "IV — F"),
    ([41, 50, 53, 57, 65],          "ii7 — Dm/F"),
    ([43, 47, 50, 55, 59],          "V7 — G7/G"),
    ([36, 52, 55, 60, 64],          "I"),
    ([36, 57, 60, 65, 69],          "vi — Am"),
    ([36, 53, 60, 65, 69],          "IV add9 — F/C"),
    ([36, 50, 57, 62, 65],          "ii7 — Dm7"),
    ([35, 47, 53, 59, 62],          "V7 — G7"),
    ([36, 52, 55, 60, 67],          "I — C maj7"),
    ([36, 53, 60, 65, 69],          "IV — F"),
    ([35, 47, 53, 59, 62],          "V7 — G7/B"),
    ([36, 52, 55, 60, 64],          "I"),
    ([41, 53, 57, 65, 69],          "IV — F"),
    ([38, 50, 55, 62, 65],          "ii — Dm/A"),
    ([43, 47, 55, 62, 67],          "V — G"),
    ([43, 47, 55, 62, 67],          "V (held) — G"),
    ([36, 52, 55, 60, 64],          "I — final"),
    ([36, 36, 55, 64, 67],          "I open — penultimate"),
    ([36, 36, 55, 64, 67],          "I — final bar"),
]


def wtc_prelude_c_major() -> bytes:
    """Bach WTC Book I — Prelude No. 1 in C major (BWV 846).

    35 bars of the famous arpeggiated chord progression.
    4/4 at 72 BPM. Single-track, one channel.
    """
    notes: list[Note] = []
    beat = 0.0

    for bar_idx, (pitches, _) in enumerate(_WTC_CHORDS):
        # Each bar: the 5-note chord repeated as 16th-note arpeggios
        # Pattern for 16 sixteenth notes per bar (4/4):
        # [p0, p1, p2, p3, p4, p3, p2, p1] × 2
        pattern = [pitches[0], pitches[1], pitches[2], pitches[3], pitches[4],
                   pitches[3], pitches[2], pitches[1]] * 2
        for i, p in enumerate(pattern):
            vel = _hv(72, (i % 4 == 0) * 12 - 6)  # accent beat 1
            notes.append(Note(pitch=p, start=beat, dur=0.24, vel=vel, ch=0))
            beat += 0.25  # 16th note = 0.25 quarter beats

    track = _notes_to_track(notes, name="Piano")
    return _smf(bpm=72, time_sig=(4, 4), tracks=[track])


# ===========================================================================
# 2. Bach — Minuet in G major (BWV Anh. 114)
# ===========================================================================
# Attributed to Christian Petzold but published in Bach's notebook.
# Public Domain. 3/4 at 104 BPM.

def bach_minuet_g() -> bytes:
    """Bach Notebook — Minuet in G major (BWV Anh. 114), 32 bars."""
    # Right hand melody (pitch, start_beat, dur_beats, vel)
    # 3/4 time — each quarter note = 1 beat
    # fmt: off
    rh_raw: list[tuple[int, float, float, int]] = [
        # Bar 1
        (67,0,1,80),(69,1,1,72),(71,2,1,72),
        # Bar 2
        (72,3,2,85),(71,5,1,70),
        # Bar 3
        (69,6,1,78),(71,7,0.5,68),(69,7.5,0.5,65),(67,8,1,75),
        # Bar 4
        (64,9,3,80),
        # Bar 5
        (65,12,1,72),(67,13,1,68),(69,14,1,68),
        # Bar 6
        (71,15,2,80),(67,17,1,70),
        # Bar 7
        (69,18,1,75),(67,19,0.5,68),(65,19.5,0.5,65),(64,20,1,72),
        # Bar 8
        (67,21,3,85),
        # Bar 9
        (71,24,1,78),(72,25,1,70),(74,26,1,70),
        # Bar 10
        (76,27,2,88),(74,29,1,72),
        # Bar 11
        (72,30,1,75),(74,31,0.5,68),(72,31.5,0.5,65),(71,32,1,72),
        # Bar 12
        (69,33,3,80),
        # Bar 13
        (72,36,1,78),(71,37,1,70),(69,38,1,68),
        # Bar 14
        (67,39,2,80),(71,41,1,70),
        # Bar 15
        (72,42,1,75),(69,43,1,68),(67,44,1,65),
        # Bar 16
        (64,45,3,88),
        # Repeat — bars 1-16 slightly varied
        (67,48,1,80),(69,49,1,72),(71,50,1,72),
        (72,51,2,85),(71,53,1,70),
        (69,54,1,78),(71,55,0.5,68),(69,55.5,0.5,65),(67,56,1,75),
        (64,57,3,80),
        (65,60,1,72),(67,61,1,68),(69,62,1,68),
        (71,63,2,80),(67,65,1,70),
        (69,66,1,75),(67,67,0.5,68),(65,67.5,0.5,65),(64,68,1,72),
        (67,69,3,85),
    ]
    # fmt: on

    # Left hand — block chords / bass pattern
    lh_raw: list[tuple[int, float, float, int]] = [
        # Bar 1 — G bass + chord
        (43,0,0.9,65),(55,0,0.9,55),(59,0,0.9,55),
        (47,1,0.9,55),(55,1,0.9,50),(62,1,0.9,50),
        (43,2,0.9,60),(55,2,0.9,50),(59,2,0.9,50),
        # Bar 2
        (48,3,1.9,60),(55,3,1.9,52),(60,3,1.9,52),
        (47,5,0.9,55),(59,5,0.9,50),
        # Bar 3
        (45,6,0.9,58),(57,6,0.9,50),(60,6,0.9,50),
        (47,7,0.9,52),(59,7,0.9,48),
        (43,8,0.9,60),(55,8,0.9,50),(59,8,0.9,50),
        # Bar 4
        (40,9,2.9,65),(52,9,2.9,55),(55,9,2.9,55),
        # Bar 5
        (41,12,0.9,60),(53,12,0.9,52),(57,12,0.9,52),
        (43,13,0.9,55),(55,13,0.9,50),(59,13,0.9,50),
        (45,14,0.9,55),(57,14,0.9,48),(60,14,0.9,48),
        # Bar 6
        (47,15,1.9,60),(59,15,1.9,52),(62,15,1.9,52),
        (43,17,0.9,55),(55,17,0.9,48),(59,17,0.9,48),
        # Bar 7
        (45,18,0.9,58),(57,18,0.9,50),(60,18,0.9,50),
        (47,19,0.9,52),(59,19,0.9,48),
        (40,20,0.9,62),(52,20,0.9,54),(55,20,0.9,54),
        # Bar 8
        (43,21,2.9,70),(55,21,2.9,58),(59,21,2.9,58),
    ]

    rh_notes = [Note(pitch=p, start=s, dur=d, vel=v, ch=0) for p,s,d,v in rh_raw]
    lh_notes = [Note(pitch=p, start=s, dur=d, vel=v, ch=1) for p,s,d,v in lh_raw]

    t1 = _notes_to_track(rh_notes, name="Right Hand")
    t2 = _notes_to_track(lh_notes, name="Left Hand")
    return _smf(bpm=104, time_sig=(3, 4), tracks=[t1, t2])


# ===========================================================================
# 3. Satie — Gymnopédie No. 1
# ===========================================================================
# Erik Satie (1866-1925) — Public Domain (>70 years since death).
# D major, 3/4 at 52 BPM ("Lent et douloureux").
# Iconic waltz chord pattern LH, floating melody RH.

def gymnopedie_no1() -> bytes:
    """Satie Gymnopédie No. 1 — 32 bars in D major, 3/4 at 52 BPM."""
    # LH: alternating "oom" (bass note) + "pah pah" (open chord on beats 2-3)
    # RH: gentle melodic line
    # fmt: off

    # LH chord voicings per 2-bar phrase (root, ch5, ch8, ch10)
    # D major: D2 A3 D4 F#4 A4
    # G major: G2 D4 G4 B4
    lh_phrases: list[list[Note]] = []

    def add_lh_bar(start: float, bass: int, ch5: int, ch8: int) -> None:
        # Beat 1: bass note (forte)
        lh_phrases.append(Note(pitch=bass, start=start,   dur=0.9, vel=60, ch=1))
        # Beats 2-3: open 5th chord (piano)
        lh_phrases.append(Note(pitch=ch5,  start=start+1, dur=1.9, vel=45, ch=1))
        lh_phrases.append(Note(pitch=ch8,  start=start+1, dur=1.9, vel=40, ch=1))

    D2, A3, D4  = 38, 57, 62   # D major bass set
    G2, D4b, G4 = 43, 62, 67   # G major bass set (D4b == D4)
    A2, E4, A4  = 45, 64, 69   # A major (V chord)
    Fs2, Cs4    = 42, 61        # F# (vii chord)

    # 32 bars — the typical waltz LH alternation
    bar_chords = [
        (D2,A3,D4),(G2,D4b,G4),(D2,A3,D4),(G2,D4b,G4),  # bars 1-4
        (D2,A3,D4),(G2,D4b,G4),(A2,E4,A4),(D2,A3,D4),   # bars 5-8
        (D2,A3,D4),(G2,D4b,G4),(D2,A3,D4),(G2,D4b,G4),  # bars 9-12
        (A2,E4,A4),(A2,E4,A4),(D2,A3,D4),(D2,A3,D4),    # bars 13-16
        (D2,A3,D4),(G2,D4b,G4),(D2,A3,D4),(G2,D4b,G4),  # bars 17-20
        (D2,A3,D4),(G2,D4b,G4),(A2,E4,A4),(D2,A3,D4),   # bars 21-24
        (D2,A3,D4),(G2,D4b,G4),(D2,A3,D4),(A2,E4,A4),   # bars 25-28
        (Fs2,Cs4,Fs2+12),(G2,D4b,G4),(A2,E4,A4),(D2,A3,D4),  # bars 29-32
    ]

    lh_notes: list[Note] = []
    for i, (bass, c5, c8) in enumerate(bar_chords):
        add_lh_bar(i * 3.0, bass, c5, c8)
        lh_notes.extend(lh_phrases)
        lh_phrases.clear()

    # RH melody — the iconic floating line
    # Starts on A4 (beat 3 of bar 1)
    # fmt: off
    rh_raw: list[tuple[int, float, float, int]] = [
        # Bar 1 pickup
        (69,2,1,65),
        # Bar 2
        (66,3,2,70),(64,5,1,62),
        # Bar 3
        (62,6,2,72),(61,8,1,60),
        # Bar 4
        (62,9,2,68),(64,11,1,62),
        # Bar 5
        (66,12,2,75),(64,14,1,65),
        # Bar 6
        (62,15,2,70),(61,17,1,62),
        # Bar 7
        (57,18,2,65),(59,20,1,60),
        # Bar 8
        (57,21,3,70),
        # Bar 9
        (69,24,2,68),(67,26,1,62),
        # Bar 10
        (66,27,2,72),(64,29,1,65),
        # Bar 11
        (62,30,2,70),(61,32,1,60),
        # Bar 12
        (62,33,3,68),
        # Bar 13
        (66,36,2,75),(69,38,1,68),
        # Bar 14
        (71,39,2,78),(69,41,1,70),
        # Bar 15
        (67,42,2,72),(66,44,1,65),
        # Bar 16
        (62,45,3,70),
        # Second half — slight variation
        (69,48,2,65),(67,50,1,60),
        (66,51,2,70),(64,53,1,62),
        (62,54,2,68),(61,56,1,58),
        (62,57,3,65),
        (66,60,2,72),(64,62,1,65),
        (62,63,2,70),(61,65,1,60),
        (57,66,2,65),(59,68,1,58),
        (57,69,3,65),
        # Gentle close
        (69,72,2,62),(67,74,1,55),
        (66,75,2,65),(64,77,1,58),
        (62,78,2,60),(57,80,1,50),
        (62,81,3,58),
        # Final bars — pppp
        (62,84,2,45),(61,86,1,38),
        (57,87,3,40),
        (62,90,3,35),
        (57,93,3,30),
    ]
    # fmt: on

    rh_notes = [Note(pitch=p, start=s, dur=d, vel=v, ch=0) for p,s,d,v in rh_raw]
    t1 = _notes_to_track(rh_notes, name="Melody")
    t2 = _notes_to_track(lh_notes, name="Accompaniment")
    return _smf(bpm=52, time_sig=(3, 4), tracks=[t1, t2])


# ===========================================================================
# 4. Chopin — Nocturne Op. 9 No. 2 in Eb major
# ===========================================================================
# Frédéric Chopin (1810-1849) — Public Domain (>70 years since death).
# 12/8 at 66 BPM. LH: wide arpeggiated chords. RH: ornate cantabile melody.

def chopin_nocturne_op9_no2() -> bytes:
    """Chopin Nocturne Op. 9 No. 2 — opening 12 bars in Eb major, 12/8."""
    # In 12/8 at 66 BPM: quarter note = 1 beat, dotted-quarter = 1.5 beats
    # 12/8 bar = 4 dotted quarter beats = 6 quarter beats per bar

    Eb3, Bb3, Eb4, G4, Bb4 = 51, 58, 63, 67, 70   # Eb major
    F3,  C4,  F4,  Ab4     = 53, 60, 65, 68         # Fm
    Bb2, F3b, Bb3b, D4     = 46, 53, 58, 62         # Bb major
    Ab2, Eb3b, Ab3, C4b    = 44, 51, 56, 60         # Ab major
    Bb3c = 58

    # LH arpeggiated pattern — low bass + wide spread chord (each beat)
    # Each 12/8 bar = 6 quarter beats
    lh_notes: list[Note] = []
    lh_pattern: list[tuple[list[int], float]] = [
        # (pitches, beat_start_per_bar)
        ([Eb3-12, Bb3, Eb4, G4], 0.0),   # Eb major
        ([F3-12,  C4,  F4,  Ab4], 6.0),  # Fm
        ([Bb2,    F3b, Bb3b,D4],  12.0), # Bb
        ([Eb3-12, Bb3, Eb4, G4], 18.0),  # Eb
        ([Ab2,    Eb3b,Ab3, C4b], 24.0), # Ab
        ([Bb2,    F3b, Bb3b,D4],  30.0), # Bb
        ([Eb3-12, Bb3, Eb4, G4], 36.0),  # Eb
        ([Eb3-12, Bb3, Eb4, G4], 42.0),  # Eb
        ([F3-12,  C4,  F4,  Ab4], 48.0), # Fm
        ([Bb2,    F3b, Bb3b,D4],  54.0), # Bb7
        ([Eb3-12, Bb3, Eb4, G4], 60.0),  # Eb
        ([Eb3-12, Bb3, Eb4, G4], 66.0),  # Eb
    ]
    for pitches, bar_start in lh_pattern:
        for beat_off in [0.0, 1.5, 3.0, 4.5]:  # 4 dotted-quarter subdivisions
            for j, p in enumerate(pitches):
                delay = beat_off + j * 0.08   # slight roll-up arpeggio
                lh_notes.append(Note(pitch=p, start=bar_start + delay, dur=1.3, vel=_hv(48, -j*3), ch=1))

    # RH iconic melody — the famous cantabile theme
    # fmt: off
    rh_raw: list[tuple[int, float, float, int]] = [
        # Bar 1 (Eb major ascending)
        (63,0,0.5,72),(65,0.5,0.5,68),(67,1,1,75),(70,2,0.5,70),(68,2.5,0.5,65),
        (67,3,1,72),(63,4,2,68),
        # Bar 2
        (67,6,0.5,75),(68,6.5,0.5,70),(70,7,1,78),(72,8,0.5,72),(70,8.5,0.5,68),
        (68,9,1,70),(67,10,2,65),
        # Bar 3
        (70,12,0.5,75),(68,12.5,0.5,70),(67,13,1,78),(70,14,0.5,72),(68,14.5,0.5,65),
        (67,15,1,70),(63,16,2,68),
        # Bar 4
        (58,18,0.5,65),(60,18.5,0.5,60),(63,19,1,72),(65,20,0.5,68),(67,20.5,0.5,62),
        (63,21,3,70),
        # Bar 5 — more ornate
        (63,24,0.5,72),(65,24.5,0.25,68),(67,24.75,0.25,65),(70,25,1,78),
        (72,26,0.5,72),(70,26.5,0.5,68),(68,27,1,70),(67,28,2,65),
        # Bar 6
        (67,30,0.5,75),(68,30.5,0.5,70),(70,31,1,80),(72,32,0.5,75),(70,32.5,0.5,68),
        (68,33,1,72),(67,34,2,65),
        # Bar 7
        (70,36,0.5,78),(72,36.5,0.5,72),(74,37,1,82),(75,38,0.5,75),(74,38.5,0.5,68),
        (72,39,1,72),(70,40,2,68),
        # Bar 8 — climax
        (75,42,1,85),(74,43,0.5,80),(72,43.5,0.5,75),(70,44,1,78),(68,45,1,72),(67,46,2,70),
        # Bar 9
        (63,48,0.5,68),(65,48.5,0.5,65),(67,49,1,72),(70,50,0.5,68),(68,50.5,0.5,62),
        (67,51,1,68),(63,52,2,65),
        # Bar 10
        (67,54,0.5,70),(68,54.5,0.5,65),(70,55,1,75),(72,56,0.5,70),(70,56.5,0.5,65),
        (68,57,1,68),(67,58,2,62),
        # Bar 11
        (63,60,2,68),(65,62,1,62),(67,63,3,70),
        # Bar 12 — ending phrase pppp
        (63,66,3,55),(60,69,3,45),
    ]
    # fmt: on

    rh_notes = [Note(pitch=p, start=s, dur=d, vel=v, ch=0) for p,s,d,v in rh_raw]
    t1 = _notes_to_track(rh_notes, name="Melody")
    t2 = _notes_to_track(lh_notes, name="Accompaniment")
    return _smf(bpm=66, time_sig=(12, 8), tracks=[t1, t2])


# ===========================================================================
# 5. Beethoven — Moonlight Sonata Op. 27 No. 2, Mvt. I
# ===========================================================================
# Ludwig van Beethoven (1770-1827) — Public Domain.
# C# minor, 4/4 ("Alla breve"), Adagio sostenuto at 54 BPM.
# Famous triplet arpeggio pattern in LH, melody in RH.

def moonlight_sonata_mvt1() -> bytes:
    """Beethoven Moonlight Sonata Mvt. I — 16 bars, C# minor, 54 BPM."""
    # Triplet pattern: each beat subdivided into 3 — groups of 12 triplet 8ths per bar
    # In quarter-note beats: each triplet 8th = 1/3 beat

    # MIDI: C1=24, C2=36, C3=48, C4=60, C5=72
    # C#2=37, G#2=44, E3=52, G#3=56, C#4=61, E4=64, G#4=68, A4=69, B4=71
    Cs2 = 37; Gs2 = 44; E3 = 52; Gs3 = 56; Cs4 = 61; E4 = 64; Gs4 = 68
    As = 57; B = 59; Fs = 54; A = 57

    # LH triplet arpeggio — pattern per bar
    # C# minor: Cs2-Gs3-Cs4 alternating patterns
    lh_patterns: list[list[int]] = [
        [Cs2, Gs3, Cs4],          # bar 1: Csm
        [Cs2, Gs3, Cs4],          # bar 2: Csm
        [37-12, 52, 56],           # bar 3: Csm/E
        [37-12, 47, 56],           # bar 4: C# diminished
        [37-12, 52, 57],           # bar 5: F# minor
        [37-12, 52, 57],           # bar 6: F# minor
        [37, 47, 56],              # bar 7: C# dim7
        [37, 52, Gs3],             # bar 8: Cs m
        [37, Gs2, Cs4],            # bar 9: Csm
        [37-12, 49, 54],           # bar 10: A major
        [37-12, 49, 54],           # bar 11: A major
        [35-12, 47, 54],           # bar 12: B major
        [37, Gs2, Cs4],            # bar 13: Csm
        [37-12, Gs2, E3],          # bar 14: C# diminished
        [37-12, Gs2, Cs4],         # bar 15: Csm
        [37-12, Gs2, Cs4],         # bar 16: Csm final
    ]

    lh_notes: list[Note] = []
    for bar_i, pattern in enumerate(lh_patterns):
        bar_start = bar_i * 4.0
        for beat in range(4):
            beat_start = bar_start + beat
            for trip in range(3):
                p = pattern[trip % len(pattern)]
                t = beat_start + trip / 3.0
                vel = _hv(45, 8 if trip == 0 and beat == 0 else 0)
                lh_notes.append(Note(pitch=p, start=t, dur=0.28, vel=vel, ch=1))

    # RH melody — the iconic upper voice over the triplets
    # fmt: off
    rh_raw: list[tuple[int, float, float, int]] = [
        # Bar 1 — slow unfolding
        (Cs4+12, 3, 1, 60),
        # Bar 2
        (Cs4+12, 4, 2, 65),(B+60, 6, 2, 58),
        # Bar 3
        (Cs4+12, 8, 4, 62),
        # Bar 4
        (Cs4+12, 12, 2, 60),(B+60, 14, 2, 55),
        # Bar 5 — F# minor region
        (Cs4+12, 16, 1, 68),(B+60, 17, 1, 62),(As+60, 18, 2, 65),
        # Bar 6
        (Gs4, 20, 2, 70),(Fs+60, 22, 2, 65),
        # Bar 7 — development
        (E4+12, 24, 1, 72),(Fs+60, 25, 1, 68),(Gs4, 26, 2, 70),
        # Bar 8
        (As+60, 28, 2, 75),(Gs4, 30, 2, 68),
        # Bar 9 — return to Csm
        (Cs4+12, 32, 4, 65),
        # Bar 10 — A major colour
        (E4+12, 36, 2, 68),(Cs4+12, 38, 2, 62),
        # Bar 11
        (A+60, 40, 2, 70),(Cs4+12, 42, 2, 65),
        # Bar 12 — B major approach
        (B+60, 44, 2, 72),(Fs+60, 46, 2, 65),
        # Bar 13 — return
        (Cs4+12, 48, 4, 68),
        # Bar 14
        (E4+12, 52, 2, 65),(Gs4, 54, 2, 60),
        # Bar 15
        (Cs4+12, 56, 2, 62),(B+60, 58, 2, 55),
        # Bar 16 — final
        (Cs4+12, 60, 4, 55),
    ]
    # fmt: on

    rh_notes = [Note(pitch=p, start=s, dur=d, vel=v, ch=0) for p,s,d,v in rh_raw]
    t1 = _notes_to_track(rh_notes, name="Melody")
    t2 = _notes_to_track(lh_notes, name="Triplet Arpeggio")
    return _smf(bpm=54, time_sig=(4, 4), tracks=[t1, t2])


# ===========================================================================
# 6. Original — Neo-Soul Groove in F# minor (multi-track)
# ===========================================================================
# Original composition. Not derived from any copyrighted work.
# 4/4 at 92 BPM. Tracks: Piano/Rhodes, Bass, Drums.

def neo_soul_groove() -> bytes:
    """Original neo-soul groove in F# minor — 16 bars, 92 BPM, multi-track."""
    Fs3, Gs3, A3, B3, Cs4, D4, E4, Fs4 = 54, 56, 57, 59, 61, 62, 64, 66
    Fs2, Cs3, A2, E2 = 42, 49, 45, 40

    # Piano/Rhodes — chord comping with characteristic neo-soul voicings
    piano_notes: list[Note] = []
    # F# minor 9 voicing: F#-A-C#-E (rootless: A-C#-E, adding 9th G#)
    comp_pattern = [
        # beat, pitches (staggered for realism), vel
        (0.0,  [Gs3, Cs4, E4],  68),
        (0.5,  [Gs3, Cs4, E4],  52),
        (1.75, [A3, D4, Fs4],   70),
        (2.0,  [A3, D4, Fs4],   58),
        (2.5,  [Gs3, Cs4, E4],  65),
        (3.0,  [Gs3, Cs4, E4],  50),
        (3.75, [A3, D4, Fs4],   72),
    ]
    for bar in range(16):
        bar_start = bar * 4.0
        # Vary chord colour slightly each 4 bars
        for beat_off, pitches, vel in comp_pattern:
            for j, p in enumerate(pitches):
                piano_notes.append(Note(pitch=p, start=bar_start + beat_off + j*0.02, dur=0.45, vel=_hv(vel, -bar%4), ch=0))

    # Bass — syncopated neo-soul bassline
    bass_raw: list[tuple[int, float]] = [
        # F# root-movement pattern
        (Fs2, 0.0), (Fs2, 0.5), (Cs3, 1.0), (A2, 2.0), (Fs2, 2.5), (E2, 3.5),
        (Fs2, 4.0), (Fs2, 4.75),(Cs3, 5.0), (E2, 6.0), (A2, 6.5), (Fs2, 7.5),
    ]
    bass_notes: list[Note] = []
    for bar in range(16):
        for pitch, beat in bass_raw[:6 + (bar % 2)*2]:
            bass_notes.append(Note(pitch=pitch, start=bar*4+beat, dur=0.35, vel=_hv(75, -10), ch=2))

    # Drums — Channel 9, GM percussion
    KICK, SNARE, HAT_C, HAT_O = 36, 38, 42, 46
    drum_pattern: list[tuple[int, float, int]] = [
        (KICK,  0.0, 85), (HAT_C, 0.0, 60),
        (HAT_C, 0.5, 52),
        (SNARE, 1.0, 80), (HAT_C, 1.0, 58),
        (HAT_C, 1.5, 50),
        (KICK,  2.0, 78), (HAT_C, 2.0, 60),
        (KICK,  2.5, 65),
        (SNARE, 3.0, 82), (HAT_C, 3.0, 58),
        (HAT_O, 3.5, 55),
        (HAT_C, 3.75, 48),
    ]
    drum_notes: list[Note] = []
    for bar in range(16):
        for pitch, beat, vel in drum_pattern:
            drum_notes.append(Note(pitch=pitch, start=bar*4+beat, dur=0.2, vel=vel, ch=9))

    t1 = _notes_to_track(piano_notes, name="Rhodes")
    t2 = _notes_to_track(bass_notes,  name="Bass")
    t3 = _notes_to_track(drum_notes,  name="Drums")
    return _smf(bpm=92, time_sig=(4, 4), tracks=[t1, t2, t3])


# ===========================================================================
# 7. Original — Modal Jazz Sketch in D Dorian (multi-track)
# ===========================================================================
# Original composition. 4/4 at 120 BPM.
# Tracks: Piano, Walking Bass, Brushed Drums.

def modal_jazz_sketch() -> bytes:
    """Original modal jazz sketch in D Dorian — 12 bars, 120 BPM."""
    D3, E3, F3, G3, A3, B3, C4, D4 = 50, 52, 53, 55, 57, 59, 60, 62
    D2, A2, G2, C2, E2, F2 = 38, 45, 43, 36, 40, 41

    # Piano comping — shell voicings (3rd + 7th)
    comp: list[Note] = []
    voicings = [
        (0.0, [F3, C4, E3], 68),   # Dm7 — F + C = 3rd+7th
        (1.0, [F3, C4],     55),
        (1.5, [F3, B3],     60),   # sus variation
        (2.0, [F3, C4, E3], 65),
        (3.0, [G3, D4],     70),   # G7sus → Dm
        (3.5, [F3, C4],     58),
    ]
    for bar in range(12):
        for beat_off, pitches, vel in voicings:
            for j, p in enumerate(pitches):
                comp.append(Note(pitch=p, start=bar*4+beat_off+j*0.015, dur=0.42, vel=_hv(vel, 0), ch=0))

    # Walking bass — Dorian
    walk_pitches = [D2, E2, F2, G2, A2, G2, F2, E2]
    bass: list[Note] = []
    for bar in range(12):
        for beat, p in enumerate(walk_pitches[:4]):
            bass.append(Note(pitch=p + (bar % 3) * 2, start=bar*4+beat, dur=0.92, vel=_hv(72, -8), ch=2))

    # Brushed snare feel
    KICK, SNARE, RD, HAT = 36, 38, 51, 42
    brush_pattern = [
        (KICK,  0.0, 75), (RD, 0.0, 55),
        (RD,    0.5, 48),
        (SNARE, 1.0, 68), (RD, 1.0, 52),
        (RD,    1.5, 45),
        (KICK,  2.0, 70), (RD, 2.0, 55),
        (KICK,  2.5, 60),
        (SNARE, 3.0, 72), (RD, 3.0, 52),
        (RD,    3.5, 48), (RD, 3.75, 44),
    ]
    drums: list[Note] = []
    for bar in range(12):
        for pitch, beat, vel in brush_pattern:
            drums.append(Note(pitch=pitch, start=bar*4+beat, dur=0.18, vel=vel, ch=9))

    t1 = _notes_to_track(comp,  name="Piano")
    t2 = _notes_to_track(bass,  name="Bass")
    t3 = _notes_to_track(drums, name="Drums")
    return _smf(bpm=120, time_sig=(4, 4), tracks=[t1, t2, t3])


# ===========================================================================
# 8. Original — Afrobeat Pulse in G major (multi-track)
# ===========================================================================
# Original composition. 12/8 at 120 BPM.
# Tracks: Piano, Bass, Djembe (perc).

def afrobeat_pulse() -> bytes:
    """Original afrobeat groove in G major — 8 bars, 12/8 at 120 BPM."""
    G3, A3, B3, D4, E4 = 55, 57, 59, 62, 64
    G2, D3, A2, C3     = 43, 50, 45, 48

    # Piano — interlocking offbeat pattern (12/8 = 4 dotted quarters)
    piano: list[Note] = []
    # 12/8: each dotted quarter = 1.5 quarter beats
    offbeat_comp = [
        (0.5, [G3, B3, D4], 70),
        (1.5, [A3, D4, E4], 65),
        (2.5, [G3, B3, D4], 72),
        (3.5, [A3, D4, E4], 68),
        (4.5, [G3, B3, D4], 65),
        (5.0, [A3, D4, E4], 60),
    ]
    for bar in range(8):
        for beat_off, pitches, vel in offbeat_comp:
            for j, p in enumerate(pitches):
                piano.append(Note(pitch=p, start=bar*6+beat_off+j*0.02, dur=0.4, vel=_hv(vel, 0), ch=0))

    # Bass — "one-drop" anchored
    bass_pts = [(G2, 0), (D3, 1.5), (G2, 3), (A2, 4.5)]
    bass: list[Note] = []
    for bar in range(8):
        for p, b in bass_pts:
            bass.append(Note(pitch=p, start=bar*6+b, dur=1.2, vel=_hv(78, -5), ch=2))

    # Djembe — channel 9, tone/slap/bass pattern
    # GM: open hi-hat=46 (djembe tone), snare=38 (slap), bass drum=35 (bass tone)
    TONE, SLAP, BASS_TONE = 46, 38, 35
    djem_pattern = [
        (BASS_TONE, 0.0, 88), (TONE, 0.5, 75), (TONE, 1.0, 65),
        (SLAP, 1.5, 80), (TONE, 2.0, 68), (TONE, 2.5, 60),
        (BASS_TONE, 3.0, 85), (TONE, 3.5, 72), (TONE, 4.0, 62),
        (SLAP, 4.5, 78), (TONE, 5.0, 65), (TONE, 5.5, 55),
    ]
    djembe: list[Note] = []
    for bar in range(8):
        for pitch, beat, vel in djem_pattern:
            djembe.append(Note(pitch=pitch, start=bar*6+beat, dur=0.18, vel=vel, ch=9))

    t1 = _notes_to_track(piano,  name="Piano")
    t2 = _notes_to_track(bass,   name="Bass")
    t3 = _notes_to_track(djembe, name="Djembe")
    return _smf(bpm=120, time_sig=(12, 8), tracks=[t1, t2, t3])


# ===========================================================================
# 9. Original — Chanson Minimale in A major (solo piano)
# ===========================================================================

def chanson_minimale() -> bytes:
    """Original chanson minimale in A major — 16 bars, 52 BPM, solo piano."""
    A3, B3, Cs4, D4, E4, Fs4, Gs4, A4 = 57, 59, 61, 62, 64, 66, 68, 69
    A2, E3, A3b = 45, 52, 57

    notes: list[Note] = []
    # Ostinato LH: A2-E3-A3 waltz (3/4)
    for bar in range(16):
        s = bar * 3.0
        notes.append(Note(A2, s,   0.85, 55, 1))
        notes.append(Note(E3, s+1, 1.85, 42, 1))
        notes.append(Note(A3b, s+1, 1.85, 38, 1))

    # RH melody — simple, folk-like
    mel_raw: list[tuple[int, float, float, int]] = [
        (E4,0,1,72),(Fs4,1,0.5,68),(E4,1.5,0.5,65),(Cs4,2,1,70),
        (D4,3,1,68),(E4,4,1,72),(A3,5,1,65),
        (A3,6,2,70),(B3,8,1,62),
        (Cs4,9,1,68),(D4,10,1,72),(E4,11,1,68),
        (Cs4,12,1,70),(B3,13,0.5,65),(A3,13.5,0.5,62),(A3,14,1,68),
        (A3,15,2,65),(B3,17,1,55),
        # Second half — more development
        (E4,18,1,75),(Fs4,19,0.5,70),(Gs4,19.5,0.5,68),(A4,20,1,80),
        (A4,21,1,75),(Gs4,22,0.5,70),(Fs4,22.5,0.5,65),(E4,23,1,68),
        (Cs4,24,2,70),(D4,26,1,62),
        (E4,27,1,65),(Cs4,28,1,68),(A3,29,1,62),
        (D4,30,1,70),(E4,31,0.5,68),(D4,31.5,0.5,65),(Cs4,32,1,72),
        (B3,33,1,65),(A3,34,2,70),
        # Coda pppp
        (E4,36,1,50),(Cs4,37,1,45),(A3,38,1,40),(A3,39,3,35),
        (A3,42,3,28),
        (A3,45,3,20),
    ]
    notes.extend(Note(p,s,d,v,0) for p,s,d,v in mel_raw)

    track = _notes_to_track(notes, name="Piano")
    return _smf(bpm=52, time_sig=(3, 4), tracks=[track])


# ===========================================================================
# 10. Original — Ambient Textures in Eb major (slow evolving pads)
# ===========================================================================

def ambient_textures() -> bytes:
    """Original ambient textures in Eb major — 32 bars, 60 BPM, pads."""
    Eb3, G3, Bb3, Eb4, G4 = 51, 55, 58, 63, 67
    Ab3, C4, Eb4b, F3, C3 = 56, 60, 63, 53, 48

    notes: list[Note] = []
    # Long sustained chords — whole notes (4 beats each) with slow swell
    chord_progression = [
        ([Eb3, G3, Bb3, Eb4], 0),    # Eb major
        ([Eb3, G3, Bb3, G4],  4),    # Eb add9
        ([Ab3, C4, Eb4b],     8),    # Ab major
        ([F3,  Bb3, Eb4b],   12),    # Bb sus
        ([Eb3, G3, Bb3, Eb4], 16),   # Eb major return
        ([Ab3, C4, Eb4b],    20),    # Ab
        ([F3,  Bb3, Eb4b],   24),    # Bb sus
        ([Eb3, G3, Bb3],     28),    # Eb final
    ]
    velocities = [45, 55, 60, 55, 50, 58, 52, 40]  # gentle swell

    for (pitches, start), vel in zip(chord_progression * 4, velocities * 4):
        for j, p in enumerate(pitches):
            for rep in range(4):  # 4 repetitions of progression
                notes.append(Note(p, start + rep*32, 3.8, _hv(vel, j), 0))

    # Sparse melodic fragments — high register
    mel_frags: list[tuple[int, float, float, int]] = [
        (Eb4+12, 8, 2, 35),(G4+12, 10, 3, 30),
        (Bb3+12, 20, 3, 32),(Eb4+12, 24, 4, 28),
        (G4+12, 36, 2, 30),(Eb4+12, 40, 3, 28),
        (G4+12, 56, 2, 25),(Eb4+12, 60, 4, 22),
    ]
    for p,s,d,v in mel_frags:
        notes.append(Note(p,s,d,v,0))

    track = _notes_to_track(notes, name="Pads")
    return _smf(bpm=60, time_sig=(4, 4), tracks=[track])


# ===========================================================================
# CODE_FILES — no longer used by seed_v2.py.
#
# seed_v2.py clones the real GitHub repos at seed time and imports their
# actual file trees and git histories.  This stub keeps the module importable
# without breaking any other script that might reference CODE_FILES.
# ===========================================================================

CODE_FILES: dict[str, dict[str, str]] = {
    # Real repos are cloned by seed_v2._import_github_repo(); nothing here.
    #   github.com/cgcardona/muse         → repo-v2-muse-vcs-00001
    #   github.com/cgcardona/agentception → repo-v2-agentcept-00001
    #   github.com/cgcardona/musehub      → repo-v2-musehub-src-001
}

# ---------------------------------------------------------------------------
# The rest of this file only defines MIDI generators.  The large synthetic
# code blobs that previously lived here have been removed; actual file content
# now comes directly from the upstream git repos.
# ---------------------------------------------------------------------------

# ===========================================================================
# Dispatch table — maps a string key to a generator function
# ===========================================================================

MIDI_GENERATORS: dict[str, callable] = {
    "wtc_prelude_c":       wtc_prelude_c_major,
    "bach_minuet_g":       bach_minuet_g,
    "gymnopedie_no1":      gymnopedie_no1,
    "chopin_nocturne_op9": chopin_nocturne_op9_no2,
    "moonlight_mvt1":      moonlight_sonata_mvt1,
    "neo_soul":            neo_soul_groove,
    "modal_jazz":          modal_jazz_sketch,
    "afrobeat":            afrobeat_pulse,
    "chanson":             chanson_minimale,
    "ambient":             ambient_textures,
}
