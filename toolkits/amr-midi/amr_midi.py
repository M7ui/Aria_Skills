#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""amr-midi — AMIDI Skills 执行层：零依赖 MIDI 工具包 CLI（仅 Python 标准库）。

子命令：
  generate   song.json 音符数据 -> 标准 MIDI 文件（Type-1，TPQN=480）
  validate   校验 song.json 的 schema / 音域 / 力度 / 量化 / 重叠
  inspect    解析现有 .mid 文件 -> 音符列表 JSON（零依赖解析器）
  scale      音阶 / 和弦工具：列音、和弦音、调式吸附、调式推测
  analyze    旋律质量分析：0-10 评分 + 中文改进建议

约定：
  - 所有子命令 JSON 进 JSON 出（generate 输出二进制 .mid 文件）
  - --input 支持 "-" 从 stdin 读取（generate/validate/analyze）
  - 退出码：0 成功 / 1 数据校验失败 / 2 用法或 IO 错误
"""

import argparse
import json
import locale
import math
import os
import re
import struct
import sys
from collections import deque

TPQN = 480  # ticks per quarter note（与网页应用一致）

# ══════════════════════════════════════════════════════════════
# 乐理数据表
# ══════════════════════════════════════════════════════════════
SCALES = {
    "major":            [0, 2, 4, 5, 7, 9, 11],
    "minor":            [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor":   [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor":    [0, 2, 3, 5, 7, 9, 11],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues":            [0, 3, 5, 6, 7, 10],
    "dorian":           [0, 2, 3, 5, 7, 9, 10],
    "phrygian":         [0, 1, 3, 5, 7, 8, 10],
    "lydian":           [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":       [0, 2, 4, 5, 7, 9, 10],
    "locrian":          [0, 1, 3, 5, 6, 8, 10],
    "whole_tone":       [0, 2, 4, 6, 8, 10],
}

CHORDS = {
    "maj":   [0, 4, 7],
    "min":   [0, 3, 7],
    "dim":   [0, 3, 6],
    "aug":   [0, 4, 8],
    "maj7":  [0, 4, 7, 11],
    "min7":  [0, 3, 7, 10],
    "dom7":  [0, 4, 7, 10],
    "m7b5":  [0, 3, 6, 10],
    "dim7":  [0, 3, 6, 9],
    "sus4":  [0, 5, 7],
    "sus2":  [0, 2, 7],
    "maj9":  [0, 4, 7, 11, 14],
    "min9":  [0, 3, 7, 10, 14],
    "add9":  [0, 4, 7, 14],
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# GM 常用音色（Program 编号）
GM_PROGRAMS = {
    0: "Acoustic Grand Piano", 24: "Acoustic Guitar (nylon)",
    25: "Acoustic Guitar (steel)", 32: "Acoustic Bass",
    33: "Electric Bass (finger)", 48: "String Ensemble 1",
    49: "String Ensemble 2", 80: "Lead 1 (square)",
    88: "Pad 2 (warm)", 114: "Steel Drums",
}


class DataError(Exception):
    """输入数据非法（校验失败 / 无法解析的 MIDI）→ 退出码 1。"""


class UsageError(Exception):
    """用法或 IO 错误 → 退出码 2。"""


# ══════════════════════════════════════════════════════════════
# 基础工具
# ══════════════════════════════════════════════════════════════
def parse_pitch(value):
    """接受 MIDI 数字或音名（"C4"=60、"F#3"=54、"Bb2"=46），返回 0-127 整数。"""
    if isinstance(value, bool):
        raise ValueError(f"无法解析音高: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        m = re.match(r"^([A-Ga-g])([#b]?)(-?\d+)$", s)
        if m:
            letter = m.group(1).upper()
            acc = {"#": 1, "b": -1}.get(m.group(2), 0)
            semitone = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[letter] + acc
            return (int(m.group(3)) + 1) * 12 + semitone
    raise ValueError(f"无法解析音高: {value!r}")


def pitch_name(pitch):
    return NOTE_NAMES[pitch % 12] + str(pitch // 12 - 1)


def snap_to_scale(pitch, root, scale_type):
    """把音高吸附到最近音阶音；等距时优先取高邻音（升号倾向向上解决）。"""
    intervals = SCALES.get(scale_type, SCALES["major"])
    rel = ((pitch % 12) - (root % 12)) % 12
    if rel in intervals:
        return pitch
    best, best_dist = None, 13
    for iv in intervals:
        d = min(abs(rel - iv), 12 - abs(rel - iv))
        if d < best_dist or (d == best_dist and (best is None or iv > best)):
            best_dist, best = d, iv
    return pitch + (best - rel)


def chord_tones(root, chord_type):
    ivs = CHORDS.get(chord_type, CHORDS["maj"])
    base = (root // 12) * 12 + (root % 12)
    return [base + iv for iv in ivs]


# ══════════════════════════════════════════════════════════════
# 音轨名编码（MIDI 文本 meta 无统一标准：中文 Windows 工具按系统
# ANSI 码页（GBK）读取，现代跨平台工具按 UTF-8——两头兼容）
# ══════════════════════════════════════════════════════════════
def resolve_name_encoding(requested):
    """auto → Windows 用系统 ANSI 码页（中文系统 GBK），其它平台 UTF-8。"""
    if requested and requested != "auto":
        try:
            "ok".encode(requested)
        except LookupError:
            raise UsageError(f"未知编码: {requested}")
        return requested
    if os.name == "nt":
        try:
            ans = locale.getpreferredencoding(False) or ""
            if ans and "utf" not in ans.lower():
                return ans
        except Exception:
            pass
    return "utf-8"


def _encode_name_bytes(name, encoding):
    """按指定编码写入音轨名；超过 64 字节时从尾部逐字截断，不切断多字节字符。"""
    if len(name.encode(encoding, errors="replace")) <= 64:
        return name.encode(encoding, errors="replace")
    s = name
    while s and len(s.encode(encoding, errors="replace")) > 64:
        s = s[:-1]
    return s.encode(encoding, errors="replace")


def _decode_name(data):
    """解析音轨名：优先 UTF-8 严格解码，失败依次尝试系统 ANSI 码页与常见 CJK
    编码（GBK/Big5/Shift-JIS），最后回退 latin-1（永不失败）。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    candidates = []
    try:
        ans = locale.getpreferredencoding(False) or ""
        if ans and "utf" not in ans.lower() and ans not in candidates:
            candidates.append(ans)
    except Exception:
        pass
    for enc in ("cp936", "gbk", "big5", "shift_jis"):
        if enc not in candidates:
            candidates.append(enc)
    for enc in candidates:
        try:
            return data.decode(enc)  # 严格解码，失败则试下一个
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1")


