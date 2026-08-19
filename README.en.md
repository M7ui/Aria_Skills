# Aria — Portable Music Skills Pack

> An AI music creation skill pack: **Skills (prompts) + Toolkit** in one package.
> Headless composition: no Node server, no LLM API calls.

[English](README.en.md) | [简体中文](README.md)

## Features

- **Natural-language composition**: say one sentence, and the Agent produces `song.json` + a standard MIDI file through a five-step workflow
- **Zero-dependency execution layer**: Python standard library only (Python 3.8+), callable directly from Bash by any Agent
- **JSON in/out + exit-code contract**: `0 success / 1 data error / 2 usage error`, results are programmatically testable
- **Quality loop**: `validate --strict` enforces 0 errors; `analyze` scores 0–10 with actionable Chinese suggestions — no release below the bar
- **Fully offline**: scale/chord lookups are computed by the built-in CLI, no network or external API required
- **Portable**: `install.py` deploys to `~/.agents` in one step for skills-scanning Agent tools

## Requirements

- Python 3.8+ (standard library only, no pip dependencies)
- Platforms: Windows / macOS / Linux (on Chinese Windows, track names default to GBK for player/DAW compatibility)

## Contents

```
.agent/
├── AGENTS.md              # Cross-tool entry facade (auto-discovered by AGENTS.md-aware tools)
├── README.md              # Chinese README
├── README.en.md           # English README (this file)
├── LICENSE                # MIT License
├── install.py             # Self-installer: deploys to ~/.agents for skills scanning
├── skills/
│   ├── aria-compose/       # Composition workflow: natural language → song.json → MIDI (pattern library / rules / examples)
│   │   └── references/    #   composition-rules / pattern-library / midi-schema / examples
│   └── aria-music-theory/  # Music theory Q&A: scales/chords/progressions + 5 style references (pop/EDM/jazz/tropical/techniques)
└── toolkits/
    ├── aria-midi/          # Zero-dependency Python CLI: generate/validate/inspect/scale/analyze
    │   ├── aria_midi.py    #   v1.1.0, single file ~865 lines
    │   ├── README.md      #   Full CLI documentation
    │   ├── tests/         #   23 self-tests (roundtrip/validation/encoding/analysis)
    │   └── bin/aria-midi.cmd   # PATH shim
    └── aria-decode/        # Zero-dependency lossless MIDI → JSON decoder
        ├── aria_decode.py  #   v1.0.1, single file ~590 lines
        ├── README.md      #   Full decoder documentation
        ├── tests/         #   22 cases, 35 assertions
        └── bin/aria-decode.cmd  # PATH shim
```

## Architecture

```mermaid
flowchart TB
    User[User: one sentence] --> Agent[Agent tool<br/>reads SKILL.md prompts]

    subgraph Skills[Skill layer · prompts]
        Compose[aria-compose<br/>composition workflow]
        Theory[aria-music-theory<br/>music theory Q&A]
    end

    subgraph Toolkit[Toolkit layer · zero-dependency Python CLI]
        Midi[aria-midi<br/>validate · analyze · generate · inspect · scale]
        Decode[aria-decode<br/>lossless MIDI → JSON]
    end

    subgraph Output[Artifacts]
        Song[song.json note data]
        MidiFile[(song.mid standard MIDI)]
        MidiJson[MIDI JSON]
    end

    Agent --> Compose
    Agent --> Theory
    Compose -->|five-step workflow| Midi
    Theory -->|scale/chord lookups| Midi
    Midi -->|validate / analyze| Song
    Midi -->|generate| MidiFile
    MidiFile --> Decode
    Decode --> MidiJson
```

Flow: one user sentence → the Agent drives the tools via skill prompts → the zero-dependency CLI computes in the toolkit layer → produces `song.json` and a standard MIDI file; `aria-decode` losslessly decodes any `.mid` back into JSON for reverse engineering / QA.

## Quick Start

```bash
# 1. Install to ~/.agents (auto-discovery for skills-scanning tools; idempotent, re-runnable)
python install.py

# 2. Use the CLI directly (zero installation)
python toolkits/aria-midi/aria_midi.py scale --root C4 --type major --list

# 3. Or add to PATH and use the short command
aria-midi generate --input song.json --output song.mid --bpm 120

# 4. Reverse-decode a MIDI file
aria-decode decode --input song.mid --output song.json
```

## CLI Subcommand Reference

