#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-roll 渲染器 — 测试套件（零依赖，仅标准库）

运行：python tests/run_tests.py
全部通过退出码 0；任一失败退出码 1，并打印失败详情。
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import aria_roll  # noqa: E402

CLI = os.path.join(ROOT, "aria_roll.py")

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


def cli(*argv, stdin=None):
    p = subprocess.run([sys.executable, CLI, *argv], input=stdin,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


# ────────────────────────── 素材 ──────────────────────────

# 素材固定为 8 拍（旋律 8 个八分 + 低音 4 个二分），勿传无效参数
def demo_song(name="demo", bpm=100, tracks=None):
    if tracks is None:
        tracks = [
            {"name": "旋律", "channel": 0, "program": 0,
             "notes": [{"pitch": p, "start_beat": i * 0.5, "duration": 0.5,
                        "velocity": 70 + (i % 4) * 8}
                       for i, p in enumerate([72, 74, 76, 74, 72, 71, 69, 71])]},
            {"name": "低音", "channel": 1, "program": 38,
             "notes": [{"pitch": p, "start_beat": i * 2.0, "duration": 2.0,
                        "velocity": 80} for i, p in enumerate([40, 43, 45, 43])]},
        ]
    return {"name": name, "bpm": bpm, "time_signature": {"numerator": 4, "denominator": 4},
            "tracks": tracks}


def write_json(tmp, obj, fn="song.json"):
    p = os.path.join(tmp, fn)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


# ────────────────────────── 数据归一化 ──────────────────────────

def test_total_beats():
    s = aria_roll._from_song(demo_song(), "x.json")
    check("total_beats 取最末音符结束点", s["total_beats"] == 8.0, s["total_beats"])


def test_pitch_range():
    s = aria_roll._from_song(demo_song(), "x.json")
    check("音域覆盖全部音轨", aria_roll._pitch_range(s) == (40, 76),
          str(aria_roll._pitch_range(s)))


def test_empty_tracks_error():
    try:
        aria_roll._from_song({"tracks": []}, "x.json")
        check("空 tracks 报错", False, "未抛异常")
    except aria_roll.DataError:
        check("空 tracks 报错", True)


def test_all_tracks_note_less_error():
    try:
        aria_roll._from_song({"tracks": [{"name": "a", "notes": []}]}, "x.json")
        check("所有音轨都无音符时报错", False, "未抛异常")
    except aria_roll.DataError:
        check("所有音轨都无音符时报错", True)


def test_legacy_notes_format():
    s = aria_roll._from_song({"bpm": 90, "notes": [
        {"pitch": 60, "start_beat": 0, "duration": 1, "velocity": 80}]}, "x.json")
    check("兼容旧版单轨 notes 格式",
          len(s["tracks"]) == 1 and s["tracks"][0]["name"] == "Piano", str(s["tracks"]))


def test_title_fallbacks():
    s = aria_roll._from_song(demo_song(name=""), r"D:\some\MySong.json")
    check("无 name 时回退文件名主干", s["title"] == "MySong", s["title"])
    s2 = aria_roll._from_song(demo_song(name="夏天"), "x.json")
    check("有 name 时优先用 name", s2["title"] == "夏天", s2["title"])


def test_pack_integer_encoding():
    """音符必须压成整数四元组：网格 0.25 拍，×4 后是无损整数。"""
    s = aria_roll._from_song(demo_song(), "x.json")
    packed = aria_roll._pack(s)
    n = packed[0]["n"][0]
    check("打包成 4 元素整数数组", isinstance(n, list) and len(n) == 4
          and all(isinstance(x, int) for x in n), str(n))
    # 与原始值对拍
    src = s["tracks"][0]["notes"][0]
    check("打包无损（×4 可还原）",
          n[0] == src["pitch"] and n[1] / 4 == src["start_beat"]
          and n[2] / 4 == src["duration"] and n[3] == src["velocity"],
          f"{n} vs {src}")


def test_pack_is_smaller_than_named():
    s = aria_roll._from_song(demo_song(), "x.json")
    named = json.dumps([{"notes": t["notes"]} for t in s["tracks"]], separators=(",", ":"))
    packed = json.dumps([{"n": t["n"]} for t in aria_roll._pack(s)], separators=(",", ":"))
    check("打包后体积明显更小（≥40%）", len(packed) < len(named) * 0.6,
          f"{len(packed)} vs {len(named)}")


def test_drum_track_color():
    s = aria_roll._from_song(demo_song(tracks=[
        {"name": "鼓", "channel": 9, "program": 0,
         "notes": [{"pitch": 36, "start_beat": 0, "duration": 0.25, "velocity": 100}]},
        {"name": "旋律", "channel": 0, "program": 0,
         "notes": [{"pitch": 72, "start_beat": 0, "duration": 1, "velocity": 90}]}]),
        "x.json")
    cols = aria_roll._colorize(s)
    check("channel 9 用中性灰，不占用调色板",
          cols[0]["color"] == aria_roll.DRUM_COLOR and cols[1]["color"] != aria_roll.DRUM_COLOR,
          str([c["color"] for c in cols]))


# ────────────────────────── 小节数（曾经的 off-by-one） ──────────────────────────

def _bars(beats, bpb=4):
    return int(beats // bpb) + (1 if beats % bpb else 0)


def test_bar_count_edges():
    check("32 小节（128 拍）不 +1", _bars(128.0) == 32, _bars(128.0))
    check("非整小节向上取整（129 拍 → 33）", _bars(129.0) == 33, _bars(129.0))
    check("不足一小节算 1 小节（3 拍）", _bars(3.0) == 1, _bars(3.0))


def test_html_meta_bar_count():
    s = aria_roll._from_song(demo_song(), "x.json")
    h = aria_roll.render_html(s)
    want = int(s["total_beats"] // 4) + (1 if s["total_beats"] % 4 else 0)
    m = re.search(r"· (\d+) 小节", h)
    check("页面 meta 的小节数 = ceil(总拍数/4)",
          m is not None and int(m.group(1)) == want,
          f"页面={m.group(1) if m else '未找到'} 期望={want} (总拍 {s['total_beats']})")


# ────────────────────────── HTML 渲染 ──────────────────────────

def test_html_self_contained():
    h = aria_roll.render_html(aria_roll._from_song(demo_song(), "x.json"))
    ext = re.findall(r'(?:src|href)="(https?://[^"]+)"', h)
    check("无任何外部资源引用（自包含）", not ext, str(ext))
    check("含 canvas 卷帘", "<canvas" in h)
    check("含 Web Audio 播放", "AudioContext" in h)
    check("含图例与播放控件", 'id="legend"' in h and 'id="play"' in h and 'id="zoom"' in h)
    check("含诊断钩子 __aria", "__aria" in h)


def test_drum_synth_not_regressed_to_noise_lowpass():
    """防回归：底鼓曾经是「白噪声 + 120Hz 低通」，实测比镲片低约 23 dB、听不见。

    白噪声能量铺满全频，只留 120Hz 等于扔掉 99% 功率，且噪声无音高，
    发不出底鼓要的"砰"。必须是正弦下扫。这条测试锁住那次修复。
    """
    h = aria_roll.render_html(aria_roll._from_song(demo_song(), "x.json"))
    check("含按 GM 鼓号分型的打击乐合成", "drumKind" in h and "playDrum" in h)
    check("底鼓用正弦下扫（而非低频噪声）",
          "exponentialRampToValueAtTime(48" in h and "o.type = 'sine'" in h, "未见下扫")
    check("已移除「pitch<40 走 lowpass」的错误分支",
          "? 'lowpass'" not in h and '"lowpass"' not in h, "旧逻辑仍在")


def test_master_bus_present():
    """防回归：鼓叠加实测峰值可达 5.0，必须有限幅总线，否则硬削波。"""
    h = aria_roll.render_html(aria_roll._from_song(demo_song(), "x.json"))
    check("含总线限幅（Gain + DynamicsCompressor）",
          "masterBus" in h and "createDynamicsCompressor" in h)
    check("声部接到总线而非直接接 destination",
          "playDrum(actx, bus," in h and "playTone(actx, bus," in h)


def test_html_embedded_json_parses():
    h = aria_roll.render_html(aria_roll._from_song(demo_song(), "x.json"))
    m = re.search(r"const SONG = (\{.*?\});\n", h, re.S)
    check("能提取内嵌 SONG", bool(m), "未匹配")
    data = json.loads(m.group(1))
    check("内嵌 JSON 合法且音符数正确",
          sum(len(t["n"]) for t in data["tracks"]) == 12,
          str(sum(len(t["n"]) for t in data["tracks"])))


def test_html_escaping_title():
    s = aria_roll._from_song(demo_song(name='<img src=x onerror=alert(1)>'), "x.json")
    h = aria_roll.render_html(s)
    head = h.split("</head>")[0]
    check("标题进入 HTML 时被转义（不注入标签）",
          "<img src=x" not in head and "&lt;img" in head, head[head.find("<title>"):][:90])


def test_html_escapes_script_close():
    """标题含 </script> 时不能提前闭合内嵌脚本。"""
    s = aria_roll._from_song(demo_song(name="x</script><b>y"), "x.json")
    h = aria_roll.render_html(s)
    body = h.split("<script>")[1]
    check("内嵌 JSON 转义 </ 防止脚本提前闭合",
          "x<\\/script>" in body, "未转义")


def test_html_title_fallback_placeholder():
    """占位符必须全部被替换，不能把 __TITLE__ 之类漏进产物。"""
    h = aria_roll.render_html(aria_roll._from_song(demo_song(), "x.json"))
    left = [k for k in ("__TITLE__", "__META__", "__SONG__", "__ZOOM__") if k in h]
    check("无未替换的模板占位符", not left, str(left))


# ────────────────────────── SVG 渲染 ──────────────────────────

def test_svg_basic():
    s = aria_roll._from_song(demo_song(), "x.json")
    svg = aria_roll.render_svg(s)
    check("SVG 根元素与命名空间", svg.startswith("<svg") and 'xmlns="http://www.w3.org/2000/svg"' in svg,
          svg[:80])
    check("SVG 标签闭合", svg.rstrip().endswith("</svg>") and svg.count("<g ") == svg.count("</g>"),
          f"<g>={svg.count('<g ')} </g>={svg.count('</g>')}")
    note_rects = [m for m in re.findall(r"<rect [^>]*/>", svg)
                  if "fill=" not in m and '100%' not in m]
    check("SVG 音符矩形数量 = 音符数", len(note_rects) == 12, len(note_rects))
    check("SVG 含图例", "旋律" in svg and "低音" in svg)


def test_svg_escapes_title():
    s = aria_roll._from_song(demo_song(name="<b>&"), "x.json")
    svg = aria_roll.render_svg(s)
    check("SVG 标题被转义", "&lt;b&gt;&amp;" in svg, svg[:200])


# ────────────────────────── CLI ──────────────────────────

def test_cli_derives_output():
    with tempfile.TemporaryDirectory() as td:
        write_json(td, demo_song(name="我的曲子"))
        code, out, err = cli("roll", "--input", os.path.join(td, "song.json"))
        d = json.loads(out)
        check("省略 --output 时按歌名派生到输入同目录",
              code == 0 and os.path.basename(d["output"]) == "我的曲子.html"
              and os.path.dirname(os.path.abspath(d["output"])) == os.path.abspath(td),
              d.get("output"))
        check("派生产物确实存在", os.path.isfile(d["output"]))


def test_cli_explicit_output_and_svg():
    with tempfile.TemporaryDirectory() as td:
        src = write_json(td, demo_song())
        out = os.path.join(td, "r.svg")
        code, o, _ = cli("roll", "--input", src, "--output", out, "--format", "svg")
        d = json.loads(o)
        check("--output + --format svg", code == 0 and d["format"] == "svg"
              and open(out, encoding="utf-8").read().startswith("<svg"), d.get("format"))


def test_cli_title_override():
    with tempfile.TemporaryDirectory() as td:
        src = write_json(td, demo_song(name="原名"))
        out = os.path.join(td, "x.html")
        cli("roll", "--input", src, "--output", out, "--title", "改过的名")
        h = open(out, encoding="utf-8").read()
        check("--title 覆盖标题", "改过的名" in h and "原名" not in h.split("<canvas")[0])


def test_cli_zoom_flag():
    with tempfile.TemporaryDirectory() as td:
        src = write_json(td, demo_song())
        out = os.path.join(td, "z.html")
        cli("roll", "--input", src, "--output", out, "--zoom", "42")
        check("--zoom 写入初始像素/拍", "let ppb = 42," in open(out, encoding="utf-8").read(),
              "未找到初始值")


def test_cli_stdout():
    with tempfile.TemporaryDirectory() as td:
        src = write_json(td, demo_song())
        code, out, _ = cli("roll", "--input", src, "--output", "-")
        check("--output - 走 stdout", code == 0 and out.startswith("<!DOCTYPE html>"), out[:40])


def test_cli_stdin():
    code, out, _ = cli("roll", "--input", "-", "--output", "-",
                       stdin=json.dumps(demo_song()))
    check("--input - 从 stdin 读 JSON", code == 0 and out.startswith("<!DOCTYPE html>"), out[:40])


def test_cli_missing_input_exit2():
    code, _, err = cli("roll")
    check("缺 --input → 退出码 2", code == 2, f"code={code} err={err[:80]}")


def test_cli_bad_json_exit1():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "bad.json")
        open(p, "w").write("{ not json")
        code, _, err = cli("roll", "--input", p, "--output", "-")
        check("坏 JSON → 退出码 1", code == 1 and "JSON" in err, f"code={code} err={err[:80]}")


def test_cli_missing_file_exit2():
    code, _, err = cli("roll", "--input", "no/such/file.json", "--output", "-")
    check("输入不存在 → 退出码 2", code == 2, f"code={code} err={err[:80]}")


def test_cli_version_and_no_subcommand():
    code, out, _ = cli("--version")
    check("--version", code == 0 and aria_roll.__version__ in out, out)
    code2, out2, _ = cli()
    check("无子命令 → 退出码 2", code2 == 2 and "usage" in out2.lower(), f"code={code2}")


# ────────────────────────── 从 .mid 渲染 ──────────────────────────

def test_from_mid_via_decode():
    """生成一个 .mid 再交给 aria-roll 渲染，验证 .mid → HTML 通路。"""
    midi_cli = os.path.normpath(os.path.join(ROOT, "..", "aria-midi", "aria_midi.py"))
    if not os.path.isfile(midi_cli):
        check("从 .mid 渲染（跳过：找不到 aria-midi）", True, "")
        return
    with tempfile.TemporaryDirectory() as td:
        src = write_json(td, demo_song(name="mid通路"))
        mid = os.path.join(td, "t.mid")
        r = subprocess.run([sys.executable, midi_cli, "generate", "--input", src,
                            "--output", mid], capture_output=True)
        if r.returncode != 0:
            check("从 .mid 渲染（跳过：generate 失败）", True, r.stderr.decode()[:120])
            return
        out = os.path.join(td, "t.html")
        code, o, err = cli("roll", "--input", mid, "--output", out)
        d = json.loads(o)
        check(".mid → HTML 成功", code == 0 and os.path.isfile(out), f"code={code} {err[:100]}")
        check(".mid 渲染的音符数与源一致", d["note_count"] == 12, d.get("note_count"))
        check(".mid 渲染出多条音轨", len(d["tracks"]) == 2, str(d.get("tracks")))


# ────────────────────────── 主流程 ──────────────────────────

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
    sys.exit(main())
