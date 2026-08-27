#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-report — MIDI 批量逆向分析报告工具（v1.0.0）

零依赖 CLI（仅 Python 标准库，复用同包 aria-decode 的解码器）：
把任意 .mid 无损解码后，输出「风格识别 + 调式推测 + 旋律动机分析」报告。

用法：
  python aria_report.py report --input <目录或文件.mid> [--output report.md] [--format md|json]

退出码契约（与 aria-midi / aria-decode 一致）：
  0 = 成功 / 1 = 数据错误 / 2 = 用法错误

定位规则：本工具与 aria-decode 同属 toolkits/ 目录（同级），通过相对路径自动
找到 ../aria-decode/aria_decode.py 复用其解码器；复制整个 toolkits/ 目录到任意
位置均可运行。
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "aria-decode"))
try:
    from aria_decode import decode_midi, DecodeError, UsageError, NOTE_NAMES, GM_PROGRAMS
except ImportError:  # pragma: no cover
    sys.stderr.write("无法定位 aria-decode（应位于 ../aria-decode/aria_decode.py）\n")
    sys.exit(2)

__version__ = "1.0.0"

# ══════════════════════════════════════════════════════════════
# 常量表
# ══════════════════════════════════════════════════════════════

# 13 种音阶模板（pitch class 集合），用于调式推测
SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "whole_tone": [0, 2, 4, 6, 8, 10],
}

# GM 打击乐通道（channel 9）不参与旋律分析
DRUM_CHANNEL = 9


# ══════════════════════════════════════════════════════════════
# 分析函数
# ══════════════════════════════════════════════════════════════

def infer_key(melody):
    """由音高集合对 13 种音阶 × 12 个根音的覆盖率推测调式。
    覆盖率相同时，优先常见调式（major/minor），再用主音出现频次打破平局。"""
    if not melody:
        return []
    pc_count = Counter(n["pitch"] % 12 for n in melody)
    pitch_freq = Counter(n["pitch"] for n in melody)
    total = sum(pc_count.values())
    results = []
    for root in range(12):
        for sname, intervals in SCALES.items():
            scale_pc = {(root + i) % 12 for i in intervals}
            coverage = sum(c for pc, c in pc_count.items() if pc in scale_pc) / total
            common = 1 if sname in ("major", "minor") else 0
            root_freq = sum(c for p, c in pitch_freq.items() if p % 12 == root)
            results.append((coverage, common, root_freq, root, sname))
    results.sort(key=lambda x: (-x[0], -x[1], -x[2]))
    return [
        {"root": NOTE_NAMES[root], "type": sname, "coverage": round(cov, 3)}
        for cov, _c, _f, root, sname in results[:3]
    ]


def detect_style(bpm, program_names, key_mode, melody):
    """基于 BPM / 音色 / 调式 / 音域的启发式风格判断。返回 Top 3。"""
    scores = []

    def add(style, score, reason):
        scores.append([style, score, reason])

    pnames = set(program_names)
    tropical_inst = {"Marimba", "Steel Drums", "Pan Flute", "Vibraphone", "Kalimba", "Xylophone"}
    piano_like = all(("Piano" in p or "Organ" in p or "Harpsichord" in p or "Clavinet" in p)
                     for p in pnames) if pnames else False
    synth_lead = any("Lead" in p for p in pnames)
    has_bass = any("Bass" in p for p in pnames)
    has_brass = any(any(x in name for x in ("Sax", "Trumpet", "Trombone", "Brass", "Horn")) for name in pnames)
    has_strings = any("String" in p for p in pnames)

    if bpm and 70 <= bpm <= 90:
        add("Lo-fi", 3, f"慢速 BPM {bpm}")
    if bpm and 100 <= bpm <= 115 and (pnames & tropical_inst):
        add("Tropical House", 3, f"BPM {bpm} + 马林巴/钢鼓/排箫音色")
    if bpm and 116 <= bpm <= 126 and has_bass:
        add("Deep House", 2, f"BPM {bpm} + 贝斯音色")
    if bpm and 118 <= bpm <= 126 and key_mode == "minor" and (has_bass or synth_lead):
        add("G-House", 2, f"BPM {bpm} + 小调 + 贝斯/合成音色")
    if bpm and 122 <= bpm <= 128 and synth_lead:
        add("Future House", 2, f"BPM {bpm} + Lead 合成音色")
    if bpm and 126 <= bpm <= 132 and synth_lead:
        add("Electro House / EDM", 3, f"BPM {bpm} + Lead 合成音色")
    if piano_like and len(pnames) <= 2:
        add("钢琴独奏 / 古典", 3, "纯钢琴/风琴类音色")
    if has_brass:
        add("爵士", 2, "萨克斯/铜管音色")
    if has_strings and not synth_lead:
        add("弦乐 / 电影配乐", 2, "弦乐音色为主")
    if key_mode == "major" and bpm and 90 <= bpm <= 130:
        add("流行", 1, "大调 + 中速")

    scores.sort(key=lambda x: -x[1])
    return [
        {"style": s, "score": sc, "reason": r}
        for s, sc, r in scores[:3]
    ]


