#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人机分析报告的测量脚本（复现 docs/人机分析报告.md 里的数字）

用法：
  python docs/measure.py                      # 输出两张对照表 + 响度峰/平滑 CV
  python docs/measure.py --detail             # 额外输出 Wait Day 的动机与节奏型序列
  python docs/measure.py --human-dir <目录> --machine-dir <目录>

依赖同包的 aria-decode（读 .mid）与 aria-midi（analyze 取小节级结构指标），
零第三方依赖。

设计注记（踩过的坑，勿改回去）：
  · 能量用**响度加权** Σ(velocity/127)²，不用音符数 —— 音数会把「军鼓滚奏」
    这类音多但力度中等的段落算成高能量，得出错误的峰值位置。
  · 平滑曲线用滑动平均（默认 8 小节），把「4 小节单元内部的周期性摆动」
    抹平，否则会把周期性微波动误算成结构事件。
  · 单轨多声部（低音+和弦+旋律同轨）必须先按音区拆旋律层，否则相邻音会
    出现跨声部虚假大跳，所有旋律指标失效。
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # 本包根目录
ARIA_DECODE = os.path.join(ROOT, "toolkits", "aria-decode", "aria_decode.py")
ARIA_MIDI = os.path.join(ROOT, "toolkits", "aria-midi", "aria_midi.py")
NAMES = "C C# D D# E F F# G G# A A# B".split()