| Subcommand | Purpose | Exit code |
|------------|---------|-----------|
| `validate --input song.json [--strict]` | Validate schema/range/velocity/quantization/overlap | 0 pass / 1 errors |
| `analyze --input song.json [--chords chords.json] [--key-root C4]` | Score 0–10 + improvement suggestions | 0 |
| `generate --input song.json --output song.mid [--bpm 120]` | Generate a standard MIDI file (Type-1, TPQN=480) | 0 / 1 / 2 |
| `inspect --input song.mid` | Parse a .mid back to JSON for self-check | 0 / 1 |
| `scale --root C4 --type major [--list/--chord/--snap/--suggest]` | Scale/chord lookups (13 scales, 14 chords) | 0 / 2 |

All subcommands take JSON in and produce JSON out; `--input -` reads from stdin; `aria-midi --version` shows the version.

## MIDI → JSON Decoding (aria-decode)

`aria-decode` answers "what is actually inside this `.mid`?" by losslessly decoding any MIDI file into structured JSON for reverse engineering, format conversion, and post-generation QA.

- **Every event**: meta / CC / pitch bend / lyrics / SysEx / system messages are kept, not just notes
- **Dual timing**: both PPQN and SMPTE (including 29.97 drop-frame) are supported
- **Exact time**: tempo changes are converted to seconds on a global timeline across tracks; notes include `start_time` / `end_time`
- **Readable mappings**: GM program names (128), standard CC controller names, and pitch names (C4 etc.)

```bash
aria-decode decode --input song.mid                      # full decode to stdout
aria-decode decode --input song.mid --output song.json   # full decode to a JSON file
aria-decode decode --input song.mid --no-events          # quick overview: header + global + notes
aria-decode decode --input song.mid --no-notes           # event details only
cat song.mid | aria-decode decode --input - > song.json  # stdin pipe
```

Unlike `aria-midi inspect` (lossy — extracts only notes/track names/tempo), aria-decode keeps every event. Prefer aria-decode when you need tempo changes, CC/pitch bend/lyrics, SysEx, or post-generation QA. See `toolkits/aria-decode/README.md` for the full command reference and output structure.

## Full Composition Workflow (see the five-step workflow in skills/aria-compose/SKILL.md)

```bash
aria-midi validate --input song.json --strict   # Step 1: must have 0 errors
aria-midi analyze  --input song.json --chords chords.json   # Step 2: score ≥ 7
aria-midi generate --input song.json --output song.mid      # Step 3: generate MIDI
aria-midi inspect  --input song.mid                         # Step 4: roundtrip self-check
```

Sample output (validate):

```json
{
  "ok": true,
  "errors": [],
  "warnings": [],
  "stats": {"bpm": 120, "track_count": 2, "note_count": 20, "total_beats": 32.0, "pitch_min": 36, "pitch_max": 74}
}
```

## How to Use the Skills

| Scenario | What to use |
|----------|-------------|
| Write/generate melodies, songs, MIDI, chord progressions | Read `skills/aria-compose/SKILL.md` and follow the five-step workflow |
| Music theory/arrangement Q&A | Read `skills/aria-music-theory/SKILL.md` |
| CLI only, no prompts needed | Call directly per `toolkits/aria-midi/README.md` |

## Self-Test

```bash
python toolkits/aria-midi/tests/run_tests.py    # all 23 cases pass
python toolkits/aria-decode/tests/run_tests.py  # all 22 cases / 35 assertions pass
```

## FAQ

| Question | Answer |
|----------|--------|
| Track names garbled in Windows players? | `generate` defaults to `--name-encoding auto` — GBK on Chinese Windows, UTF-8 elsewhere; override with `--name-encoding` |
| Low `analyze` score? | Follow the suggestions in the output: chord tones on strong beats, velocity arcs, rhythmic breathing, rhythmic variety |
| Notes not on the 0.25 grid? | Non-strict `validate` only warns; add `--strict` to treat it as an error; start_beat/duration must be multiples of 0.25 |
| Multi-track analysis inaccurate? | Known limitation: `analyze` merges all tracks, including accompaniment; treat the melody track as the primary reference |
| Skill changes not taking effect? | This pack is packaged from `skills-source/`; edit the source files and repackage — do not edit this pack directly (except install.py) |

## License

This project is open-sourced under the **MIT License**. See [LICENSE](LICENSE).
Copyright (c) 2026 Mark7us

## Source of Truth

This pack is generated from `skills-source/` (via `package_to_agent.py`).
Edit skills in the source workspace and repackage; do not edit this pack directly (except install.py).
