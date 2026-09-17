#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aria-midi — Aria Skills 执行层：零依赖 MIDI 工具包 CLI（仅 Python 标准库）。

子命令：
  generate   song.json 音符数据 -> 标准 MIDI 文件（Type-1，TPQN=480）
  validate   校验 song.json 的 schema / 音域 / 力度 / 量化 / 重叠
  inspect    解析现有 .mid 文件 -> 音符列表 JSON（零依赖解析器）
  scale      音阶 / 和弦工具：列音、和弦音、调式吸附、调式推测
  analyze    旋律质量分析：0-10 评分 + 乐句结构分析 + 中文改进建议

约定：
  - 所有子命令 JSON 进 JSON 出（generate 输出二进制 .mid 文件）
  - --input 支持 "-" 从 stdin 读取（generate/validate/analyze）
  - 退出码：0 成功 / 1 数据校验失败 / 2 用法或 IO 错误
  - generate 的 --output 可省：song.json 顶层有 name（或给 --name）时
    派生为 <输入目录>/<歌名>.mid，并把歌名写成 MIDI 序列名
"""

import argparse
import json
import locale
import math
import os
import re
import struct
import sys
from collections import Counter, deque

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


def slugify(name, max_chars=60):
    """把歌曲名规范化成安全的文件名主干。

    中文可直接保留（UTF-8 文件系统没问题），只处理真正会出事的字符：
    路径分隔符与 Windows 保留字符、控制字符、结尾的点/空格（Windows 会静默截断）。
    结果为空时回退为 "song"，避免产出无名文件或路径穿越。
    """
    s = "".join("_" if (c in '<>:"/\\|?*' or ord(c) < 32) else c for c in str(name))
    s = re.sub(r"\s+", " ", s).strip().strip(". ")
    if len(s) > max_chars:                 # 多数文件系统单段上限 255 字节，中文 3 字节/字
        s = s[:max_chars].strip()
    return s or "song"


def resolve_output_path(output, name, raw_name, input_path, outdir):
    """决定 .mid 输出路径。

    优先级：--output > (--name 或 song.json 顶层 name) 派生 > 报错。
    派生规则：<outdir>/<slug(歌名)>.mid
    --outdir 未给时取 --input 所在目录 —— 「每首歌一个目录」的布局下，
    直接 `generate --input 未寄出的信/song.json` 就会写出
    `未寄出的信/未寄出的信.mid`，无需重复敲路径。
    --input 为 stdin（'-'）时退回当前目录。
    """
    if output:
        return output
    if not raw_name:
        raise UsageError("缺少输出路径：请给 --output，"
                         "或在 song.json 顶层写 \"name\"（也可用 --name 指定）")
    if outdir:
        target_dir = outdir
    elif input_path and input_path != "-":
        target_dir = os.path.dirname(os.path.abspath(input_path))
    else:
        target_dir = "."
    if not os.path.isdir(target_dir):
        raise UsageError(f"输出目录不存在: {target_dir}")
    return os.path.join(target_dir, slugify(name) + ".mid")


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


def build_conductor_track(bpm, num, den, seq_name=None, name_encoding="utf-8"):
    events = []
    # 序列名（meta 0x03）：DAW/播放器会把它当作曲名显示。
    # 不传时完全不写这个事件，未命名作品的输出保持与旧版逐字节一致。
    if seq_name:
        raw = _encode_name_bytes(str(seq_name), name_encoding)
        if len(raw) > 64:                  # 与音轨名同样截断，且不切断多字节字符
            raw = raw[:64]
            while raw and (raw[-1] & 0xC0) == 0x80:
                raw = raw[:-1]
        events.append((0, b"\xff\x03" + encode_vlq(len(raw)) + raw))
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


def build_midi(tracks, bpm, num=4, den=4, name_encoding="utf-8", seq_name=None):
    conductor = build_conductor_track(bpm, num, den, seq_name, name_encoding)
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
    # 歌曲名：--name 优先于 song.json 顶层的 name。同时用于派生文件名与写入序列名。
    raw_name = args.name or song.get("name")
    out_path = resolve_output_path(args.output, raw_name, raw_name,
                                   args.input, args.outdir)
    data = build_midi(tracks, bpm, num, den, name_encoding,
                      seq_name=raw_name or None)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if not os.path.isdir(out_dir):
        raise UsageError(f"输出目录不存在: {out_dir}")
    try:
        with open(out_path, "wb") as f:
            f.write(data)
    except OSError as e:
        raise UsageError(f"无法写入输出文件: {e}")
    total = sum(len(t["notes"]) for t in tracks)
    print(json.dumps({
        "ok": True,
        "output": out_path,
        "format": "MIDI Type-1",
        "tpqn": TPQN,
        "bpm": bpm,
        "name": slugify(raw_name) if raw_name else None,
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
# 旋律性豁免风格：这些风格以跳进/琶音为特征，不做「级进占比」硬约束
_LEAPY_STYLES = {"jazz", "arpeggio", "blues", "edm", "lofi"}


def _select_analysis_tracks(tracks, args):
    """选择评分音轨。--all-tracks 全轨；--track 按名称匹配；默认取平均音高最高的旋律轨。"""
    if getattr(args, "all_tracks", False):
        return tracks
    if getattr(args, "track", None):
        for t in tracks:
            if args.track in t["name"]:
                return [t]
        raise DataError(f"未找到名称含 {args.track!r} 的音轨（可用 --all-tracks 分析全部音轨）")
    if len(tracks) <= 1:
        return tracks
    best, best_avg = None, None
    for t in tracks:
        ns = [n for n in t.get("notes", []) if isinstance(n, dict)]
        if not ns:
            continue
        avg = sum(float(n.get("pitch", 60)) for n in ns) / len(ns)
        if best_avg is None or avg > best_avg:
            best_avg, best = avg, t
    return [best] if best is not None else tracks


def _motif_reuse(pitches):
    """检测 4 音动机（3 音程窗口）重复次数；纯音阶（音程全同）不计为动机。"""
    if len(pitches) < 5:
        return 0
    intervals = [pitches[i + 1] - pitches[i] for i in range(len(pitches) - 1)]
    if len(set(intervals)) == 1:
        return 0
    seen, reused = set(), 0
    for i in range(len(intervals) - 2):
        tri = (intervals[i], intervals[i + 1], intervals[i + 2])
        if tri in seen:
            reused += 1
        else:
            seen.add(tri)
    return reused


def _segment_phrases(srt, gap_thresh=0.5, long_note=2.0):
    """按休止与长音把旋律切成乐句（大 IOI / 长音是乐句边界的强预测因子，Pearce et al. 2010）。

    边界判定：音符间隙 >= gap_thresh 拍，或音符时值 >= long_note 拍（长音即句尾）。
    输入为按 start_beat 排序的音符列表；返回乐句列表，每个乐句是音符 dict 列表。
    """
    phrases, cur = [], []
    for i, n in enumerate(srt):
        cur.append(n)
        end = float(n.get("start_beat", 0)) + float(n.get("duration", 1))
        if i + 1 < len(srt):
            gap = float(srt[i + 1].get("start_beat", 0)) - end
            boundary = gap >= gap_thresh or float(n.get("duration", 1)) >= long_note
        else:
            boundary = True
        if boundary:
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    return phrases


def _phrase_contour(phrase):
    """乐句的音程方向轮廓（1 上行 / -1 下行 / 0 同音），用于跨乐句相似性比较。"""
    ps = [int(n.get("pitch", 60)) for n in phrase]
    return tuple(1 if ps[i + 1] > ps[i] else -1 if ps[i + 1] < ps[i] else 0
                 for i in range(len(ps) - 1))


def _analyze_bar_structure(srt, beats_per_bar=4):
    """小节级结构分析 —— 不依赖休止切分，对循环式与通谱式作品都成立。

    存在的理由：乐句级分析靠「音隔 ≥0.5 拍」切分，遇到**循环式作品**（旋律几乎
    无休止，如 DAW 导出的氛围/lo-fi）会把整曲合并成一两个巨型乐句，小节内的同头
    结构完全落不进切分里 —— 实测一首头细胞重复率 88% 的人写作品，被乐句级分析
    判成「缺少同头复用」。本函数改用固定窗口（小节）取样：

      rhythm_template  每小节的节奏骨架（各音起点在小节内的偏移序列）
      head_cell        每小节前 3 个音的音高序列

    并据两条轴的相对强度判定结构类型。
    """
    bars = {}
    for n in srt:
        sb = float(n.get("start_beat", 0))
        bars.setdefault(int(sb // beats_per_bar), []).append(n)
    bars = {b: sorted(v, key=lambda x: float(x.get("start_beat", 0)))
            for b, v in bars.items() if len(v) >= 3}       # 音太少的残句不参与
    n = len(bars)
    if n < 4:
        return None
    base = min(bars)
    rhythm = {b: tuple(round(float(x["start_beat"]) - b * beats_per_bar, 2) for x in v)
              for b, v in bars.items()}
    heads = {b: tuple(int(x.get("pitch", 60)) for x in v[:3]) for b, v in bars.items()}
    u_rh, u_hd = len(set(rhythm.values())), len(set(heads.values()))
    top_rh = max(Counter(rhythm.values()).values())
    top_hd = max(Counter(heads.values()).values())
    head_reuse = 1 - u_hd / n
    rhythm_reuse = 1 - u_rh / n
    # 哪个轴在主导：差值 0.15 以内算两轴并重
    d = head_reuse - rhythm_reuse
    if d >= 0.15:
        kind = "音高主导（同头异尾）"
    elif d <= -0.15:
        kind = "节奏主导（固定节奏变奏）"
    else:
        kind = "双轴并重（严格循环）"
    return {
        "bars_with_melody": n,
        "first_bar": base + 1,
        "rhythm_template_count": u_rh,
        "rhythm_reuse": round(rhythm_reuse, 3),
        "top_rhythm_coverage": round(top_rh / n, 3),
        "head_cell_count": u_hd,
        "head_reuse": round(head_reuse, 3),
        "top_head_coverage": round(top_hd / n, 3),
        "structure_kind": kind,
        "note": "小节级指标，与休止无关；对循环式与通谱式作品都成立",
    }


def _analyze_structure(srt, key_pc=None):
    """模块化乐句结构分析（动机→乐句→乐段的连贯性维度）。

    检测项：
      - 乐句切分：按休止/长音分段（period/sentence/起承转合 的物质基础是「可数的乐句」）
      - 跨乐句轮廓复用：乐句开头轮廓相同 = AABA/起承转合/period 的「同头」特征
      - 高潮位置：全曲最高音应落在 35%–90% 区间（拱形轮廓经验值），过早出现 = 后主歌失去期待
      - 终止稳定性（给定调性时）：末乐句落主音 = 收束；倒数乐句落属音 = 半终止铺垫

    返回 (structure_dict, suggestions_list, structure_score_0_to_10)。
    """
    if len(srt) < 6:
        return None, [], None
    phrases = _segment_phrases(srt)
    first_start = float(srt[0].get("start_beat", 0))
    total_beats = float(srt[-1]["start_beat"]) + float(srt[-1].get("duration", 1)) - first_start

    # 高潮位置：最高音首次出现的相对位置
    peak_pitch = max(int(n.get("pitch", 60)) for n in srt)
    peak_beat = min(float(n.get("start_beat", 0)) for n in srt if int(n.get("pitch", 60)) == peak_pitch)
    climax_pos = (peak_beat - first_start) / total_beats if total_beats > 0 else 0.0

    # 跨乐句轮廓复用：两两比较乐句开头 2 个音程方向（「同头变尾」是 period/起承转合的核心）
    contours = [_phrase_contour(p) for p in phrases]
    contour_reuse = 0
    for i in range(len(contours)):
        for j in range(i + 1, len(contours)):
            a, b = contours[i], contours[j]
            if len(a) >= 2 and len(b) >= 2 and a[:2] == b[:2]:
                contour_reuse += 1

    # 乐句结束音（每句最后一个音高的 pitch class）
    endings = [int(p[-1].get("pitch", 60)) % 12 for p in phrases if p]
    final_on_tonic = None
    penult_on_dominant = None
    if key_pc is not None and endings:
        final_on_tonic = endings[-1] == key_pc % 12
        if len(endings) >= 2:
            penult_on_dominant = endings[-2] in {(key_pc + 7) % 12, (key_pc + 2) % 12}

    # 小节级结构（与休止无关）—— 用来给乐句级结论做交叉校验：
    # 乐句级抓不到同头时，若小节级重复度很高，说明只是切分没对上，不是真缺结构
    bar_info = _analyze_bar_structure(srt)
    bar_structured = bool(bar_info and max(bar_info["head_reuse"],
                                           bar_info["rhythm_reuse"]) >= 0.5)

    suggestions = []
    points, max_points = 0.0, 8.0
    if len(phrases) >= 2:
        points += 3.0 if len(phrases) <= 8 else 2.0
    else:
        points += 1.0
        if len(srt) >= 8 and not bar_structured:
            suggestions.append(
                "整段旋律只切出 1 个乐句（全程无 ≥0.5 拍休止或 ≥2 拍长音），"
                "听感会一口气喘不上来；按 period 4+4 / sentence 2+2+4 / 起承转合 四句体切分乐句")
    if contour_reuse > 0:
        points += 3.0
    elif bar_structured:
        # 乐句级因无休止而切分失效，但小节级重复成立 —— 结构确实存在，按同头计分。
        # 这是**严格增量**：只补回被误判扣掉的分，不改变任何本来就得分的作品。
        points += 3.0
        suggestions.append(
            f"乐句级未检出同头（旋律无休止，按音隔切分失效），但小节级结构明确："
            f"{bar_info['structure_kind']} —— 开头细胞重复率 {bar_info['head_reuse']*100:.0f}%、"
            f"节奏型重复率 {bar_info['rhythm_reuse']*100:.0f}%（{bar_info['bars_with_melody']} 个有旋律小节）。"
            "这是循环式写法，不是缺陷；若想增强旋律辨识度，可在保持骨架的前提下多换尾句")
    elif len(phrases) >= 3:
        suggestions.append(
            f"{len(phrases)} 个乐句的开头轮廓两两不同，缺少「同头」复用；"
            "AABA / 起承转合 / period 都靠乐句开头相同、结尾变化建立连贯性，"
            "建议让相邻乐句共享前 2-3 个音的音程走向")
    if total_beats >= 16:
        if 0.35 <= climax_pos <= 0.9:
            points += 2.0
        elif climax_pos < 0.3:
            suggestions.append(
                f"全曲最高音出现在前 {climax_pos * 100:.0f}% 处，高潮来得太早，后段失去期待感；"
                "建议把最高音安排在全曲 1/2–4/5 处（拱形轮廓），或副歌偏后位置")
        else:
            points += 1.0
    else:
        points += 2.0  # 短旋律不做高潮位置约束
    if key_pc is not None and endings:
        max_points += 2.0
        if final_on_tonic:
            points += 2.0
        else:
            suggestions.append(
                f"末乐句结束音 {NOTE_NAMES[endings[-1]]} 不是主音 {NOTE_NAMES[key_pc % 12]}，"
                "全曲缺少收束感；若不是有意的开放结尾，建议末句落在主音（长音 ≥2 拍）")
        if len(endings) >= 2 and not penult_on_dominant:
            suggestions.append(
                "倒数乐句的结束音不是属音/上主音，段尾缺少半终止铺垫；"
                "问答句结构里前句停属音（开放）、后句停主音（收束）是最省力的连贯性手段")

    structure_score = round(points / max_points * 10, 1) if max_points else None
    info = {
        "phrase_count": len(phrases),
        "phrase_lengths": [len(p) for p in phrases],
        "phrase_endings_pc": endings,
        "contour_reuse_pairs": contour_reuse,
        "climax_position": f"{climax_pos * 100:.0f}%",
        "final_on_tonic": final_on_tonic,
        "bar_structure": bar_info,
    }
    return info, suggestions, structure_score


def cmd_analyze(args):
    song = load_json_input(args.input, "song.json")
    tracks = normalize_tracks(song)

    all_track_notes = [n for t in tracks for n in t.get("notes", []) if isinstance(n, dict)]

    analysis_tracks = _select_analysis_tracks(tracks, args)
    all_notes = [n for t in analysis_tracks for n in t.get("notes", []) if isinstance(n, dict)]
    if not all_notes:
        print(json.dumps({"score": 0, "summary": "暂无音符可分析",
                          "suggestions": ["先添加一些音符再分析"]}, ensure_ascii=False))
        return 0

    style = (args.style or "melodic").lower()
    style_exempt = style in _LEAPY_STYLES

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
    step_count = leap_count = 0
    for i in range(1, len(pitches)):
        diff = abs(pitches[i] - pitches[i - 1])
        if diff <= 2:
            step_count += 1  # 大二度以内 = 级进
        else:
            leap_count += 1  # ≥ 小三度 = 跳进

    total_moves = step_count + leap_count
    step_ratio = step_count / total_moves if total_moves else 0.0

    motif_reused = _motif_reuse(pitches)

    suggestions = []
    rate = chord_tone_hits / chord_tone_total if chord_tone_total else 0
    strong_rate = strong_hits / strong_total if strong_total else None
    if strong_total > 0 and strong_rate < 0.6:
        suggestions.append(f"强拍(第1、3拍)上的音符与和弦音匹配率仅 {strong_rate * 100:.0f}%，建议检查和弦进行定义；若是挂留/倚音/蓝调音的有意表达，可保留")
    elif strong_total == 0 and chord_tone_total > 0 and rate < 0.6:
        suggestions.append(f"音符与和弦音匹配率仅 {rate * 100:.0f}%，建议检查和弦进行定义；若是挂留/倚音/蓝调音的有意表达，可保留")
    if total_moves >= 4 and not style_exempt:
        # 先排除「单轨多声部」这个输入侧问题：低音与旋律挤在同一轨时，相邻音符会
        # 在跨越声部处产生十几半音的大跳，级进占比随之崩到个位数 —— 此时报「旋律
        # 断裂」是答错了题，真正该做的是先拆声部。判据用**平均音程跨度**：混声部的
        # 均值通常 >7 半音，而爵士/琶音式跳进的均值一般在 3–5。
        mean_iv = (sum(abs(pitches[i] - pitches[i - 1]) for i in range(1, len(pitches)))
                   / total_moves) if total_moves else 0.0
        multi_voice = mean_iv >= 7.0 and step_ratio < 0.25
        if multi_voice:
            suggestions.append(
                f"平均音程跨度达 {mean_iv:.1f} 半音、级进仅 {step_ratio * 100:.0f}% —— "
                "这个特征通常不是旋律本身的问题，而是**低音/和弦/旋律被压在同一个音轨里**，"
                "跨声部的相邻音造成了虚假大跳。请先按音区拆声部（或改用多轨 MIDI）再评分，"
                "否则本轨的各项旋律指标都不可信")
        elif step_ratio < 0.4:
            suggestions.append(f"级进占比仅 {step_ratio * 100:.0f}%（跳进 {leap_count} 次 vs 级进 {step_count} 次），旋律断裂、机器味明显；除非是爵士/琶音/蓝调风格，否则应把跳进控制在级进的 1/3 以内")
        elif step_ratio < 0.6:
            suggestions.append(f"级进占比偏低（{step_ratio * 100:.0f}%），建议多数音程用大二度以内的级进，让旋律更可唱")
    if unique_durs < 3:
        suggestions.append(f"节奏缺少变化，仅用了 {unique_durs} 种时值。建议至少混用 3 种不同时值 (0.25/0.5/0.75/1.0/1.5/2.0)")
    if vel_spread < 15:
        suggestions.append(f"力度变化太小（范围仅 {vel_spread}），真人演奏至少需要 ±15 的动态范围")
    if back_to_back > len(all_notes) * 0.6:
        suggestions.append(f"音符连接太紧密（{back_to_back}/{len(all_notes)} 连续无休止），需要更多呼吸空间；若是 EDM/Lo-fi 连续律动，可保留")
    if rest_count < 3 and len(all_notes) > 8:
        suggestions.append(f"只有 {rest_count} 处休止，建议每 4 小节至少 2 处明显停顿")
    if motif_reused == 0 and len(pitches) >= 8:
        suggestions.append("缺少动机重复：旋律像流水账，建议设计 2-5 音动机并发展（重复/模进/变奏）")

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
                    suggestions.append(f"有 {len(bad)} 个音符超出 {NOTE_NAMES[kroot % 12]} {ktype} 音阶（占 {len(bad) / len(all_notes) * 100:.0f}%），建议检查调式或修正音高；若是借调/半音经过音，可保留")
        except ValueError as e:
            raise UsageError(str(e))

    # ── 模块化乐句结构分析（连贯性维度，独立于总分，作为第三栏报告）──
    key_pc = None
    if args.key_root:
        try:
            key_pc = parse_pitch(args.key_root) % 12
        except ValueError:
            key_pc = None
    structure_info, structure_sugs, structure_score = _analyze_structure(srt, key_pc)
    suggestions.extend(structure_sugs)

    # ── 评分（总分 10）：基础分降到 2.0，级进占比升为核心指标 ──
    score = 2.0
    if strong_total > 0:
        score += min(1.5, strong_rate * 1.5)  # 规则 2：强拍和弦音（基础正确性）
    elif chord_tone_total > 0:
        score += min(1.5, rate * 1.5)
    if style_exempt:
        score += 1.25  # 跳进型风格：级进占比中性
    elif step_ratio >= 0.6:
        score += 2.5  # 级进占比 ≥60% 拿满（规则 5，可唱性核心）
    elif step_ratio >= 0.4:
        score += 1.5
    else:
        score += 0.5  # 严重断裂
    score += min(1.5, unique_durs / 3)
    score += min(1.0, vel_spread / 20)
    score += min(1.0, max(0.0, 1.0 - back_to_back / len(all_notes)) * 2)
    score += 0.5 if motif_reused > 0 else 0.0  # 动机发展（规则 1）

    # 旋律断裂惩罚：级进占比 <40%（跳进为主）是机器味强信号
    if not style_exempt and total_moves >= 6 and step_ratio < 0.4:
        score -= 2.0
    # 跳进过度惩罚：跳进是级进的 2 倍以上
    if not style_exempt and total_moves >= 6 and leap_count > step_count * 2:
        score -= 1.5

    score = max(0.0, min(10.0, round(score)))

    # ── 子分：技术分（规则 2/3/4/7 机械正确性）与音乐性分（规则 1/5 旋律性）──
    # 拆成两栏，避免「技术指标刷分」掩盖旋律断裂，两者都需达标才放行
    tech = 0.0
    if strong_total > 0:
        tech += min(3.0, strong_rate * 3)
    elif chord_tone_total > 0:
        tech += min(3.0, rate * 3)
    tech += min(2.5, (unique_durs / 3) * 2.5)  # 时值多样
    tech += min(2.0, (vel_spread / 20) * 2.0)  # 力度范围
    tech += min(2.5, max(0.0, 1.0 - back_to_back / len(all_notes)) * 2 * 2.5)  # 呼吸空间
    tech = round(min(10.0, tech), 1)

    music = 0.0
    if style_exempt:
        music += 4.0  # 跳进型风格中性
    elif step_ratio >= 0.6:
        music += 6.0
    elif step_ratio >= 0.4:
        music += 3.5
    else:
        music += 1.0
    music += 4.0 if motif_reused > 0 else 0.0  # 动机发展
    if not style_exempt and total_moves >= 6 and step_ratio < 0.4:
        music -= 2.0  # 旋律断裂
    if not style_exempt and total_moves >= 6 and leap_count > step_count * 2:
        music -= 1.5  # 跳进过度
    music = round(max(0.0, min(10.0, music)), 1)

    passed = tech >= 6.0 and music >= 6.0

    print(json.dumps({
        "score": score,
        "technical_score": tech,
        "musicality_score": music,
        "structure_score": structure_score,
        "passed": passed,
        "summary": "优秀" if score >= 8 else "良好" if score >= 6 else "一般" if score >= 4 else "需要改进",
        "details": {
            "analyzed_track": analysis_tracks[0]["name"] if len(analysis_tracks) == 1 else "全部音轨",
            "analyzed_notes": len(all_notes),
            "total_notes": len(all_track_notes),
            "track_count": len(tracks),
            "style": style,
            "unique_durations": unique_durs,
            "duration_distribution": dur_counts,
            "velocity_range": f"{vel_min}-{vel_max}",
            "velocity_spread": vel_spread,
            "rests_between_notes": rest_count,
            "back_to_back_count": back_to_back,
            "steps": step_count,
            "leaps": leap_count,
            "step_ratio": f"{step_ratio * 100:.0f}%",
            "leap_step_ratio": f"{leap_count / step_count:.1f}" if step_count else "∞",
            "motif_reuse": motif_reused,
            "chord_tone_rate": f"{rate * 100:.0f}%" if chord_tone_total > 0 else "无和弦定义",
            "strong_beat_chord_tone_rate": f"{strong_rate * 100:.0f}%" if strong_total > 0 else "无强拍数据",
            "out_of_scale": out_of_scale,
            "structure": structure_info,
        },
        "suggestions": suggestions or ["当前旋律各项指标良好！"],
    }, ensure_ascii=False, indent=2))
    return 0


# ══════════════════════════════════════════════════════════════
# 子命令：compare（风格锚定）
# ══════════════════════════════════════════════════════════════
def _style_profile(notes):
    """从音符列表提取风格参数画像（用于产出与真实案例的锚定对比）。"""
    if not notes:
        return None
    pitches = [int(n["pitch"]) for n in notes]
    vels = [int(n.get("velocity", 100)) for n in notes]
    durs = [float(n.get("duration", 1)) for n in notes]
    srt = sorted(notes, key=lambda n: (float(n.get("start_beat", 0)), int(n.get("pitch", 0))))
    steps = leaps = 0
    for i in range(1, len(srt)):
        d = abs(int(srt[i]["pitch"]) - int(srt[i - 1]["pitch"]))
        if d <= 2:
            steps += 1
        else:
            leaps += 1
    total_moves = steps + leaps
    total_beats = max((float(n.get("start_beat", 0)) + float(n.get("duration", 1))) for n in notes)
    return {
        "note_count": len(notes),
        "pitch_min": min(pitches),
        "pitch_max": max(pitches),
        "pitch_span": max(pitches) - min(pitches),
        "velocity_spread": max(vels) - min(vels),
        "step_ratio": round(steps / total_moves, 3) if total_moves else 0.0,
        "density": round(len(notes) / total_beats, 3) if total_beats > 0 else 0.0,
        "short_note_ratio": round(sum(1 for d in durs if d <= 0.5) / len(durs), 3),
    }


def _pick_melody_notes(tracks):
    """选平均音高最高的轨（旋律轨）返回其音符列表。"""
    best_notes, best_avg = None, None
    for t in tracks:
        ns = [n for n in t.get("notes", []) if isinstance(n, dict)]
        if not ns:
            continue
        avg = sum(float(n.get("pitch", 60)) for n in ns) / len(ns)
        if best_avg is None or avg > best_avg:
            best_avg, best_notes = avg, ns
    return best_notes or []


def cmd_compare(args):
    song = load_json_input(args.input, "song.json")
    tracks = normalize_tracks(song)
    src_notes = _pick_melody_notes(tracks)
    src_bpm = song.get("bpm", 120)

    try:
        ref_data = read_input(args.reference, binary=True)
    except OSError as e:
        raise UsageError(f"无法读取参考文件: {e}")
    ref = parse_midi(ref_data)
    ref_notes = _pick_melody_notes(ref["tracks"])
    ref_bpm = ref["bpm"] or 120

    src_prof = _style_profile(src_notes)
    ref_prof = _style_profile(ref_notes)
    if not src_prof or not ref_prof:
        print(json.dumps({"ok": False, "error": "产出或参考缺少音符，无法对比"}, ensure_ascii=False))
        return 1

    def dim(src_val, ref_val, abs_tol, rel_tol=0.35):
        delta = round(src_val - ref_val, 3)
        ok = abs(delta) <= abs_tol or abs(delta) <= abs(ref_val) * rel_tol
        return {"source": src_val, "reference": ref_val, "delta": delta, "ok": bool(ok)}

    dims = {
        "bpm": dim(int(src_bpm), int(ref_bpm), 8),
        "step_ratio": dim(src_prof["step_ratio"], ref_prof["step_ratio"], 0.12),
        "pitch_span": dim(src_prof["pitch_span"], ref_prof["pitch_span"], 6),
        "velocity_spread": dim(src_prof["velocity_spread"], ref_prof["velocity_spread"], 12),
        "density": dim(src_prof["density"], ref_prof["density"], 1.0),
        "short_note_ratio": dim(src_prof["short_note_ratio"], ref_prof["short_note_ratio"], 0.25),
    }
    checked = [d for d in dims.values() if d["ok"] is not None]
    matched = sum(1 for d in checked if d["ok"])
    similarity = round(matched / len(checked), 3) if checked else 0.0
    # 级进占比是风格核心：严重偏离（>0.2）直接判偏离，无论其他维度是否接近
    step_fail = dims["step_ratio"]["ok"] is False and abs(dims["step_ratio"]["delta"]) > 0.2
    verdict = "风格偏离" if (step_fail or similarity < 0.6) else "风格匹配"

    print(json.dumps({
        "ok": True,
        "reference": args.reference,
        "reference_bpm": ref_bpm,
        "source_bpm": int(src_bpm),
        "dimensions": dims,
        "similarity": similarity,
        "verdict": verdict,
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
        prog="aria-midi",
        description="Aria Skills 执行层：零依赖 MIDI 工具包（generate/validate/inspect/scale/analyze）")
    parser.add_argument("--version", action="version", version="aria-midi 1.3.0")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="<子命令>")

    p = sub.add_parser("generate", help="song.json → 标准 MIDI 文件（Type-1, TPQN=480）")
    p.add_argument("--input", required=True, help="song.json 路径，'-' 读 stdin")
    p.add_argument("--output", help="输出 .mid 路径；省略时由歌曲名派生 <歌名>.mid")
    p.add_argument("--name", help="歌曲名（覆盖 song.json 顶层的 name）；决定派生文件名与序列名")
    p.add_argument("--outdir", help="派生输出时的目录；默认取 --input 所在目录")
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
    p.add_argument("--track", default=None, help="按名称指定评分音轨（默认取平均音高最高的旋律轨）")
    p.add_argument("--all-tracks", action="store_true", help="合并全部音轨评分（旧行为）")
    p.add_argument("--style", default="melodic", help="风格：melodic(默认) 或 jazz/arpeggio/blues/edm/lofi 豁免跳进约束")

    p = sub.add_parser("compare", help="风格锚定：产出 song.json 与参考 .mid 做风格参数对比")
    p.add_argument("--input", required=True, help="产出 song.json 路径，'-' 读 stdin")
    p.add_argument("--reference", required=True, help="参考 .mid 文件（如 examples/midi/tropical-demo.mid）")
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
            "compare": cmd_compare,
        }[args.cmd](args)
    except DataError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1
    except UsageError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