# ══════════════════════════════════════════════════════════════
# MIDI 编码（generate）— 迁移自 AI-Music-Roll 的 midi_gen.py
# ══════════════════════════════════════════════════════════════
def encode_vlq(value):
    value = max(0, int(value))
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(parts))


def _vlq_len(data, pos, end):
    """返回 (值, 新位置)。越界抛 DataError。"""
    value = 0
    while True:
        if pos >= end:
            raise DataError("MIDI 数据截断：变长整数未结束")
        b = data[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not (b & 0x80):
            return value, pos


def build_track_body(name, channel, program, notes, name_encoding="utf-8"):
    events = []

    name_bytes = _encode_name_bytes(name, name_encoding)
    events.append((0, b"\xff\x03" + struct.pack("B", len(name_bytes)) + name_bytes))

    if program >= 0:
        events.append((0, struct.pack("BB", 0xC0 | (channel & 0x0F), program & 0x7F)))

    raw = []
    for n in notes:
        pitch = max(0, min(127, int(round(float(n.get("pitch", 60))))))
        start = float(n.get("start_beat", 0))
        if start < 0:
            raise DataError(f"音符 start_beat 不能为负（收到 {start}），负起点会破坏 MIDI 时间流")
        dur = float(n.get("duration", 1))
        vel = max(1, min(127, int(n.get("velocity", 100))))
        tick_on = int(round(start * TPQN))
        dur_tick = int(round(dur * TPQN))
        if dur_tick <= 0:
            dur_tick = int(round(0.25 * TPQN))
        raw.append((tick_on, "on", channel & 0x0F, pitch, vel))
        raw.append((tick_on + dur_tick, "off", channel & 0x0F, pitch, 0))

    # 同一 tick 内 Note-Off 先于 Note-On，避免同音高衔接被吃掉
    raw.sort(key=lambda x: (x[0], 0 if x[1] == "off" else 1))

    for abs_tick, typ, ch, pitch, vel in raw:
        status = (0x90 | ch) if typ == "on" else (0x80 | ch)
        events.append((abs_tick, struct.pack("BBB", status, pitch, vel)))

    events.sort(key=lambda x: x[0])
    last_tick = events[-1][0] if events else 0
    events.append((last_tick, b"\xff\x2f\x00"))

    body = bytearray()
    cursor = 0
    for abs_tick, data in events:
        body.extend(encode_vlq(abs_tick - cursor))
        cursor = abs_tick
        body.extend(data)
    return struct.pack(">4sI", b"MTrk", len(body)) + bytes(body)


def build_conductor_track(bpm, num, den):
    events = []
    us_per_quarter = int(60_000_000 / bpm)
    events.append((0, b"\xff\x51\x03" + struct.pack(">I", us_per_quarter)[1:]))
    if den > 0 and (den & (den - 1)) == 0:
        den_byte = int(math.log2(den))
    else:
        den_byte = 2  # 非 2 的幂时回退 4/4
    events.append((0, b"\xff\x58\x04" + struct.pack("BBBB", num, den_byte, 24, 8)))
    events.append((0, b"\xff\x2f\x00"))

    body = bytearray()
    cursor = 0
    for abs_tick, data in events:
        body.extend(encode_vlq(abs_tick - cursor))
        cursor = abs_tick
        body.extend(data)
    return struct.pack(">4sI", b"MTrk", len(body)) + bytes(body)


def build_midi(tracks, bpm, num=4, den=4, name_encoding="utf-8"):
    conductor = build_conductor_track(bpm, num, den)
    midi_tracks = []
    for t in tracks:
        name = str(t.get("name", "Track"))
        channel = int(t.get("channel", 0)) & 0x0F
        program = int(t.get("program", 0))
        notes = t.get("notes", [])
        midi_tracks.append(build_track_body(name, channel, program, notes, name_encoding))
    header = struct.pack(">4sIHHH", b"MThd", 6, 1, len(midi_tracks) + 1, TPQN)
    return header + conductor + b"".join(midi_tracks)


# ══════════════════════════════════════════════════════════════
# MIDI 解析（inspect）— 零依赖解析器
# ══════════════════════════════════════════════════════════════
_META_CHANNEL = 0x8


def _data_len(status):
    """通道消息的数据字节数：0x8n-0xBn、0xEn 为 2 字节，0xCn-0xDn 为 1 字节。"""
    if 0x80 <= status < 0xC0 or 0xE0 <= status < 0xF0:
        return 2
    return 1


def parse_midi(data):
    if len(data) < 14 or data[:4] != b"MThd":
        raise DataError("不是有效的 MIDI 文件（缺少 MThd 头）")
    header_len = struct.unpack(">I", data[4:8])[0]
    fmt = struct.unpack(">H", data[8:10])[0]
    ntrks = struct.unpack(">H", data[10:12])[0]
    division = struct.unpack(">H", data[12:14])[0]
    if division & 0x8000:
        raise DataError("不支持 SMPTE 时基的 MIDI 文件")
    tpqn = division or TPQN

    pos = 8 + header_len
    result = {"format": fmt, "tpqn": tpqn, "bpm": None, "time_signature": "4/4", "tracks": []}

    for ti in range(ntrks):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            raise DataError(f"音轨 {ti} 缺少 MTrk 块")
        track_len = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        pos += 8
        end = min(pos + track_len, len(data))

        abs_tick = 0
        running = None
        pending = {}  # pitch -> deque[(tick, vel)]
        track = {"index": ti, "name": f"Track {ti}", "program": None, "notes": []}
        had_name = False
        had_program = False

        while pos < end:
            delta, pos = _vlq_len(data, pos, end)
            abs_tick += delta
            b = data[pos]
            pos += 1

            if b == 0xFF:  # Meta 事件
                if pos >= end:
                    raise DataError("MIDI 数据截断：meta 类型缺失")
                meta_type = data[pos]
                pos += 1
                mlen, pos = _vlq_len(data, pos, end)
                payload = data[pos:pos + mlen]
                pos += mlen
                if meta_type == 0x2F:  # End of Track：未闭合音符就地收尾
                    for pitch, q in pending.items():
                        for tick, vel in q:
                            track["notes"].append({
                                "pitch": pitch,
                                "start_beat": round(tick / tpqn, 3),
                                "duration": round((abs_tick - tick) / tpqn, 3),
                                "velocity": vel,
                            })
                    pending.clear()
                elif meta_type == 0x03:  # 音轨名
                    track["name"] = _decode_name(payload)
                    had_name = True
                elif meta_type == 0x51 and len(payload) >= 3:  # Tempo
                    us = int.from_bytes(payload[:3], "big")
                    if us > 0 and result["bpm"] is None:
                        result["bpm"] = round(60_000_000 / us, 2)
                elif meta_type == 0x58 and len(payload) >= 2:  # 拍号
                    result["time_signature"] = f"{payload[0]}/{2 ** payload[1]}"
                continue

            if b in (0xF0, 0xF7):  # SysEx
                slen, pos = _vlq_len(data, pos, end)
                pos += slen
                continue

            if b & 0x80:
                status = b
                running = b
            else:
                if running is None:
                    raise DataError(f"MIDI 数据非法：数据字节 0x{b:02X} 出现在状态字节之前")
                status = running
                pos -= 1  # 该字节是数据字节，回退

            if status in (0xF1, 0xF3, 0xF9):  # 仅含长度的系统消息
                pos += {0xF1: 1, 0xF3: 1, 0xF9: 0}[status]
                continue
            if status in (0xF2, 0xF6, 0xF7, 0xF8, 0xFA, 0xFB, 0xFC, 0xFE):
                pos += 2 if status == 0xF2 else 0
                continue

            nbytes = _data_len(status)
            if pos + nbytes > end:
                raise DataError("MIDI 数据截断：通道消息数据不足")
            d1 = data[pos]
            d2 = data[pos + 1] if nbytes == 2 else None
            pos += nbytes

            msg = status & 0xF0
            ch = status & 0x0F
            if msg == 0xC0:  # Program Change
                track["program"] = d1
                had_program = True
            elif msg == 0x90 and d2 == 0:  # vel=0 记法 → Note-Off
                q = pending.get(d1)
                if q:
                    tick, vel = q.popleft()
                    track["notes"].append({
                        "pitch": d1,
                        "start_beat": round(tick / tpqn, 3),
                        "duration": round((abs_tick - tick) / tpqn, 3),
                        "velocity": vel,
                    })
            elif msg == 0x90:  # Note-On
                pending.setdefault(d1, deque()).append((abs_tick, d2))
            elif msg == 0x80:  # Note-Off
                q = pending.get(d1)
                if q:
                    tick, vel = q.popleft()
                    track["notes"].append({
                        "pitch": d1,
                        "start_beat": round(tick / tpqn, 3),
                        "duration": round((abs_tick - tick) / tpqn, 3),
                        "velocity": vel,
                    })

        track["notes"].sort(key=lambda n: (n["start_beat"], n["pitch"]))
        if not track["program"]:
            track["program"] = 0
        # 跳过纯指挥轨（无音符、无音轨名、无 Program Change）
        if track["notes"] or had_name or had_program:
            result["tracks"].append(track)

    if result["bpm"] is None:
        result["bpm"] = 120
    return result


# ══════════════════════════════════════════════════════════════
# 子命令：generate
# ══════════════════════════════════════════════════════════════
def cmd_generate(args):
    song = load_json_input(args.input, "song.json")
    tracks = normalize_tracks(song)
    # --bpm 显式传入时优先于 song.json（保证「覆盖」语义与文档一致）
    bpm = int(args.bpm if args.bpm is not None else song.get("bpm", 120))
    if not (40 <= bpm <= 300):
        raise DataError(f"BPM 越界：{bpm}（允许 40-300）")
    num = int(song.get("time_signature", {}).get("numerator", 4)) if isinstance(song.get("time_signature"), dict) else 4
    den = int(song.get("time_signature", {}).get("denominator", 4)) if isinstance(song.get("time_signature"), dict) else 4
    name_encoding = resolve_name_encoding(args.name_encoding)
    data = build_midi(tracks, bpm, num, den, name_encoding)
    try:
        with open(args.output, "wb") as f:
            f.write(data)
    except OSError as e:
        raise UsageError(f"无法写入输出文件: {e}")
    total = sum(len(t["notes"]) for t in tracks)
    print(json.dumps({
        "ok": True,
        "output": args.output,
        "format": "MIDI Type-1",
        "tpqn": TPQN,
        "bpm": bpm,
        "name_encoding": name_encoding,
        "tracks": [{"name": t["name"], "program": t["program"], "notes": len(t["notes"])} for t in tracks],
        "note_count": total,
        "bytes": len(data),
    }, ensure_ascii=False))
    return 0


# ══════════════════════════════════════════════════════════════
# 子命令：validate
# ══════════════════════════════════════════════════════════════
def _on_grid(x):
    return abs(x * 4 - round(x * 4)) < 1e-6


def cmd_validate(args):
    song = load_json_input(args.input, "song.json")
    strict = args.strict
    errors, warnings = [], []

    if not isinstance(song, dict):
        errors.append("顶层必须是 JSON 对象")
        return _print_validate(errors, warnings, {})

    bpm = song.get("bpm", 120)
    if not isinstance(bpm, (int, float)) or not (40 <= bpm <= 300):
        errors.append(f"BPM 越界或类型错误：{bpm}（允许 40-300）")
    else:
        bpm = int(bpm)

    tracks = normalize_tracks(song, raise_on_error=False)
    if tracks is None:
        errors.append("缺少 tracks 数组或 notes 数组（二者必有其一）")
        tracks = []

    stats = {"bpm": bpm, "track_count": len(tracks), "note_count": 0,
             "total_beats": 0.0, "pitch_min": None, "pitch_max": None}

    for ti, t in enumerate(tracks):
        tname = t.get("name", f"Track {ti}")
        notes = t.get("notes")
        if not isinstance(notes, list):
            errors.append(f"[{tname}] notes 必须是数组")
            continue
        prefix = f"[{tname}]"
        for ni, n in enumerate(notes):
            where = f"{prefix} 音符#{ni + 1}"
            if not isinstance(n, dict):
                errors.append(f"{where} 必须是对象")
                continue
            pitch = n.get("pitch")
            if not isinstance(pitch, (int, float)) or isinstance(pitch, bool) or not (0 <= float(pitch) <= 127):
                errors.append(f"{where} 音高越界：{pitch}（允许 0-127）")
            else:
                p = int(round(float(pitch)))
                stats["pitch_min"] = p if stats["pitch_min"] is None else min(stats["pitch_min"], p)
                stats["pitch_max"] = p if stats["pitch_max"] is None else max(stats["pitch_max"], p)
            start = n.get("start_beat")
            if not isinstance(start, (int, float)) or isinstance(start, bool) or float(start) < 0:
                errors.append(f"{where} start_beat 非法：{start}（必须 ≥0 数字）")
            elif not _on_grid(float(start)):
                (errors if strict else warnings).append(f"{where} start_beat={start} 不在 0.25 拍网格上")
            dur = n.get("duration")
            if not isinstance(dur, (int, float)) or isinstance(dur, bool) or float(dur) <= 0:
                errors.append(f"{where} duration 非法：{dur}（必须 >0 数字）")
            elif not _on_grid(float(dur)):
                (errors if strict else warnings).append(f"{where} duration={dur} 不在 0.25 拍网格上")
            vel = n.get("velocity", 100)
            if not isinstance(vel, (int, float)) or isinstance(vel, bool) or not (1 <= float(vel) <= 127):
                errors.append(f"{where} 力度越界：{vel}（允许 1-127）")
            if isinstance(start, (int, float)) and isinstance(dur, (int, float)) and float(dur) > 0:
                stats["total_beats"] = max(stats["total_beats"], float(start) + float(dur))

        # 同音高重叠检测
        snotes = sorted(
            (n for n in notes if isinstance(n, dict)
             and isinstance(n.get("pitch"), (int, float))
             and isinstance(n.get("start_beat"), (int, float))
             and isinstance(n.get("duration"), (int, float))),
            key=lambda n: (n["start_beat"], n["pitch"]))
        open_notes = []  # (end_beat, pitch, index)
        for n in snotes:
            p, s, d = n["pitch"], n["start_beat"], n["duration"]
            for end_beat, op, oi in open_notes:
                if op == p and s < end_beat:
                    errors.append(f"[{tname}] 同音高重叠：{pitch_name(int(p))} 音符#{oi + 1} 与 #{snotes.index(n) + 1}")
            open_notes.append((s + d, p, snotes.index(n)))
        stats["note_count"] += len(notes)

    return _print_validate(errors, warnings, stats)


def _print_validate(errors, warnings, stats):
    print(json.dumps({
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }, ensure_ascii=False, indent=2))
    return 1 if errors else 0


# ══════════════════════════════════════════════════════════════
# 子命令：inspect
# ══════════════════════════════════════════════════════════════
def cmd_inspect(args):
    try:
        data = read_input(args.input, binary=True)
    except OSError as e:
        raise UsageError(f"无法读取输入文件: {e}")
    result = parse_midi(data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# ══════════════════════════════════════════════════════════════
# 子命令：scale
# ══════════════════════════════════════════════════════════════
def cmd_scale(args):
    actions = [a for a in (args.list, args.chord, args.snap, args.suggest) if a]
    if not actions:
        raise UsageError("scale 需要至少一个动作：--list / --chord / --snap / --suggest")

    out = {}
    try:
        root = parse_pitch(args.root)
    except ValueError as e:
        raise UsageError(str(e))

    if args.list:
        ivs = SCALES[args.type]
        out["root"] = pitch_name(root)
        out["root_midi"] = root
        out["scale"] = args.type
        out["notes"] = [{"name": pitch_name(root + iv), "midi": root + iv}
                        for iv in ivs if 0 <= root + iv <= 127]
    if args.chord:
        tones = [t for t in chord_tones(root, args.chord) if 0 <= t <= 127]
        out["root"] = pitch_name(root)
        out["chord"] = args.chord
        out["tones"] = [{"name": pitch_name(t), "midi": t} for t in tones]
    if args.snap:
        snapped = []
        for s in args.snap:
            try:
                p = parse_pitch(s)
                sp = snap_to_scale(p, root, args.type)
                snapped.append({"original": p, "original_name": pitch_name(p),
                                "midi": sp, "name": pitch_name(sp)})
            except ValueError as e:
                raise UsageError(str(e))
        out["snapped"] = snapped
    if args.suggest:
        try:
            pcs = sorted({parse_pitch(s) % 12 for s in args.suggest.split(",")})
        except ValueError as e:
            raise UsageError(str(e))
        if not pcs:
            raise UsageError("--suggest 需要至少一个音高（逗号分隔）")
        scored = []
        for r in range(12):
            for st, ivs in SCALES.items():
                scale_pcs = {(r + iv) % 12 for iv in ivs}
                matched = len(set(pcs) & scale_pcs)
                coverage = matched / len(pcs) * 100
                if coverage > 0:
                    scored.append({"root": NOTE_NAMES[r], "root_midi": r + 60,
                                   "scale": st, "matched": matched,
                                   "total": len(pcs), "coverage": round(coverage, 1)})
        scored.sort(key=lambda x: (-x["coverage"], -x["matched"]))
        out["input_pitch_classes"] = [NOTE_NAMES[p] for p in pcs]
        out["suggestions"] = scored[:5]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# ══════════════════════════════════════════════════════════════
# 子命令：analyze
# ══════════════════════════════════════════════════════════════
def cmd_analyze(args):
    song = load_json_input(args.input, "song.json")
    tracks = normalize_tracks(song)
    all_notes = []
    for t in tracks:
        for n in t.get("notes", []):
            if isinstance(n, dict):
                all_notes.append(n)
    if not all_notes:
        print(json.dumps({"score": 0, "summary": "暂无音符可分析",
                          "suggestions": ["先添加一些音符再分析"]}, ensure_ascii=False))
        return 0

    chords = []
    if args.chords:
        cdata = load_json_input(args.chords, "chords.json")
        chords = cdata.get("chords", []) if isinstance(cdata, dict) else []
        for c in chords:
            try:
                c["root"] = parse_pitch(c.get("root", 60))
            except (ValueError, TypeError):
                raise DataError(f"和弦定义非法: {c!r}")

    chord_tone_hits, chord_tone_total = 0, 0
    strong_hits, strong_total = 0, 0
    for n in all_notes:
        try:
            beat = float(n["start_beat"])
        except (KeyError, TypeError, ValueError):
            continue
        chord = next((c for c in chords
                      if float(c.get("start_beat", 0)) <= beat
                      < float(c.get("start_beat", 0)) + float(c.get("duration", 4))), None)
        if chord:
            chord_tone_total += 1
            tones_pc = {t % 12 for t in chord_tones(chord["root"], chord.get("type", "maj"))}
            hit = int(n.get("pitch", 0)) % 12 in tones_pc
            if hit:
                chord_tone_hits += 1
            # 强拍（4/4 的第 1、3 拍）单独统计——这是规则 2 的核心要求
            beat_in_bar = beat % 4
            if abs(beat_in_bar - round(beat_in_bar)) < 0.01 and round(beat_in_bar) in (0, 2):
                strong_total += 1
                if hit:
                    strong_hits += 1

    dur_counts = {}
    for n in all_notes:
        d = round(float(n.get("duration", 1)), 3)
        dur_counts[d] = dur_counts.get(d, 0) + 1
    unique_durs = len(dur_counts)

    vels = [int(n.get("velocity", 100)) for n in all_notes]
    vel_min, vel_max, vel_spread = min(vels), max(vels), max(vels) - min(vels)

    srt = sorted(all_notes, key=lambda n: (float(n.get("start_beat", 0)), int(n.get("pitch", 0))))
    rest_count = back_to_back = 0
    for i in range(1, len(srt)):
        prev_end = float(srt[i - 1]["start_beat"]) + float(srt[i - 1].get("duration", 1))
        next_start = float(srt[i]["start_beat"])
        if next_start - prev_end > 0.2:
            rest_count += 1
        if next_start - prev_end < 0.01:
            back_to_back += 1

    pitches = [int(n["pitch"]) for n in srt]
    leap_count = step_count = 0
    for i in range(1, len(pitches)):
        diff = abs(pitches[i] - pitches[i - 1])
        if diff <= 2:
            step_count += 1
        elif diff >= 4:
            leap_count += 1

    suggestions = []
    rate = chord_tone_hits / chord_tone_total if chord_tone_total else 0
    strong_rate = strong_hits / strong_total if strong_total else None
    if strong_total > 0 and strong_rate < 0.6:
        suggestions.append(f"强拍(第1、3拍)上的音符与和弦音匹配率仅 {strong_rate * 100:.0f}%，建议检查和弦进行定义，让强拍音符落在和弦音上")
    elif strong_total == 0 and chord_tone_total > 0 and rate < 0.6:
        suggestions.append(f"音符与和弦音匹配率仅 {rate * 100:.0f}%，建议检查和弦进行定义，让强拍音符落在和弦音上")
    if unique_durs < 3:
        suggestions.append(f"节奏缺少变化，仅用了 {unique_durs} 种时值。建议至少混用 3 种不同时值 (0.25/0.5/0.75/1.0/1.5/2.0)")
    if vel_spread < 15:
        suggestions.append(f"力度变化太小（范围仅 {vel_spread}），真人演奏至少需要 ±15 的动态范围")
    if back_to_back > len(all_notes) * 0.6:
        suggestions.append(f"音符连接太紧密（{back_to_back}/{len(all_notes)} 连续无休止），需要更多呼吸空间")
    if rest_count < 3 and len(all_notes) > 8:
        suggestions.append(f"只有 {rest_count} 处休止，建议每 4 小节至少 2 处明显停顿")
    if leap_count > step_count * 2:
        suggestions.append(f"跳进过多（{leap_count} 次跳进 vs {step_count} 次级进），旋律不够连贯")

    out_of_scale = None
    if args.key_root:
        try:
            kroot = parse_pitch(args.key_root)
            ktype = args.key_type or "major"
            scale_pcs = {(kroot + iv) % 12 for iv in SCALES.get(ktype, SCALES["major"])}
            bad = [n for n in all_notes if int(n.get("pitch", 0)) % 12 not in scale_pcs]
            if bad:
                out_of_scale = {"count": len(bad), "rate": f"{len(bad) / len(all_notes) * 100:.0f}%"}
                if len(bad) / len(all_notes) > 0.2:
                    suggestions.append(f"有 {len(bad)} 个音符超出 {NOTE_NAMES[kroot % 12]} {ktype} 音阶（占 {len(bad) / len(all_notes) * 100:.0f}%），建议检查调式或修正音高")
        except ValueError as e:
            raise UsageError(str(e))

    score = 5.0
    if strong_total > 0:
        score += min(2, strong_rate * 2)  # 规则 2 核心：强拍和弦音
    elif chord_tone_total > 0:
        score += min(2, rate * 2)
    score += min(2, unique_durs / 3)
    score += min(1, vel_spread / 20)
    score += min(1, max(0, 1 - back_to_back / len(all_notes)) * 2)
    score = max(0, min(10, round(score)))

    print(json.dumps({
        "score": score,
        "summary": "优秀" if score >= 8 else "良好" if score >= 6 else "一般" if score >= 4 else "需要改进",
        "details": {
            "total_notes": len(all_notes),
            "track_count": len(tracks),
            "unique_durations": unique_durs,
            "duration_distribution": dur_counts,
            "velocity_range": f"{vel_min}-{vel_max}",
            "velocity_spread": vel_spread,
            "rests_between_notes": rest_count,
            "back_to_back_count": back_to_back,
            "leaps": leap_count,
            "steps": step_count,
            "leap_step_ratio": f"{leap_count / step_count:.1f}" if step_count else "∞",
            "chord_tone_rate": f"{rate * 100:.0f}%" if chord_tone_total > 0 else "无和弦定义",
            "strong_beat_chord_tone_rate": f"{strong_rate * 100:.0f}%" if strong_total > 0 else "无强拍数据",
            "out_of_scale": out_of_scale,
        },
        "suggestions": suggestions or ["当前旋律各项指标良好！"],
    }, ensure_ascii=False, indent=2))
    return 0


# ══════════════════════════════════════════════════════════════
# 通用辅助
# ══════════════════════════════════════════════════════════════
def read_input(path, binary=False):
    if path == "-":
        return sys.stdin.buffer.read() if binary else sys.stdin.read()
    with open(path, "rb" if binary else "r", encoding=None if binary else "utf-8") as f:
        return f.read()


def load_json_input(path, what):
    try:
        raw = read_input(path)
    except OSError as e:
        raise UsageError(f"无法读取 {what}: {e}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DataError(f"{what} JSON 解析失败: {e}")
    return data


def normalize_tracks(song, raise_on_error=True):
    """统一 tracks / 旧版 notes 两种输入格式。"""
    tracks = song.get("tracks")
    if tracks is None and isinstance(song.get("notes"), list):
        tracks = [{"name": "Piano", "channel": 0, "program": 0, "notes": song["notes"]}]
    if not isinstance(tracks, list) or not tracks:
        if raise_on_error:
            raise DataError("缺少 tracks 数组或 notes 数组（二者必有其一）")
        return None
    norm = []
    for i, t in enumerate(tracks):
        if not isinstance(t, dict):
            raise DataError(f"track[{i}] 必须是对象")
        norm.append({
            "name": str(t.get("name", f"Track {i + 1}")),
            "channel": int(t.get("channel", i)),
            "program": int(t.get("program", 0)),
            "notes": t.get("notes") if isinstance(t.get("notes"), list) else [],
        })
    return norm


def build_parser():
    parser = argparse.ArgumentParser(
        prog="amr-midi",
        description="AMIDI Skills 执行层：零依赖 MIDI 工具包（generate/validate/inspect/scale/analyze）")
    parser.add_argument("--version", action="version", version="amr-midi 1.1.0")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="<子命令>")

    p = sub.add_parser("generate", help="song.json → 标准 MIDI 文件（Type-1, TPQN=480）")
    p.add_argument("--input", required=True, help="song.json 路径，'-' 读 stdin")
    p.add_argument("--output", required=True, help="输出 .mid 文件路径")
    p.add_argument("--bpm", type=int, default=None, help="覆盖 song.json 中的 BPM（40-300）")
    p.add_argument("--name-encoding", default="auto",
                   help="音轨名编码: auto(默认, Windows 用系统 ANSI 码页如 GBK)/utf-8/gbk/...")

    p = sub.add_parser("validate", help="校验 song.json 数据合法性")
    p.add_argument("--input", required=True, help="song.json 路径，'-' 读 stdin")
    p.add_argument("--strict", action="store_true", help="非 0.25 网格音符视为错误（默认警告）")

    p = sub.add_parser("inspect", help="解析 .mid 文件为音符列表 JSON")
    p.add_argument("--input", required=True, help=".mid 文件路径")

    p = sub.add_parser("scale", help="音阶/和弦工具：列音、和弦音、吸附、调式推测")
    p.add_argument("--root", default="C4", help="根音：音名（C4）或 MIDI 数字（60）")
    p.add_argument("--type", default="major", choices=sorted(SCALES), help="音阶类型")
    p.add_argument("--list", action="store_true", help="列出音阶音")
    p.add_argument("--chord", metavar="TYPE", choices=sorted(CHORDS), help="列出和弦音")
    p.add_argument("--snap", nargs="*", metavar="PITCH", help="把音高吸附到音阶")
    p.add_argument("--suggest", metavar="PITCHES", help="逗号分隔音高，推测调式")

    p = sub.add_parser("analyze", help="旋律质量分析：0-10 评分 + 改进建议")
    p.add_argument("--input", required=True, help="song.json 路径，'-' 读 stdin")
    p.add_argument("--chords", default=None, help="可选 chords.json（和弦进行定义）")
    p.add_argument("--key-root", default=None, help="可选：检查出界音符的调式根音（如 C4）")
    p.add_argument("--key-type", default="major", choices=sorted(SCALES), help="配合 --key-root 使用")
    return parser


def main(argv=None):
    # 统一 UTF-8 IO：JSON 规范为 UTF-8，避免管道/重定向时被系统码页误转
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args(argv)
    try:
        return {
            "generate": cmd_generate,
            "validate": cmd_validate,
            "inspect": cmd_inspect,
            "scale": cmd_scale,
            "analyze": cmd_analyze,
        }[args.cmd](args)
    except DataError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1
    except UsageError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
