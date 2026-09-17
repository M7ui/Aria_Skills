#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-report 逆向分析工具 — 测试套件（零依赖，仅标准库）

运行：python tests/run_tests.py
全部通过退出码 0；任一失败退出码 1，并打印失败详情。

MIDI 素材在内存里现造（与 aria-decode/tests 同一套构造器约定）：
每个 chunk = "delta + event"，_track 只负责在结尾补 EOT。
"""

import json
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "aria_report.py")
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "aria-decode"))
import aria_report  # noqa: E402

TMPDIR = os.path.join(HERE, "_tmp_report")

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
    data = b"".join(chunks) + _vlq(eot_delta) + _meta(0x2F)
    return b"MTrk" + struct.pack(">I", len(data)) + data


def build_midi(division, *tracks, fmt=1):
    head = struct.pack(">HHH", fmt, len(tracks), division)
    return b"MThd" + struct.pack(">I", 6) + head + b"".join(tracks)


def _seq_notes(channel, pitches, dur=240, vel=90):
    """把一串音高排成等时值的顺序音符（0.5 拍 @480）。"""
    ev = b""
    for p in pitches:
        ev += _vlq(0) + _ch(0x90 | channel, p, vel) + _vlq(dur) + _ch(0x80 | channel, p, 0)
    return ev


def fresh_tmpdir():
    if os.path.isdir(TMPDIR):
        shutil.rmtree(TMPDIR)
    os.makedirs(TMPDIR)
    return TMPDIR


def write_mid(name, data):
    os.makedirs(TMPDIR, exist_ok=True)
    path = os.path.join(TMPDIR, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def cli(*args):
    p = subprocess.run([sys.executable, TOOL, *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


# 常用素材：C 大调音阶 + 一个重复动机 (60 62 64) x2
MELODY_PITCHES = [60, 62, 64, 60, 62, 64, 67, 69, 72]
# 完整七声 C 大调（音级 0,2,4,5,7,9,11），用于调式推测
C_MAJOR_7 = [60, 62, 64, 65, 67, 69, 71, 72]
TEMPO_120 = _vlq(0) + _meta(0x51, b"\x07\xa1\x20")


def mid_melody_only(name="melody.mid"):
    """轨0 指挥（120 BPM），轨1 钢琴旋律。"""
    ev = _vlq(0) + _meta(0x03, "Lead".encode()) + _vlq(0) + _ch(0xC0, 0) + _seq_notes(0, MELODY_PITCHES)
    return write_mid(name, build_midi(480, _track(TEMPO_120), _track(ev)))


# ────────────────────────── 断言框架 ──────────────────────────

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


# ────────────────────────── 单元：调式推测 ──────────────────────────

def test_infer_key_c_major():
    # 必须是完整七声（含 F 与 B）才能把 C major 与其他调式区分开；
    # 只用五声音级时多个音阶会并列满分（见 test_infer_key_relative_modes_tie）
    melody = [{"pitch": p, "start_beat": i * 0.5} for i, p in enumerate(C_MAJOR_7)]
    keys = aria_report.infer_key(melody)
    check("infer_key 返回 Top3", len(keys) == 3, str(keys))
    check("infer_key 首推 C major", keys[0]["root"] == "C" and keys[0]["type"] == "major", str(keys))
    check("infer_key 覆盖率 1.0", keys[0]["coverage"] == 1.0, str(keys[0]))


def test_infer_key_relative_modes_tie():
    """已知局限：C major 与 A minor / D dorian 音级集合完全相同，
    覆盖率必然并列 1.0，只能靠「常见调式优先 + 主音频次」排先后。"""
    def coverage(pitches, root_pc, scale):
        scale_pc = {(root_pc + i) % 12 for i in aria_report.SCALES[scale]}
        return sum(1 for p in pitches if p % 12 in scale_pc) / len(pitches)

    check("相对大/小调覆盖率并列",
          coverage(C_MAJOR_7, 0, "major") == 1.0 and coverage(C_MAJOR_7, 9, "minor") == 1.0,
          str([coverage(C_MAJOR_7, r, s) for r, s in ((0, "major"), (9, "minor"), (2, "dorian"))]))
    keys = aria_report.infer_key([{"pitch": p, "start_beat": 0} for p in C_MAJOR_7])
    check("并列时 common 调式（major/minor）优先于教会调式",
          keys[1]["type"] in ("major", "minor"), str(keys))


def test_infer_key_empty():
    check("infer_key 空旋律返回空表", aria_report.infer_key([]) == [], "应返回 []")


def test_infer_key_chromatic_low_coverage():
    # 十二音全上：任何七声音阶覆盖率都 < 1
    melody = [{"pitch": 60 + i, "start_beat": i * 0.5} for i in range(12)]
    keys = aria_report.infer_key(melody)
    check("infer_key 半音阶覆盖率不高", keys and keys[0]["coverage"] < 1.0, str(keys[0]))


# ────────────────────────── 单元：风格识别 ──────────────────────────

def test_style_lofi_by_bpm():
    st = aria_report.detect_style(80.0, ["Acoustic Grand Piano"], "major", [])
    names = [s["style"] for s in st]
    check("风格：80 BPM 命中 Lo-fi", "Lo-fi" in names, str(st))
    check("风格：Lo-fi 得分为最高档", st[0]["style"] == "Lo-fi" and st[0]["score"] == 3, str(st))


def test_style_piano_solo():
    st = aria_report.detect_style(96.0, ["Acoustic Grand Piano"], "major", [])
    check("风格：纯钢琴命中独奏/古典",
          any(s["style"] == "钢琴独奏 / 古典" for s in st), str(st))


def test_style_tropical():
    st = aria_report.detect_style(112.0, ["Marimba", "Acoustic Bass"], "major", [])
    check("风格：112 BPM + 马林巴命中 Tropical House",
          any(s["style"] == "Tropical House" for s in st), str(st))


def test_style_edm_by_bpm_lead():
    st = aria_report.detect_style(128.0, ["Lead 1 (square)", "Electric Bass (finger)"], "minor", [])
    check("风格：128 BPM + Lead 命中 EDM",
          any("EDM" in s["style"] for s in st), str(st))


def test_style_empty_returns_list():
    st = aria_report.detect_style(None, [], None, [])
    check("风格：无信息仍返回列表", isinstance(st, list), str(type(st)))


# ────────────────────────── 单元：动机提取 ──────────────────────────

def test_extract_motifs_repeat():
    melody = [{"pitch": p, "start_beat": i * 0.5} for i, p in enumerate(MELODY_PITCHES)]
    ms = aria_report.extract_motifs(melody)
    check("动机：检出重复音程对", len(ms) >= 1, str(ms))
    top = ms[0]
    check("动机：音程对为 [2,2]", top["intervals"] == [2, 2], str(top))
    check("动机：出现 2 次", top["count"] == 2, str(top))
    check("动机：起始音相同判为原样重复", top["technique"] == "原样重复", str(top))
    check("动机：音名序列正确", top["note_names"] == ["C4", "D4", "E4"], str(top["note_names"]))
    check("动机：带小节/拍位置", all("bar" in p and "beat" in p for p in top["positions"]), str(top["positions"]))


def test_extract_motifs_transposed():
    # (60 63 65) 与 (67 70 72) 音程都是 [3,2]，起始音不同 → 模进
    melody = [{"pitch": p, "start_beat": i * 0.5} for i, p in enumerate([60, 63, 65, 67, 70, 72])]
    ms = aria_report.extract_motifs(melody)
    hit = [m for m in ms if m["intervals"] == [3, 2]]
    check("动机：检出移调模进", hit and hit[0]["technique"] == "模进（移调）", str(ms))


def test_extract_motifs_too_short():
    melody = [{"pitch": p, "start_beat": i * 0.5} for i, p in enumerate([60, 62, 64, 65])]
    check("动机：音符不足 5 个返回空", aria_report.extract_motifs(melody) == [], "应返回 []")


def test_extract_motifs_no_repeat():
    # 全部音程互不相同，无重复对 → 空
    melody = [{"pitch": p, "start_beat": i * 0.5} for i, p in enumerate([60, 62, 65, 69, 74, 80])]
    check("动机：无重复音程对返回空", aria_report.extract_motifs(melody) == [], "应返回 []")


def test_bar_pos():
    check("小节定位 0 拍", aria_report._bar_pos(0.0) == (1, 0.0), str(aria_report._bar_pos(0.0)))
    check("小节定位 5.5 拍", aria_report._bar_pos(5.5) == (2, 1.5), str(aria_report._bar_pos(5.5)))
    check("小节定位 8.0 拍", aria_report._bar_pos(8.0) == (3, 0.0), str(aria_report._bar_pos(8.0)))


# ────────────────────────── 单元：单文件分析 ──────────────────────────

def test_analyze_basic():
    p = mid_melody_only()
    r = aria_report.analyze_midi(p)
    check("分析 ok", r["ok"] is True, str(r))
    check("分析 BPM", r["bpm"] == 120.0, str(r["bpm"]))
    check("分析 拍号", r["time_signature"] == "4/4", str(r["time_signature"]))
    check("分析 音符数", r["note_count"] == len(MELODY_PITCHES), str(r["note_count"]))
    check("分析 旋律轨名", r["melody_track"] == "Lead", str(r["melody_track"]))
    check("分析 旋律音数", r["melody_note_count"] == len(MELODY_PITCHES), str(r["melody_note_count"]))
    check("分析 音色表", r["programs"] == ["Acoustic Grand Piano"], str(r["programs"]))
    check("分析 含动机", len(r["motifs"]) >= 1, str(r["motifs"]))
    check("分析 含风格", len(r["style"]) >= 1, str(r["style"]))
    check("分析 含调式", len(r["key_inference"]) == 3, str(r["key_inference"]))


def test_analyze_corrupt_returns_not_ok():
    p = write_mid("bad.mid", b"not a midi file at all")
    r = aria_report.analyze_midi(p)
    check("分析 坏文件 ok=False", r["ok"] is False and r.get("error"), str(r))
    check("分析 坏文件保留文件名", r["file"] == "bad.mid", str(r.get("file")))


def test_analyze_missing_file_raises():
    try:
        aria_report.analyze_midi(os.path.join(TMPDIR, "__nope__.mid"))
        check("分析 缺文件抛错", False, "未抛异常")
    except aria_report.UsageError:
        check("分析 缺文件抛错", True)


def test_drum_channel_excluded():
    """轨0 是 channel 9 鼓（音高更高），轨1 才该被选为旋律轨。"""
    drum = _vlq(0) + _meta(0x03, "Drums".encode()) + _seq_notes(9, [80, 81, 82, 83, 84], dur=120, vel=100)
    mel = (_vlq(0) + _meta(0x03, "Lead".encode()) + _vlq(0) + _ch(0xC0, 0) +
           _seq_notes(0, MELODY_PITCHES))
    p = write_mid("drums.mid", build_midi(480, _track(TEMPO_120), _track(drum), _track(mel)))
    r = aria_report.analyze_midi(p)
    check("鼓通道被排除出旋律轨", r["melody_track"] == "Lead", str(r["melody_track"]))
    check("鼓音符不计入旋律音数", r["melody_note_count"] == len(MELODY_PITCHES), str(r["melody_note_count"]))
    check("鼓音符仍计入总音符数", r["note_count"] == len(MELODY_PITCHES) + 5, str(r["note_count"]))


def test_melody_track_highest_average():
    low = _vlq(0) + _meta(0x03, "Bass".encode()) + _seq_notes(0, [40, 42, 43, 45, 47])
    high = (_vlq(0) + _meta(0x03, "Lead".encode()) + _vlq(0) + _ch(0xC0, 0) +
            _seq_notes(1, [72, 74, 76, 77, 79]))
    p = write_mid("two.mid", build_midi(480, _track(TEMPO_120), _track(low), _track(high)))
    r = aria_report.analyze_midi(p)
    check("旋律轨取平均音高最高者", r["melody_track"] == "Lead", str(r["melody_track"]))


def test_explicit_key_signature_used():
    """meta 调号存在时，风格判断的 key_mode 应优先取它。"""
    # 调号 0 升 0 降 = C 大调（major）
    ev = (_vlq(0) + _meta(0x59, b"\x00\x00") + _vlq(0) + _meta(0x03, "Lead".encode()) +
          _vlq(0) + _ch(0xC0, 0) + _seq_notes(0, MELODY_PITCHES))
    p = write_mid("keysig.mid", build_midi(480, _track(TEMPO_120), _track(ev)))
    r = aria_report.analyze_midi(p)
    check("读出 meta 调号", r["key_signature"] and r["key_signature"].get("mode") == "major",
          str(r["key_signature"]))
    check("风格判断可用小调/大调信息", any(s["style"] == "流行" for s in r["style"]), str(r["style"]))


# ────────────────────────── 单元：输入扫描 ──────────────────────────

def test_scan_input_single_file():
    p = mid_melody_only("solo.mid")
    check("扫描 单文件", aria_report.scan_input(p) == [p], "应返回单文件")


def test_scan_input_directory_sorted():
    d = fresh_tmpdir()
    for n in ("b.mid", "a.mid", "c.mid"):
        write_mid(n, build_midi(480, _track()))
    write_mid("ignore.txt", b"x")
    got = [os.path.basename(x) for x in aria_report.scan_input(d)]
    check("扫描 目录按名排序且只取 .mid", got == ["a.mid", "b.mid", "c.mid"], str(got))


def test_scan_input_missing_raises():
    try:
        aria_report.scan_input(os.path.join(TMPDIR, "__no_dir__"))
        check("扫描 缺路径抛错", False, "未抛异常")
    except aria_report.UsageError:
        check("扫描 缺路径抛错", True)


def test_scan_input_non_mid_file():
    p = write_mid("ignore2.txt", b"x")
    check("扫描 非 mid 单文件返回空", aria_report.scan_input(p) == [], "应返回 []")


# ────────────────────────── 单元：Markdown 渲染 ──────────────────────────

def test_render_markdown():
    r = aria_report.analyze_midi(mid_melody_only("render.mid"))
    md = aria_report.render_markdown([r], "decode/")
    check("报告 标题", md.startswith("# 旋律动机分析报告"), md[:40])
    check("报告 含概览表头", "| 文件 | BPM | 调式推测 | 风格（Top1） | 主旋律轨 | 动机数 |" in md, "缺概览表头")
    check("报告 含文件名行", "| render.mid |" in md, "缺文件名行")
    check("报告 含各分节", all(s in md for s in
          ("### 基本信息", "### 风格判断（启发式，供参考）", "### 调式推测", "### 旋律动机分析")),
          "缺分节")
    check("报告 含来源标签", "输入 decode/" in md, "缺来源标签")


def test_render_markdown_failed_file():
    r = aria_report.analyze_midi(write_mid("broken.mid", b"garbage"))
    md = aria_report.render_markdown([r], "x")
    check("报告 失败文件标注解码失败", "解码失败" in md, md)


def test_render_markdown_no_motif():
    # 只有 3 个音 → 无动机，应给出提示文案而非空白
    ev = _vlq(0) + _ch(0xC0, 0) + _seq_notes(0, [60, 62, 64])
    p = write_mid("sparse.mid", build_midi(480, _track(TEMPO_120), _track(ev)))
    r = aria_report.analyze_midi(p)
    md = aria_report.render_markdown([r], "x")
    check("报告 无动机时给提示", "旋律音符不足" in md, md)


# ────────────────────────── CLI 级 ──────────────────────────

def test_cli_report_stdout():
    p = mid_melody_only("cli.mid")
    code, out, err = cli("report", "--input", p)
    check("CLI 单文件退出码 0", code == 0, f"code={code} err={err}")
    check("CLI 输出 Markdown 报告", out.startswith("# 旋律动机分析报告"), out[:60])


def test_cli_format_json():
    p = mid_melody_only("cli2.mid")
    code, out, _ = cli("report", "--input", p, "--format", "json")
    data = json.loads(out)
    check("CLI --format json 退出码 0", code == 0, f"code={code}")
    check("CLI --format json 是数组", isinstance(data, list) and len(data) == 1, str(type(data)))
    check("CLI --format json 含关键字段",
          data[0]["ok"] is True and data[0]["melody_track"] == "Lead", str(data[0])[:200])


def test_cli_output_file():
    p = mid_melody_only("cli3.mid")
    out_path = os.path.join(TMPDIR, "report.md")
    code, out, _ = cli("report", "--input", p, "--output", out_path)
    body = open(out_path, encoding="utf-8").read()
    check("CLI --output 退出码 0", code == 0, f"code={code}")
    check("CLI --output 提示写入路径", "报告已写入" in out, out)
    check("CLI --output 文件内容完整", body.startswith("# 旋律动机分析报告"), body[:60])


def test_cli_output_missing_dir():
    p = mid_melody_only("cli4.mid")
    code, _, err = cli("report", "--input", p, "--output",
                       os.path.join(TMPDIR, "no_such_dir", "r.md"))
    check("CLI 输出目录不存在退出码 2", code == 2 and "输出目录不存在" in err, f"code={code} err={err}")


def test_cli_directory_input():
    d = fresh_tmpdir()
    write_mid("a.mid", build_midi(480, _track(TEMPO_120), _track(
        _vlq(0) + _meta(0x03, "Lead".encode()) + _vlq(0) + _ch(0xC0, 0) + _seq_notes(0, MELODY_PITCHES))))
    write_mid("b.mid", b"broken")
    code, out, _ = cli("report", "--input", d, "--format", "json")
    data = json.loads(out)
    check("CLI 目录扫描退出码 0", code == 0, f"code={code}")
    check("CLI 目录扫描 2 个文件", len(data) == 2, str(len(data)))
    check("CLI 目录扫描 好坏各一", sorted(x["ok"] for x in data) == [False, True], str(data))


def test_cli_empty_directory_exit1():
    d = fresh_tmpdir()
    open(os.path.join(d, "readme.txt"), "w").close()
    code, _, err = cli("report", "--input", d)
    check("CLI 无 mid 目录退出码 1", code == 1 and "未找到 .mid 文件" in err, f"code={code} err={err}")


def test_cli_missing_path_exit2():
    code, _, err = cli("report", "--input", os.path.join(TMPDIR, "__gone__"))
    check("CLI 输入路径不存在退出码 2", code == 2 and "输入路径不存在" in err, f"code={code} err={err}")


def test_cli_no_subcommand_exit2():
    code, out, _ = cli()
    check("CLI 无子命令退出码 2", code == 2 and "usage" in out.lower(), f"code={code}")


def test_cli_version():
    code, out, _ = cli("--version")
    check("CLI --version", code == 0 and aria_report.__version__ in out, out)


def test_cli_missing_input_arg_exit2():
    code, _, _ = cli("report")
    check("CLI 缺 --input 退出码 2", code == 2, f"code={code}")


def test_cli_stdout_utf8():
    code, out, _ = cli("report", "--input", mid_melody_only("utf8.mid"))
    raw = subprocess.run([sys.executable, TOOL, "report", "--input",
                          os.path.join(TMPDIR, "utf8.mid")], capture_output=True)
    check("CLI stdout 为 UTF-8 无替换符",
          code == 0 and "旋律动机分析报告".encode("utf-8") in raw.stdout
          and b"\xef\xbf\xbd" not in raw.stdout, raw.stdout[:120])


# ────────────────────────── 主流程 ──────────────────────────

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    try:
        for t in tests:
            t()
    finally:
        if os.path.isdir(TMPDIR):
            shutil.rmtree(TMPDIR)
    print(f"\n{len(tests)} 个用例：{PASS} 通过 / {FAIL} 失败")
    if _FAILURES:
        print("失败明细：")
        for f in _FAILURES:
            print(f"  - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
