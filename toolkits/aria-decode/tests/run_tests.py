#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-decode 解码工具 — 测试套件（零依赖，仅标准库）

运行：python tests/run_tests.py
全部通过退出码 0；任一失败退出码 1，并打印失败详情。

事件串约定：每个 chunk = "delta + event"，_track 只负责在结尾补 EOT。
"""

import json
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aria_decode  # noqa: E402

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aria_decode.py")
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp.mid")

# ────────────────────────── MIDI 构造器 ──────────────────────────

def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.insert(0, 0x80 | (n & 0x7F))
        n >>= 7
    return bytes(out)


def _meta(meta_type, payload=b""):
    return bytes([0xFF, meta_type]) + _vlq(len(payload)) + payload


def _ch(status, *data):
    return bytes([status]) + bytes(data)


def _track(*chunks, eot_delta=0):
    """chunks 为 'delta + event' 连接；结尾补 delta(eot_delta) + EOT。"""
    data = b"".join(chunks) + _vlq(eot_delta) + _meta(0x2F)
    return b"MTrk" + struct.pack(">I", len(data)) + data


def build_midi(division, *tracks, fmt=1):
    head = struct.pack(">HHH", fmt, len(tracks), division)
    return b"MThd" + struct.pack(">I", 6) + head + b"".join(tracks)


def write_tmp(data):
    with open(TMP, "wb") as f:
        f.write(data)


def cli(*args, stdin=None):
    if isinstance(stdin, bytes):
        p = subprocess.run([sys.executable, TOOL, *args], capture_output=True, input=stdin)
        return p.returncode, p.stdout.decode("utf-8", errors="replace"), p.stderr.decode("utf-8", errors="replace")
    p = subprocess.run([sys.executable, TOOL, *args], capture_output=True,
                       input=stdin, text=True)
    return p.returncode, p.stdout, p.stderr


# ────────────────────────── 用例 ──────────────────────────

PASS = FAIL = 0
_FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        _FAILURES.append(f"{name} :: {detail}")
        print(f"FAIL  {name} :: {detail}")


def test_header_ppqn():
    mid = build_midi(480, _track())
    r = aria_decode.decode_midi(mid)
    h = r["header"]
    check("header PPQN", h["format"] == 1 and h["tpqn"] == 480 and h["division_type"] == "tpqn", str(h))


def test_basic_notes():
    ev = _vlq(0) + _ch(0x90, 60, 100) + _vlq(240) + _ch(0x80, 60, 0)
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    n = r["notes"]
    check("note 聚合", len(n) == 1 and n[0]["pitch"] == 60 and n[0]["pitch_name"] == "C4", json.dumps(n, ensure_ascii=False))
    check("note 时值", n[0]["start_beat"] == 0.0 and n[0]["duration"] == 0.5 and n[0]["velocity"] == 100, str(n[0]))
    check("note 秒时间", n[0]["start_time"] == 0.0 and abs(n[0]["end_time"] - 0.25) < 1e-9, str(n[0]))
    check("note channel", n[0]["channel"] == 0 and n[0]["track"] == 0, str(n[0]))
    check("轨统计", r["tracks"][0]["note_count"] == 1 and r["tracks"][0]["channel"] == 0, str(r["tracks"][0]))


def test_tempo_time():
    # tempo 120 → 240 tick；tempo 60 → 480 tick，验证秒换算（480 tick @60bpm = 1s）
    ev = _vlq(0) + _meta(0x51, b"\x07\xa1\x20") + _vlq(240) + _ch(0x90, 60, 90) + _vlq(240) + _ch(0x80, 60, 0)
    ev2 = _vlq(0) + _meta(0x51, b"\x0f\x42\x40") + _vlq(480) + _ch(0x90, 64, 90) + _vlq(480) + _ch(0x80, 64, 0)
    mid = build_midi(480, _track(ev), _track(ev2))
    r = aria_decode.decode_midi(mid)
    check("tempo bpm", r["global"]["bpm"] == 120.0, str(r["global"]))
    t1 = r["tracks"][1]["events"]
    tempo_ev = [e for e in t1 if e.get("meta") == "tempo"][0]
    note = [e for e in t1 if e["type"] == "note_on"][0]
    check("tempo 60 换算", tempo_ev["bpm"] == 60.0 and abs(note["time"] - 1.0) < 1e-6,
          json.dumps([tempo_ev, note], ensure_ascii=False))


def test_time_signature():
    ev = _vlq(0) + _meta(0x58, b"\x03\x02\x18\x08")
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    check("拍号", r["global"]["time_signature"] == "3/4", str(r["global"]))
    ts = [e for e in r["tracks"][0]["events"] if e.get("meta") == "time_signature"][0]
    check("拍号详情", ts["numerator"] == 3 and ts["denominator"] == 4 and ts["clocks_per_click"] == 24, str(ts))


def test_track_name_gbk():
    name = "旋律".encode("gbk")
    mid = build_midi(480, _track(_vlq(0) + _meta(0x03, name)))
    r = aria_decode.decode_midi(mid)
    check("GBK 音轨名", r["tracks"][0]["name"] == "旋律", repr(r["tracks"][0]["name"]))


def test_meta_lyrics_marker():
    ev = _vlq(0) + _meta(0x05, "la~".encode()) + _vlq(0) + _meta(0x06, b"A")
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    kinds = [(e["meta"], e.get("text")) for e in r["tracks"][0]["events"] if e["type"] == "meta"]
    check("歌词与标记", ("lyrics", "la~") in kinds and ("marker", "A") in kinds, str(kinds))


def test_cc_pitchbend_program():
    ev = (_vlq(0) + _ch(0xB0, 7, 100) + _vlq(0) + _ch(0xE0, 0x00, 0x40) + _vlq(0) +
          _ch(0xC0, 0) + _vlq(0) + _ch(0x90, 60, 80) + _vlq(120) + _ch(0x80, 60, 0))
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    es = r["tracks"][0]["events"]
    cc = [e for e in es if e["type"] == "control_change"][0]
    pb = [e for e in es if e["type"] == "pitch_bend"][0]
    pg = [e for e in es if e["type"] == "program_change"][0]
    check("CC 控制器名", cc["controller"] == 7 and cc["controller_name"] == "Channel Volume (MSB)", str(cc))
    check("弯音 14bit", pb["value"] == 8192 and pb["semitones"] == 0.0, str(pb))
    check("GM 音色名", pg["program"] == 0 and pg["program_name"] == "Acoustic Grand Piano", str(pg))


def test_running_status():
    # note_on 后省略状态字节的 running status；note_off 用显式状态字节
    ev = (_vlq(0) + _ch(0x90, 60, 90) + _vlq(120) + bytes([62, 80]) + _vlq(120) + bytes([64, 70]) + _vlq(120) +
          _ch(0x80, 60, 0))
    for p in (62, 64):
        ev += _vlq(0) + _ch(0x80, p, 0)
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    check("running status", len(r["notes"]) == 3 and [n["pitch"] for n in r["notes"]] == [60, 62, 64], str(r["notes"]))


def test_vel0_noteoff():
    ev = _vlq(0) + _ch(0x90, 65, 100) + _vlq(120) + _ch(0x90, 65, 0)
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    check("vel0 记法", len(r["notes"]) == 1 and r["notes"][0]["pitch"] == 65 and r["notes"][0]["duration"] == 0.25, str(r["notes"]))


def test_overlap_stacking():
    # 同 pitch 重叠音符（双叠音）：note_on A, note_on A, note_off, note_off
    ev = (_vlq(0) + _ch(0x90, 60, 90) + _vlq(120) + _ch(0x90, 60, 70) + _vlq(120) +
          _ch(0x80, 60, 0) + _vlq(120) + _ch(0x80, 60, 0))
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    check("重叠音符", len(r["notes"]) == 2 and
          (r["notes"][0]["duration"], r["notes"][1]["duration"]) == (0.5, 0.5), str(r["notes"]))


def test_smpte():
    mid = build_midi(0xE828, _track())  # fps=-24(0xE8), ticks/frame=40
    r = aria_decode.decode_midi(mid)
    h = r["header"]
    check("SMPTE 头", h["division_type"] == "smpte" and h["fps"] == 24 and h["ticks_per_frame"] == 40, str(h))


def test_smpte_time():
    # SMPTE 30fps、100 tick/frame：100 tick = 1/30 秒
    mid = build_midi(0xE264, _track())  # fps=-30(0xE2), ticks/frame=100 (0x64)
    r = aria_decode.decode_midi(mid)
    h = r["header"]
    check("SMPTE 30fps", h["fps"] == 30 and h["ticks_per_frame"] == 100, str(h))


def test_end_of_track_unclosed():
    ev = _vlq(0) + _ch(0x90, 67, 80)  # 无 note_off，EOT(240) 收尾
    mid = build_midi(480, _track(ev, eot_delta=240))
    r = aria_decode.decode_midi(mid)
    check("EOT 收尾", len(r["notes"]) == 1 and r["notes"][0]["duration"] == 0.5, str(r["notes"]))


def test_unknown_meta_warning():
    ev = _vlq(0) + _meta(0x7E, b"\x01\x02")
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    check("未知 meta 告警", len(r["warnings"]) == 1, str(r["warnings"]))


def test_flags():
    ev = _vlq(0) + _ch(0x90, 60, 90) + _vlq(120) + _ch(0x80, 60, 0)
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid, include_events=False)
    check("--no-events 语义", "events" not in r["tracks"][0] and len(r["notes"]) == 1, str(r["tracks"][0]))
    r2 = aria_decode.decode_midi(mid, include_notes=False)
    check("--no-notes 语义", "notes" not in r2 and len(r2["tracks"][0]["events"]) >= 1, str(r2))


def test_exit_codes():
    write_tmp(b"not a midi file at all")
    code, out, _ = cli("decode", "--input", TMP)
    check("退出码 1（数据错误）", code == 1 and '"ok": false' in out, f"code={code} out={out}")
    code2, _, _ = cli("decode")
    check("退出码 2（用法错误）", code2 == 2, f"code={code2}")
    code3, out3, _ = cli("--version")
    check("--version", code3 == 0 and "1.0.0" in out3, out3)


def test_stdin():
    ev = _vlq(0) + _ch(0x90, 72, 100) + _vlq(120) + _ch(0x80, 72, 0)
    mid = build_midi(480, _track(ev))
    code, out, _ = cli("decode", "--input", "-", "--no-events", stdin=mid)
    check("stdin 解码", code == 0 and '"pitch": 72' in out, f"code={code}")
    check("stdin 文件名", '"file": "-"' in out, out[:200])


def test_channel_prefix():
    ev = _vlq(0) + _meta(0x20, b"\x02") + _vlq(0) + _ch(0x90, 60, 80) + _vlq(120) + _ch(0x80, 60, 0)
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    cp = [e for e in r["tracks"][0]["events"] if e.get("meta") == "channel_prefix"][0]
    check("通道前缀", cp["channel"] == 2, str(cp))


def test_sysex_skipped():
    # SysEx（F0）被正确记录而非破坏解析流
    sysex = b"\xF0\x03\x01\x02\x03"
    ev = _vlq(0) + sysex + _vlq(0) + _ch(0x90, 60, 90) + _vlq(120) + _ch(0x80, 60, 0)
    mid = build_midi(480, _track(ev))
    r = aria_decode.decode_midi(mid)
    types = [e["type"] for e in r["tracks"][0]["events"]]
    check("SysEx 记录", "sys_exclusive" in types and len(r["notes"]) == 1, str(types))


def test_output_file():
    ev = _vlq(0) + _ch(0x90, 60, 90) + _vlq(120) + _ch(0x80, 60, 0)
    mid = build_midi(480, _track(ev))
    write_tmp(mid)
    out_path = os.path.join(os.path.dirname(TMP), "_tmp_out.json")
    code, _, _ = cli("decode", "--input", TMP, "--output", out_path)
    with open(out_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    check("--output 写文件", code == 0 and data["ok"] is True and len(data["notes"]) == 1, str(data.get("ok")))
    os.remove(out_path)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\n{len(tests)} 个用例：{PASS} 通过 / {FAIL} 失败")
    if _FAILURES:
        print("失败明细：")
        for f in _FAILURES:
            print(f"  - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        if os.path.exists(TMP):
            os.remove(TMP)