def _bar_pos(start_beat):
    """拍位置 → 「第 N 小节第 X 拍」（4/4 假设）。"""
    bar = int(start_beat // 4) + 1
    beat = round(start_beat % 4, 2)
    return bar, beat


def extract_motifs(melody, top_n=6):
    """提取旋律轨的重复音程动机 + 发展手法。"""
    if len(melody) < 5:
        return []
    pitches = [int(n["pitch"]) for n in melody]
    starts = [float(n["start_beat"]) for n in melody]
    intervals = [pitches[i + 1] - pitches[i] for i in range(len(pitches) - 1)]

    win = 2  # 2 个音程 = 3 音动机
    seen = defaultdict(list)
    for i in range(len(intervals) - win + 1):
        seen[tuple(intervals[i:i + win])].append(i)

    motifs = []
    for key, positions in seen.items():
        if len(positions) < 2:
            continue
        # 起始音高（判断原样重复 vs 模进移调）
        start_pitches = [pitches[p] for p in positions]
        same_pitch = len(set(start_pitches)) == 1
        technique = "原样重复" if same_pitch else "模进（移调）"
        first = positions[0]
        note_names = [NOTE_NAMES[p % 12] + str(p // 12 - 1) for p in pitches[first:first + win + 1]]
        motifs.append({
            "intervals": list(key),
            "note_names": note_names,
            "count": len(positions),
            "technique": technique,
            "positions": [{"bar": _bar_pos(starts[p])[0], "beat": _bar_pos(starts[p])[1]} for p in positions],
        })

    motifs.sort(key=lambda m: (-m["count"], -len(m["positions"])))
    return motifs[:top_n]


def analyze_midi(path):
    """解码并分析单个 .mid，返回结构化结果。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise UsageError(f"无法读取文件 {path}: {e}")

    try:
        dec = decode_midi(data, include_events=False, include_notes=True,
                          file_name=os.path.basename(path))
    except DecodeError as e:
        return {"file": os.path.basename(path), "ok": False, "error": str(e)}

    header = dec.get("header", {})
    global_ = dec.get("global", {})
    tracks = dec.get("tracks", [])
    notes = dec.get("notes", [])

    # 按音轨分组（排除鼓通道）
    track_notes = defaultdict(list)
    for n in notes:
        if n.get("channel") == DRUM_CHANNEL:
            continue
        track_notes[n.get("track", 0)].append(n)

    # 旋律轨 = 平均音高最高的轨
    melody_track = None
    best_avg = -1
    for ti, ns in track_notes.items():
        if not ns:
            continue
        avg = sum(x["pitch"] for x in ns) / len(ns)
        if avg > best_avg:
            best_avg, melody_track = avg, ti

    melody = sorted(track_notes.get(melody_track, []),
                    key=lambda n: (n["start_beat"], n["pitch"])) if melody_track is not None else []

    # 音色列表（去重，保持出现顺序）
    programs = [t.get("program") for t in tracks if t.get("program") is not None]
    seen_p = set()
    program_names = []
    for p in programs:
        if p is not None and p < len(GM_PROGRAMS) and p not in seen_p:
            seen_p.add(p)
            program_names.append(GM_PROGRAMS[p])

    # 调式：meta 调号优先，否则由音符推测
    key_sig = global_.get("key_signature")
    key_mode = None
    if key_sig:
        key_mode = key_sig.get("mode")
    inferred = infer_key(melody)
    if key_mode is None and inferred:
        key_mode = inferred[0]["type"] if "major" in inferred[0]["type"] or "minor" in inferred[0]["type"] else None

    bpm = global_.get("bpm")
    style = detect_style(bpm, program_names, key_mode, melody)
    motifs = extract_motifs(melody)

    melody_name = tracks[melody_track]["name"] if melody_track is not None else None

    return {
        "file": os.path.basename(path),
        "ok": True,
        "bpm": bpm,
        "time_signature": global_.get("time_signature"),
        "duration_sec": round(global_.get("duration_sec", 0), 1),
        "key_signature": key_sig,
        "track_count": len(tracks),
        "note_count": len(notes),
        "melody_track": melody_name,
        "melody_note_count": len(melody),
        "programs": program_names,
        "style": style,
        "key_inference": inferred,
        "motifs": motifs,
        "warnings": dec.get("warnings", []),
    }


def scan_input(path):
    """扫描输入路径，返回 .mid 文件列表（单文件则直接返回）。"""
    if os.path.isfile(path):
        return [path] if path.lower().endswith(".mid") else []
    if not os.path.isdir(path):
        raise UsageError(f"输入路径不存在: {path}")
    files = sorted(os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith(".mid"))
    return files


# ══════════════════════════════════════════════════════════════
# 报告渲染
# ══════════════════════════════════════════════════════════════

def render_markdown(results, src_label):
    lines = []
    lines.append("# 旋律动机分析报告")
    lines.append("")
    ok_results = [r for r in results if r.get("ok")]
    lines.append(f"> 分析文件 {len(results)} 个（成功 {len(ok_results)} 个）· 工具 aria-report {__version__} · 输入 {src_label}")
    lines.append("")

    # 概览表
    lines.append("## 概览")
    lines.append("")
    lines.append("| 文件 | BPM | 调式推测 | 风格（Top1） | 主旋律轨 | 动机数 |")
    lines.append("|------|-----|----------|-------------|----------|--------|")
    for r in ok_results:
        key = r["key_inference"][0] if r["key_inference"] else "—"
        key_label = f"{key['root']} {key['type']}" if isinstance(key, dict) else "—"
        style_label = r["style"][0]["style"] if r["style"] else "—"
        lines.append(f"| {r['file']} | {r['bpm']} | {key_label} | {style_label} | {r['melody_track'] or '—'} | {len(r['motifs'])} |")
    for r in results:
        if not r.get("ok"):
            lines.append(f"| {r['file']} | — | — | 解码失败 | — | — |")
    lines.append("")

    # 逐个文件详述
    for r in ok_results:
        lines.append(f"## {r['file']}")
        lines.append("")
        lines.append("### 基本信息")
        lines.append("")
        lines.append(f"- BPM：{r['bpm']} ｜ 拍号：{r['time_signature']} ｜ 时长：{r['duration_sec']}s")
        lines.append(f"- 音轨数：{r['track_count']} ｜ 音符总数：{r['note_count']} ｜ 主旋律轨：{r['melody_track'] or '—'}（{r['melody_note_count']} 音）")
        if r["programs"]:
            lines.append(f"- 音色：{'、'.join(r['programs'])}")
        if r["key_signature"]:
            ks = r["key_signature"]
            lines.append(f"- 调号（meta）：{ks.get('sharps_flats')} 升/降号 · {'大调' if ks.get('mode') == 'major' else '小调'}")
        lines.append("")

        lines.append("### 风格判断（启发式，供参考）")
        lines.append("")
        if r["style"]:
            for i, s in enumerate(r["style"], 1):
                lines.append(f"{i}. **{s['style']}**（得分 {s['score']}）— {s['reason']}")
        else:
            lines.append("（未能匹配已知风格，建议结合 BPM 与音色人工判断）")
        lines.append("")

        lines.append("### 调式推测")
        lines.append("")
        if r["key_inference"]:
            for k in r["key_inference"]:
                lines.append(f"- {k['root']} {k['type']}（覆盖率 {k['coverage']}）")
        lines.append("")

        lines.append("### 旋律动机分析")
        lines.append("")
        if r["motifs"]:
            for i, m in enumerate(r["motifs"], 1):
                pos = "、".join(f"第{p['bar']}小节第{p['beat']}拍" for p in m["positions"][:4])
                more = f" 等 {m['count']} 处" if m["count"] > 4 else ""
                lines.append(f"**动机 {i}**：`{' → '.join(m['note_names'])}`（音程 `{' '.join(f'{x:+d}' for x in m['intervals'])}`）")
                lines.append(f"- 出现 {m['count']} 次：{pos}{more} ｜ 手法：{m['technique']}")
        else:
            lines.append("（旋律音符不足 5 个或未检出显著重复动机）")
        lines.append("")

        if r["warnings"]:
            lines.append(f"> 解码警告：{'；'.join(r['warnings'])}")
            lines.append("")

    for r in results:
        if not r.get("ok"):
            lines.append(f"## {r['file']}")
            lines.append("")
            lines.append(f"> 解码失败：{r.get('error')}")
            lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def cmd_report(args):
    files = scan_input(args.input)
    if not files:
        print(json.dumps({"ok": False, "error": "未找到 .mid 文件（请把 MIDI 放入 decode/ 目录）"},
                         ensure_ascii=False), file=sys.stderr)
        return 1

    results = [analyze_midi(f) for f in files]

    if args.format == "json":
        out = json.dumps(results, ensure_ascii=False, indent=2)
        if args.output and args.output != "-":
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out + "\n")
        else:
            print(out)
    else:
        md = render_markdown(results, args.input)
        if args.output and args.output != "-":
            out_dir = os.path.dirname(os.path.abspath(args.output))
            if out_dir and not os.path.isdir(out_dir):
                raise UsageError(f"输出目录不存在: {out_dir}")
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(md + "\n")
            print(f"报告已写入 {args.output}（{len(results)} 个文件）")
        else:
            print(md)
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="aria-report",
        description="Aria 技能包 — MIDI 批量逆向分析（风格识别 + 调式推测 + 旋律动机报告）")
    p.add_argument("--version", action="version", version=f"aria-report {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<子命令>")

    r = sub.add_parser("report", help="扫描目录/文件，生成旋律动机分析报告")
    r.add_argument("--input", required=True, metavar="<目录或文件.mid>",
                   help="输入 .mid 文件或包含 .mid 的目录")
    r.add_argument("--output", metavar="<report.md>", help="输出报告路径（默认 stdout）")
    r.add_argument("--format", choices=["md", "json"], default="md", help="输出格式（默认 md）")
    r.set_defaults(handler=cmd_report)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return 2
    try:
        return args.handler(args)
    except UsageError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
