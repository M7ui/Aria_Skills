#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aria 技能包 — aria-decode 解码工具（v1.0.1）

零依赖 MIDI → JSON 无损解码器（仅 Python 标准库，Python 3.8+）。

功能：
  - 无损解码 MIDI 文件全部事件：meta / 通道事件 / SysEx / 系统消息
  - SMPTE 时基与 PPQN 时基均支持
  - Tempo 变化精确换算事件秒时间戳
  - 音符聚合（跨轨道、含 channel 信息）
  - GM 音色名 / 标准 CC 控制器名 / 音高名映射
  - JSON 进出，退出码：0=成功 / 1=数据错误 / 2=用法错误

用法：
  python aria_decode.py decode --input <file.mid> [--output <file.json>] [--no-events] [--no-notes]

CLI 定位规则：本文件可按包内相对路径定位（复制到任何目录均可直接运行）。
"""

import argparse
import json
import struct
import sys
import os
from bisect import bisect_right

__version__ = "1.0.1"

# ══════════════════════════════════════════════════════════════
# 常量表
# ══════════════════════════════════════════════════════════════

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# GM1 音色名（128 项）
GM_PROGRAMS = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
    "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
    "Celesta", "Glockenspiel", "Music Box", "Vibraphone",
    "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
    "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)", "Electric Guitar (jazz)", "Electric Guitar (clean)",
    "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar", "Guitar Harmonics",
    "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)", "Fretless Bass",
    "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
    "Violin", "Viola", "Cello", "Contrabass",
    "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
    "String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2",
    "Choir Aahs", "Voice Oohs", "Synth Voice", "Orchestra Hit",
    "Trumpet", "Trombone", "Tuba", "Muted Trumpet",
    "French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
    "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet",
    "Piccolo", "Flute", "Recorder", "Pan Flute",
    "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
    "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
    "Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass + lead)",
    "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
    "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
    "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
    "Sitar", "Banjo", "Shamisen", "Koto",
    "Kalimba", "Bag pipe", "Fiddle", "Shanai",
    "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
    "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
    "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
    "Telephone Ring", "Helicopter", "Applause", "Gunshot",
]

# 标准 MIDI 控制器名（0-119）
CC_NAMES = {
    0: "Bank Select (MSB)", 1: "Modulation Wheel (MSB)", 2: "Breath Controller (MSB)",
    4: "Foot Controller (MSB)", 5: "Portamento Time (MSB)", 6: "Data Entry (MSB)",
    7: "Channel Volume (MSB)", 8: "Balance (MSB)", 10: "Pan (MSB)",
    11: "Expression Controller (MSB)", 64: "Damper Pedal On/Off (Sustain)",
    65: "Portamento On/Off", 66: "Sostenuto On/Off", 67: "Soft Pedal On/Off",
    68: "Legato Footswitch", 69: "Hold 2", 70: "Sound Controller 1 (Sound Variation)",
    71: "Sound Controller 2 (Timbre/Harmonic Intensity)", 72: "Sound Controller 3 (Release Time)",
    73: "Sound Controller 4 (Attack Time)", 74: "Sound Controller 5 (Brightness)",
    84: "Portamento Control", 91: "Effects 1 Depth (Reverb)", 92: "Effects 2 Depth (Tremolo)",
    93: "Effects 3 Depth (Chorus)", 94: "Effects 4 Depth (Celeste/Detune)", 95: "Effects 5 Depth (Phaser)",
    96: "Data Increment", 97: "Data Decrement",
    98: "Non-Registered Parameter Number (LSB)", 99: "Non-Registered Parameter Number (MSB)",
    100: "Registered Parameter Number (LSB)", 101: "Registered Parameter Number (MSB)",
}
for _cc in range(16, 20):
    CC_NAMES[_cc] = f"General Purpose Controller {_cc - 15}"
for _cc in range(80, 84):
    CC_NAMES[_cc] = f"General Purpose Controller {_cc - 75}"
for _cc in range(32, 64):
    CC_NAMES[_cc] = f"LSB for CC {_cc - 32}"


class DecodeError(Exception):
    """数据错误（退出码 1）。"""


class UsageError(Exception):
    """用法错误（退出码 2）。"""


# ══════════════════════════════════════════════════════════════
# 基础工具
# ══════════════════════════════════════════════════════════════

def pitch_name(m):
    if not (0 <= m <= 127):
        return None
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def read_vlq(data, pos, end):
    """读取变长数量（VLQ），返回 (value, new_pos)。"""
    value = 0
    while pos < end:
        b = data[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, pos
        if value > 0x0FFFFFFF:
            break
    raise DecodeError("MIDI 数据截断：VLQ 未终结")


def _decode_text(payload):
    """文本解码：优先 latin-1，中文 GBK/Big5/Shift-JIS 逐级回退。"""
    for enc in ("utf-8", "gbk", "big5", "shift_jis"):
        try:
            return payload.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return payload.decode("latin-1", errors="replace")


def _hexdump(payload):
    return payload.hex().upper()


def _build_tempo_table(entries, default_spb):
    """把 (tick, 秒/tick) 事件整理成可二分查询的时间轴。

    同一 tick 的 Tempo 事件后者覆盖前者；返回 (ticks, spbs, times)，
    times[i] 是 ticks[i] 处的累计秒数，spbs[i] 从 ticks[i] 起生效。
    """
    effective = {}
    for tick, spb in entries:
        effective[tick] = spb

    ticks = [0]
    spbs = [default_spb]
    times = [0.0]
    prev_tick = 0
    prev_spb = default_spb

    for tick, spb in sorted(effective.items()):
        if tick == prev_tick:
            spbs[-1] = spb
            prev_spb = spb
            continue
        if tick < prev_tick:
            continue
        times.append(times[-1] + (tick - prev_tick) * prev_spb)
        ticks.append(tick)
        spbs.append(spb)
        prev_tick = tick
        prev_spb = spb
    return ticks, spbs, times


def _sec_at_tick(ticks, spbs, times, tick):
    """按全局 Tempo 时间轴把绝对 tick 换算为秒。"""
    i = bisect_right(ticks, tick) - 1
    return times[i] + (tick - ticks[i]) * spbs[i]


# ══════════════════════════════════════════════════════════════
# 核心解码器
# ══════════════════════════════════════════════════════════════

def decode_midi(data, include_events=True, include_notes=True, file_name=None):
    """MIDI 字节流 → 完整 JSON 结构。"""
    if len(data) < 14 or data[:4] != b"MThd":
        raise DecodeError("不是有效的 MIDI 文件（缺少 MThd 头）")

    header_len = struct.unpack(">I", data[4:8])[0]
    fmt = struct.unpack(">H", data[8:10])[0]
    ntrks = struct.unpack(">H", data[10:12])[0]
    division = struct.unpack(">H", data[12:14])[0]

    if division & 0x8000:
        fps_neg = struct.unpack(">b", struct.pack(">H", division)[:1])[0]
        ticks_per_frame = division & 0x00FF
        if fps_neg >= 0 or ticks_per_frame == 0:
            raise DecodeError(f"SMPTE 时基非法：{division:#06x}")
        fps = -fps_neg
        fps_actual = 29.97 if fps == 29 else float(fps)  # 29 → 29.97 drop-frame
        division_type = "smpte"
        header = {"format": fmt, "track_count": ntrks, "division": division,
                  "division_type": "smpte", "fps": fps, "fps_actual": fps_actual,
                  "ticks_per_frame": ticks_per_frame}
        sec_per_tick = 1.0 / (fps_actual * ticks_per_frame)
        tpqn = None
    else:
        tpqn = division or 480
        division_type = "tpqn"
        header = {"format": fmt, "track_count": ntrks, "division": division,
                  "division_type": "tpqn", "tpqn": tpqn}
        sec_per_tick = None  # 由 tempo 事件决定

    # PPQN 默认 120 BPM；Tempo 事件统一收集为全局时间轴，跨轨精确换算
    default_spb = sec_per_tick if division_type == "smpte" else 0.5 / (tpqn or 480)
    tempo_entries = []

    pos = 8 + header_len
    warnings = []
    tracks = []
    all_notes = []
    global_bpm = None
    global_time_sig = None
    global_key_sig = None
    last_tick = 0

    for ti in range(ntrks):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            raise DecodeError(f"音轨 {ti} 缺少 MTrk 块")
        track_len = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        pos += 8
        end = min(pos + track_len, len(data))

        abs_tick = 0
        running = None

        events = []
        pending = {}  # (channel, pitch) -> deque[(start_tick, vel)]
        track_name = None
        channel_counter = {}
        last_program = None
        last_channel = None

        while pos < end:
            delta, pos = read_vlq(data, pos, end)
            abs_tick += delta
            if abs_tick > last_tick:
                last_tick = abs_tick
            b = data[pos]
            pos += 1
            ev = {"tick": abs_tick, "time": None, "delta": delta}

            if b == 0xFF:  # Meta 事件
                if pos >= end:
                    raise DecodeError("MIDI 数据截断：meta 类型缺失")
                meta_type = data[pos]
                pos += 1
                mlen, pos = read_vlq(data, pos, end)
                payload = data[pos:pos + mlen]
                pos += mlen
                ev["type"] = "meta"

                if meta_type == 0x00:  # 序号
                    ev["meta"] = "sequence_number"
                    ev["number"] = int.from_bytes(payload[:2], "big") if payload else None
                elif meta_type == 0x01:
                    ev["meta"] = "text"
                    ev["text"] = _decode_text(payload)
                elif meta_type == 0x02:
                    ev["meta"] = "copyright"
                    ev["text"] = _decode_text(payload)
                elif meta_type == 0x03:  # 音轨名
                    ev["meta"] = "track_name"
                    name = _decode_text(payload)
                    ev["name"] = name
                    if track_name is None and name:
                        track_name = name
                elif meta_type == 0x04:
                    ev["meta"] = "instrument_name"
                    ev["name"] = _decode_text(payload)
                elif meta_type == 0x05:  # 歌词
                    ev["meta"] = "lyrics"
                    ev["text"] = _decode_text(payload)
                elif meta_type == 0x06:
                    ev["meta"] = "marker"
                    ev["text"] = _decode_text(payload)
                elif meta_type == 0x07:
                    ev["meta"] = "cue_point"
                    ev["text"] = _decode_text(payload)
                elif meta_type == 0x08:
                    ev["meta"] = "program_name"
                    ev["text"] = _decode_text(payload)
                elif meta_type == 0x09:
                    ev["meta"] = "device_name"
                    ev["text"] = _decode_text(payload)
                elif meta_type == 0x20:  # 通道前缀
                    ev["meta"] = "channel_prefix"
                    ev["channel"] = payload[0] if payload else None
                elif meta_type == 0x21:  # MIDI 端口
                    ev["meta"] = "midi_port"
                    ev["port"] = payload[0] if payload else None
                elif meta_type == 0x2F:  # 音轨结束：未闭合音符就地收尾
                    ev["meta"] = "end_of_track"
                    for (ch, p), q in pending.items():
                        for st_tick, vel in q:
                            all_notes.append(_mk_note(ti, ch, p, st_tick, abs_tick - st_tick, vel, tpqn))
                    pending.clear()
                elif meta_type == 0x51 and len(payload) >= 3:  # Tempo
                    us = int.from_bytes(payload[:3], "big")
                    if us > 0:
                        bpm = 60_000_000 / us
                        ev["meta"] = "tempo"
                        ev["bpm"] = round(bpm, 2)
                        ev["us_per_beat"] = us
                        if division_type == "tpqn":
                            tempo_entries.append((abs_tick, us / 1_000_000 / tpqn))
                        if global_bpm is None:
                            global_bpm = round(bpm, 2)
                elif meta_type == 0x54:  # SMPTE 偏移
                    ev["meta"] = "smpte_offset"
                    if len(payload) >= 5:
                        ev["offset"] = {"hours": payload[0], "minutes": payload[1],
                                        "seconds": payload[2], "frames": payload[3],
                                        "sub_frames": payload[4]}
                elif meta_type == 0x58:  # 拍号
                    if len(payload) >= 2:
                        num, den_pow = payload[0], payload[1]
                        ev["meta"] = "time_signature"
                        ev["numerator"] = num
                        ev["denominator"] = 2 ** den_pow
                        ev["clocks_per_click"] = payload[2] if len(payload) > 2 else None
                        ev["notated_32nds"] = payload[3] if len(payload) > 3 else None
                        if global_time_sig is None:
                            global_time_sig = f"{num}/{2 ** den_pow}"
                elif meta_type == 0x59:  # 调号
                    if len(payload) >= 2:
                        sf = struct.unpack(">b", payload[:1])[0]
                        mode = "major" if payload[1] == 0 else "minor"
                        ev["meta"] = "key_signature"
                        ev["sharps_flats"] = sf
                        ev["mode"] = mode
                        if global_key_sig is None:
                            global_key_sig = {"sharps_flats": sf, "mode": mode}
                elif meta_type == 0x7F:  # Sequencer 专用
                    ev["meta"] = "sequencer_specific"
                    ev["data"] = _hexdump(payload)
                else:
                    ev["meta"] = "unknown"
                    ev["type"] = meta_type
                    ev["data"] = _hexdump(payload)
                    warnings.append(f"轨{ti} tick{abs_tick}: 未知 meta 类型 0x{meta_type:02X}")
                events.append(ev)
                continue

            if b in (0xF0, 0xF7):  # SysEx
                slen, pos = read_vlq(data, pos, end)
                payload = data[pos:pos + slen]
                pos += slen
                ev["type"] = "sys_exclusive" if b == 0xF0 else "sys_exclusive_continue"
                ev["data"] = _hexdump(payload)
                events.append(ev)
                continue

            if b & 0x80:
                status = b
                running = b
            else:
                if running is None:
                    raise DecodeError(f"MIDI 数据非法：数据字节 0x{b:02X} 出现在状态字节之前")
                status = running
                pos -= 1  # 该字节是数据字节，回退

            # 系统实时/公共消息
            if status == 0xF1:  # MTC Quarter Frame
                if pos >= end:
                    raise DecodeError("MIDI 数据截断")
                ev["type"] = "mtc_quarter_frame"
                ev["value"] = data[pos]
                pos += 1
                events.append(ev)
                continue
            if status == 0xF2:  # Song Position Pointer
                if pos + 2 > end:
                    raise DecodeError("MIDI 数据截断")
                ev["type"] = "song_position"
                ev["value"] = struct.unpack(">H", data[pos:pos + 2])[0]
                pos += 2
                events.append(ev)
                continue
            if status == 0xF3:  # Song Select
                if pos >= end:
                    raise DecodeError("MIDI 数据截断")
                ev["type"] = "song_select"
                ev["value"] = data[pos]
                pos += 1
                events.append(ev)
                continue
            if status == 0xF6:
                ev["type"] = "tune_request"
                events.append(ev)
                continue
            if status in (0xF8, 0xFA, 0xFB, 0xFC, 0xFE):
                ev["type"] = {0xF8: "timing_clock", 0xFA: "start", 0xFB: "continue",
                              0xFC: "stop", 0xFE: "active_sensing"}[status]
                events.append(ev)
                continue
            if status == 0xFF or status == 0xF0:
                raise DecodeError(f"MIDI 数据非法：状态字节 0x{status:02X} 处理异常")

            # 通道消息
            nbytes = 2 if (status & 0xF0) not in (0xC0, 0xD0) else 1
            if pos + nbytes > end:
                raise DecodeError("MIDI 数据截断：通道消息数据不足")
            d1 = data[pos]
            d2 = data[pos + 1] if nbytes == 2 else None
            pos += nbytes
            ch = status & 0x0F
            msg = status & 0xF0
            channel_counter[ch] = channel_counter.get(ch, 0) + 1

            if msg == 0x80:  # Note-Off
                ev["type"] = "note_off"
                ev["channel"] = ch
                ev["pitch"] = d1
                ev["pitch_name"] = pitch_name(d1)
                ev["velocity"] = d2
                q = pending.get((ch, d1))
                if q:
                    st_tick, vel = q.pop(0)
                    dur = abs_tick - st_tick
                    all_notes.append(_mk_note(ti, ch, d1, st_tick, dur, vel, tpqn))
            elif msg == 0x90:  # Note-On（vel=0 视作 Note-Off）
                ev["type"] = "note_on" if d2 > 0 else "note_off"
                ev["channel"] = ch
                ev["pitch"] = d1
                ev["pitch_name"] = pitch_name(d1)
                ev["velocity"] = d2
                if d2 > 0:
                    pending.setdefault((ch, d1), []).append((abs_tick, d2))
                else:
                    q = pending.get((ch, d1))
                    if q:
                        st_tick, vel = q.pop(0)
                        dur = abs_tick - st_tick
                        all_notes.append(_mk_note(ti, ch, d1, st_tick, dur, vel, tpqn))
            elif msg == 0xA0:  # Poly Aftertouch
                ev["type"] = "poly_aftertouch"
                ev["channel"] = ch
                ev["pitch"] = d1
                ev["pitch_name"] = pitch_name(d1)
                ev["value"] = d2
            elif msg == 0xB0:  # Control Change
                ev["type"] = "control_change"
                ev["channel"] = ch
                ev["controller"] = d1
                ev["controller_name"] = CC_NAMES.get(d1, f"CC {d1}")
                ev["value"] = d2
            elif msg == 0xC0:  # Program Change
                ev["type"] = "program_change"
                ev["channel"] = ch
                ev["program"] = d1
                ev["program_name"] = GM_PROGRAMS[d1] if d1 < len(GM_PROGRAMS) else None
                last_program = d1
            elif msg == 0xD0:  # Channel Pressure
                ev["type"] = "channel_pressure"
                ev["channel"] = ch
                ev["value"] = d1
            elif msg == 0xE0:  # Pitch Bend
                value = d1 | (d2 << 7)
                ev["type"] = "pitch_bend"
                ev["channel"] = ch
                ev["value"] = value
                ev["semitones"] = round((value - 8192) / 8192 * 2, 4)
            events.append(ev)

        # 轨内未闭合音符（理论不应到达，防御）
        for (ch, p), q in pending.items():
            for st_tick, vel in q:
                warnings.append(f"轨{ti} 音符 {p} 未闭合，强制收尾")
                all_notes.append(_mk_note(ti, ch, p, st_tick, abs_tick - st_tick, vel, tpqn))
        pending.clear()

        last_channel = max(channel_counter, key=channel_counter.get) if channel_counter else None
        track = {
            "index": ti,
            "name": track_name or f"Track {ti}",
            "channel": last_channel,
            "program": last_program,
            "event_count": len(events),
            "note_count": sum(1 for n in all_notes if n["track"] == ti),
        }
        if include_events:
            track["events"] = events
        tracks.append(track)

    ticks, spbs, times = _build_tempo_table(tempo_entries, default_spb)
    for track in tracks:
        for ev in track.get("events", []):
            ev["time"] = round(_sec_at_tick(ticks, spbs, times, ev["tick"]), 6)
    for n in all_notes:
        n["start_time"] = round(_sec_at_tick(ticks, spbs, times, n["start_tick"]), 6)
        n["end_time"] = round(_sec_at_tick(ticks, spbs, times, n["end_tick"]), 6)
    last_sec = _sec_at_tick(ticks, spbs, times, last_tick)

    notes = sorted(all_notes, key=lambda n: (n["track"], n["channel"], n["start_tick"], n["pitch"])) if include_notes else []
    if not include_notes:
        notes = None

    global_data = {
        "bpm": global_bpm if global_bpm is not None else 120.0,
        "time_signature": global_time_sig or "4/4",
        "key_signature": global_key_sig,
        "duration_ticks": last_tick,
        "duration_sec": round(last_sec, 6),
    }

    result = {
        "ok": True,
        "file": file_name,
        "decoder": f"aria-decode {__version__}",
        "header": header,
        "global": global_data,
        "tracks": tracks,
        "warnings": warnings,
    }
    if notes is not None:
        result["notes"] = notes
    return result


def _mk_note(track, channel, pitch, st_tick, dur_ticks, vel, tpqn):
    """构造音符对象；秒时间戳由全局 Tempo 时间轴在解码完成后回填。"""
    beat_div = tpqn if tpqn else 480
    return {
        "track": track,
        "channel": channel,
        "pitch": pitch,
        "pitch_name": pitch_name(pitch),
        "start_tick": st_tick,
        "start_beat": round(st_tick / beat_div, 3),
        "start_time": None,
        "end_tick": st_tick + dur_ticks,
        "duration_ticks": dur_ticks,
        "duration": round(dur_ticks / beat_div, 3),
        "end_time": None,
        "velocity": vel,
    }


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def _read_input(path, binary=True):
    if path == "-":
        data = sys.stdin.buffer.read() if binary else sys.stdin.read()
        return data, "-"
    with open(path, "rb" if binary else "r", encoding=None) as f:
        return f.read(), path


def cmd_decode(args):
    try:
        data, fname = _read_input(args.input, binary=True)
    except OSError as e:
        raise UsageError(f"无法读取输入文件: {e}")
    result = decode_midi(data, include_events=not args.no_events,
                         include_notes=not args.no_notes, file_name=fname)
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output and args.output != "-":
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out + "\n")
        except OSError as e:
            raise UsageError(f"无法写入输出文件: {e}")
    else:
        print(out)
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="aria-decode",
        description="Aria 技能包 — 零依赖 MIDI → JSON 无损解码器")
    p.add_argument("--version", action="version", version=f"aria-decode {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<子命令>")

    d = sub.add_parser("decode", help="解码 .mid → JSON（默认输出全部事件与音符汇总）")
    d.add_argument("--input", required=True, metavar="<file.mid>", help="输入 MIDI 文件（- 表示 stdin）")
    d.add_argument("--output", metavar="<file.json>", help="输出 JSON 文件（默认 stdout，- 同上）")
    d.add_argument("--no-events", action="store_true", help="不输出逐事件明细，仅头部/全局/音符")
    d.add_argument("--no-notes", action="store_true", help="不输出音符汇总，仅事件明细")
    d.set_defaults(handler=cmd_decode)
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
    except DecodeError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1
    except UsageError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