def nm(p):
    return NAMES[p % 12] + str(p // 12 - 1)


def decode(path):
    p = subprocess.run([sys.executable, ARIA_DECODE, "decode", "--input", path,
                        "--no-events", "--output", "-"], capture_output=True)
    if p.returncode:
        raise SystemExit("解码失败 %s: %s" % (path, p.stderr.decode("utf-8", "replace")[:200]))
    return json.loads(p.stdout.decode("utf-8"))


def bar_structure(notes, bpm):
    """调 aria-midi analyze 取小节级结构指标（与报告口径一致）。"""
    song = {"bpm": bpm, "tracks": [{"name": "m", "channel": 0, "program": 0,
            "notes": [{"pitch": int(n["pitch"]), "start_beat": float(n["start_beat"]),
                       "duration": float(n["duration"]), "velocity": int(n["velocity"])}
                      for n in notes]}]}
    f = tempfile.mktemp(suffix=".json")
    try:
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(song, fh, ensure_ascii=False)
        r = subprocess.run([sys.executable, ARIA_MIDI, "analyze", "--input", f],
                           capture_output=True)
        if r.returncode:
            return None
        return json.loads(r.stdout.decode("utf-8"))["details"]["structure"]["bar_structure"]
    finally:
        if os.path.exists(f):
            os.unlink(f)


def loudness_curve(notes, nbars):
    """每小节响度加权能量 —— 不用音符数（见文件头注记）。"""
    curve = [0.0] * nbars
    for n in notes:
        b = int(n["start_beat"] // 4)
        if 0 <= b < nbars:
            curve[b] += (n["velocity"] / 127.0) ** 2
    return curve


def smooth(curve, win=8):
    w = min(win, max(2, len(curve) // 4))
    return [statistics.mean(curve[max(0, i - w // 2):i + w // 2 + 1])
            for i in range(len(curve))]


def peak_pos(curve, win=8):
    nz = [i for i, v in enumerate(curve) if v]
    if not nz:
        return None, None
    body = curve[nz[0]:nz[-1] + 1]
    sm = smooth(body, win)
    mean = statistics.mean(sm)
    return round(100 * sm.index(max(sm)) / len(sm)), round(statistics.pstdev(sm) / mean, 2) if mean else 0


def melody_layer(notes):
    """单轨多声部 → 取音高分布上段作旋律层（≥第 55 百分位）。"""
    ps = sorted(n["pitch"] for n in notes)
    if not ps:
        return []
    thr = ps[int(len(ps) * 0.55)]
    return [n for n in notes if n["pitch"] >= thr]


def measure(name, path, from_song=None, track=None):
    dur = None
    if from_song:
        s = json.load(open(path, encoding="utf-8"))
        allnotes = [n for t in s["tracks"] for n in t["notes"]]
        bpm = s["bpm"]
        if track:
            mel = [x for x in s["tracks"] if x["name"] == track][0]["notes"]
        else:
            mel = max(s["tracks"], key=lambda t: sum(n["pitch"] for n in t["notes"]) /
                      max(1, len(t["notes"])))["notes"]
    else:
        d = decode(path)
        allnotes, bpm = d["notes"], d["global"]["bpm"]
        mel = melody_layer(allnotes)
        dur = round(d["global"]["duration_sec"])       # .mid 用文件真实时长
    nb = int(max(n["start_beat"] + n["duration"] for n in allnotes) // 4) + 1
    bs = bar_structure(mel, bpm)
    pk, cv = peak_pos(loudness_curve(allnotes, nb))
    ps = [n["pitch"] for n in allnotes]
    return dict(name=name, bpm=bpm, sec=dur or round(nb * 4 / bpm * 60),
                notes=len(allnotes), bars=nb, kinds=len(set(ps)),
                reuse=round(len(allnotes) / max(1, len(set(ps))), 1),
                head=bs["head_reuse"] if bs else None,
                rhy=bs["rhythm_reuse"] if bs else None,
                kind=bs["structure_kind"] if bs else "—",
                peak=pk, cv=cv)


def table(title, rows):
    print("=== %s ===" % title)
    print("  %-20s %4s %5s %6s %6s %7s %8s %8s  %s" % (
        "文件", "BPM", "秒", "音符", "音高种", "复用", "头重复", "节奏重复", "结构类型"))
    for r in rows:
        print("  %-20s %4g %5d %6d %6d %6.1f %7.0f%% %7.0f%%  %s" % (
            r["name"], r["bpm"], r["sec"], r["notes"], r["kinds"], r["reuse"],
            (r["head"] or 0) * 100, (r["rhy"] or 0) * 100, r["kind"]))
    hs = [r["head"] for r in rows if r["head"] is not None]
    rs = [r["rhy"] for r in rows if r["rhy"] is not None]
    pks = sorted(r["peak"] for r in rows if r["peak"] is not None)
    cvs = [r["cv"] for r in rows if r["cv"] is not None]
    print("  均值： 头重复 %.0f%%   节奏重复 %.0f%%   响度峰中位 %s%%   平滑CV %.2f"
          % (100 * statistics.mean(hs), 100 * statistics.mean(rs),
             pks[len(pks) // 2] if pks else "—",
             statistics.mean(cvs) if cvs else 0))
    print()
    return rows


def detail_waitday(path):
    """Wait Day 的动机 / 节奏型序列（报告第 5 节）。"""
    d = decode(path)
    mel = [n for n in d["notes"] if n["pitch"] >= 67]
    bybar = defaultdict(list)
    for n in mel:
        bybar[int(n["start_beat"] // 4) + 1].append(n)
    for b in bybar:
        bybar[b].sort(key=lambda x: x["start_beat"])

    print("=== Wait Day 旋律层细节 ===")
    heads = Counter(tuple(n["pitch"] for n in bybar[b][:3]) for b in bybar if len(bybar[b]) >= 3)
    print("  开头细胞（前 3 音）：")
    for k, v in heads.most_common():
        print("    %-22s 音程 %-8s ×%d" % (" → ".join(nm(p) for p in k),
              " ".join("%+d" % (k[i + 1] - k[i]) for i in range(len(k) - 1)), v))

    rh = {b: tuple(round(n["start_beat"] % 4, 2) for n in bybar[b])
          for b in bybar if len(bybar[b]) >= 3}
    lab = {}
    for i, (k, _) in enumerate(Counter(rh.values()).most_common()):
        lab[k] = "ABCDEFGH"[i]
    print("  节奏型明细：")
    for k, v in Counter(rh.values()).most_common():
        print("    %s = %-40s ×%d  小节 %s" % (lab[k], " ".join(str(x) for x in k), v,
              [b for b in sorted(rh) if rh[b] == k]))
    if 17 in rh:
        print("  第 17-32 小节的节奏型序列：")
        print("    小节 :", " ".join("%2d" % b for b in range(17, max(rh) + 1)))
        print("    型   :", " ".join(" %s" % lab.get(rh.get(b), "·") for b in range(17, max(rh) + 1)))

    mel_ps = [n["pitch"] for n in mel]
    iv = [mel_ps[i + 1] - mel_ps[i] for i in range(len(mel_ps) - 1)]
    step = sum(1 for x in iv if abs(x) <= 2)
    print("  旋律层：%d 音  只用 %d 个音高（复用 %.1f）  级进 %d/%d = %.0f%%"
          % (len(mel_ps), len(set(mel_ps)), len(mel_ps) / len(set(mel_ps)),
             step, len(iv), 100 * step / max(1, len(iv))))


def main():
    ap = argparse.ArgumentParser(description="人机分析报告的测量脚本")
    ap.add_argument("--human-dir", default=r"D:\document\midi", help="人写 MIDI 目录")
    ap.add_argument("--machine-dir", default=os.path.normpath(os.path.join(ROOT, "..")),
                    help="机写 song.json 所在目录（默认本包上一级）")
    ap.add_argument("--wait-day", default=r"C:\Users\Admin\Downloads\Wait Day.mid")
    ap.add_argument("--detail", action="store_true", help="额外输出 Wait Day 细节")
    args = ap.parse_args()

    # 人写：目录内全部 .mid（不足 4 个可用小节、算不出小节级指标的文件跳过并列出）
    human, skipped = [], []
    if os.path.isdir(args.human_dir):
        for fn in sorted(os.listdir(args.human_dir)):
            if fn.lower().endswith((".mid", ".midi")):
                r = measure(fn, os.path.join(args.human_dir, fn))
                (human if r["head"] is not None else skipped).append(r)
    if os.path.isfile(args.wait_day):
        r = measure("Wait Day.mid", args.wait_day)
        (human if r["head"] is not None else skipped).append(r)
    for r in skipped:
        print("  [跳过] %-22s 仅 %d 小节，不足以计算小节级指标" % (r["name"], r["bars"]))

    # 机写：约定「<歌名>/song.json」布局
    machine = []
    md = args.machine_dir
    for song, track in (("Wait Night", None), ("晴朗日", "旋律"),
                        ("霓虹夜行", "主音Lead"), ("summer beach", "旋律")):
        p = os.path.join(md, song, "song.json")
        if os.path.isfile(p):
            machine.append(measure(song, p, from_song=True, track=track))

    if skipped:
        print()
    table("人写（%d 首）" % len(human), human)
    table("机写（%d 首）" % len(machine), machine)

    if args.detail and os.path.isfile(args.wait_day):
        detail_waitday(args.wait_day)
    return 0


if __name__ == "__main__":
    sys.exit(main())
