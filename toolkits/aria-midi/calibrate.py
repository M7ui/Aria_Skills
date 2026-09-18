#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-midi calibrate —— 用真实人写语料标定「结构关系」指标的分位数。

用途：把阈值从"拍脑袋的常数"换成"真实作品的分位数"。
      产出 JSON 默认打到 stdout；包里预置的那份（reference/human-baseline.json）
      就是本脚本对 POP909 跑出来的结果，供 analyze --baseline 直接消费。

零依赖：只复用同目录 aria_midi.py 的 parse_midi（手写 MIDI 解析）+ 标准库。
        不需要 pip，不需要 install，不需要 numpy。

语料契约（通用，不绑定任何数据集）：
  --corpus-dir DIR
    DIR 下有子目录 → 每个子目录算一首（找带 MELODY 轨的 MIDI，找不到就取最大的 .mid）
     DIR 下直接是 .mid → 每个文件算一首
  POP909 的目录直接可用（001/001.mid + chord_midi.txt + beat_midi.txt），
  多余的标注文件会被忽略。

用法：
  python calibrate.py --corpus-dir /path/to/POP909 --limit 100
  python calibrate.py --corpus-dir /path/to/POP909 --out reference/human-baseline.json
  python calibrate.py --corpus-dir /path/to/POP909 --format md
"""

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aria_midi  # noqa: E402  （同目录，复用 parse_midi / pitch_name）

BEATS_PER_BAR = 4.0     # 分析窗口（拍）。可用 --window-beats 覆盖。
                        # 为什么是"窗口"不是"小节"：POP909 300 首里只有 39% 声明 4/4
                        # （1/4 有 151 首），且起音在 4 拍周期内近乎均匀分布、只有 18–25%
                        # 落在整拍上——这些文件**没有可识别的真实小节**。所以任何 per_bar
                        # 量都只能按显式窗口算，名字里也不再写 bar。
MIN_NOTES = 20          # 旋律音数少于这个的样本跳过
BREATH_MIN = 0.24       # 间隙达到这个拍数算一次「换气」
POSITION_GRID = 4.0     # 呼吸位置一致性固定按 4 拍网格算（与窗口解耦，否则指标随窗口漂）

# 12 个调上的大调五声音阶（C D E G A 的移调）
PENTATONICS = [{(r + x) % 12 for x in (0, 2, 4, 7, 9)} for r in range(12)]
# 12 个调上的大调音阶
MAJORS = [{(r + x) % 12 for x in (0, 2, 4, 5, 7, 9, 11)} for r in range(12)]


# ══════════════════════════════════════════════════════════════
# 语料发现
# ══════════════════════════════════════════════════════════════
def _track_score(track):
    """给一条轨打分，挑旋律轨用：有 MELODY 名字的最优先。"""
    name = (track.get("name") or "").upper()
    notes = track.get("notes") or []
    if not notes:
        return -1
    bonus = 100 if "MELODY" in name else (30 if "LEAD" in name or "VOCAL" in name else 0)
    avg = sum(n["pitch"] for n in notes) / len(notes)
    return bonus * 1000 + avg


def find_songs(corpus_dir):
    """返回 [(曲名, midi 路径)]。子目录优先，否则平铺 .mid。"""
    songs = []
    for entry in sorted(os.listdir(corpus_dir)):
        p = os.path.join(corpus_dir, entry)
        if os.path.isdir(p):
            mids = [f for f in sorted(os.listdir(p)) if f.lower().endswith(".mid")]
            if mids:
                songs.append((entry, os.path.join(p, mids[0] if len(mids) == 1 else _biggest(p, mids))))
        elif entry.lower().endswith(".mid"):
            songs.append((os.path.splitext(entry)[0], p))
    return songs


def _biggest(d, names):
    return max(names, key=lambda f: os.path.getsize(os.path.join(d, f)))


def load_melody(path):
    """读一首，返回 (旋律音符列表, bpm)。旋律轨 = MELODY 优先，否则平均音高最高。"""
    with open(path, "rb") as fh:
        data = fh.read()
    parsed = aria_midi.parse_midi(data)
    tracks = [t for t in parsed["tracks"] if t.get("notes")]
    if not tracks:
        return None, None
    best = max(tracks, key=_track_score)
    return best["notes"], parsed["bpm"] or 120


# ══════════════════════════════════════════════════════════════
# 指标（全部是"关系/组织"型，不是边缘统计；换音高躲不掉）
# ══════════════════════════════════════════════════════════════
def _best_fit(pcs, candidates):
    """返回覆盖该音级集合最多的那个音阶（用于五声率、大调率）。"""
    return max(candidates, key=lambda s: len(pcs & s))


def _slope(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


def metrics_for(notes, bpm):
    ns = sorted(notes, key=lambda n: (n["start_beat"], n["pitch"]))
    if len(ns) < MIN_NOTES:
        return None
    pts = [n["pitch"] for n in ns]
    span = max(pts) - min(pts)
    pcs = {p % 12 for p in pts}
    total_beats = max(n["start_beat"] + n["duration"] for n in ns) - ns[0]["start_beat"]
    bars_n = max(1, int(total_beats // BEATS_PER_BAR) + 1)

    per_bar = defaultdict(list)
    for n in ns:
        per_bar[int(n["start_beat"] // BEATS_PER_BAR)].append(n)
    bars = sorted(per_bar)

    m = {}
    # ── 音高材料 ───────────────────────────────────────────
    m["pitch_class_count"] = len(pcs)
    m["span"] = span
    m["pentatonic_rate"] = len(pcs & _best_fit(pcs, PENTATONICS)) / len(pcs)
    m["diatonic_rate"] = len(pcs & _best_fit(pcs, MAJORS)) / len(pcs)

    # ── 音程语汇 ───────────────────────────────────────────
    iv = [b["pitch"] - a["pitch"] for a, b in zip(ns, ns[1:]) if b["pitch"] - a["pitch"] != 0
          or True]
    iv = [b["pitch"] - a["pitch"] for a, b in zip(ns, ns[1:])]
    nz = [x for x in iv if x != 0]
    m["step_share"] = sum(1 for x in iv if abs(x) <= 3) / len(iv) if iv else 0
    up = [x for x in iv if x > 0]
    dn = [-x for x in iv if x < 0]
    m["asc_mean"] = sum(up) / len(up) if up else 0
    m["desc_mean"] = sum(dn) / len(dn) if dn else 0
    m["desc_minus_asc"] = m["desc_mean"] - m["asc_mean"]

    # ── 节奏与时值 ─────────────────────────────────────────
    durs = Counter(round(n["duration"], 3) for n in ns)
    m["duration_kinds"] = len(durs)
    m["top_duration_share"] = durs.most_common(1)[0][1] / len(ns)
    m["onset_grid"] = len({round(n["start_beat"] % 1.0, 3) for n in ns})

    # ── 连接与呼吸 ─────────────────────────────────────────
    gaps = [(a["start_beat"] + a["duration"], b["start_beat"] - (a["start_beat"] + a["duration"]))
            for a, b in zip(ns, ns[1:])]
    m["legato_rate"] = sum(1 for _, g in gaps if abs(g) < 1e-6) / len(gaps) if gaps else 0
    breaths = [(s % POSITION_GRID, g) for s, g in gaps if g >= BREATH_MIN]
    # 换气密度按「拍」算，**不除以窗口** —— 否则指标会随窗口线性放大，等于量了个常数
    m["breaths_per_beat"] = len(breaths) / total_beats if total_beats else 0
    m["breaths_per_window"] = len(breaths) / bars_n
    if breaths:
        bp = Counter(round(s * 4) / 4 for s, _ in breaths)
        m["breath_position_consistency"] = bp.most_common(1)[0][1] / len(breaths)
        m["breath_share_strong"] = sum(1 for _, g in breaths if g >= 0.75) / len(breaths)
    else:
        m["breath_position_consistency"] = 0
        m["breath_share_strong"] = 0

    # ── 起句手势（用音程形状，不用绝对音高 → 移位再现也算复现）──
    shapes_dir, shapes_iv = [], []
    for b in bars:
        seg = sorted(per_bar[b], key=lambda n: n["start_beat"])[:3]
        if len(seg) < 3:
            continue
        sgn = [1 if seg[i + 1]["pitch"] > seg[i]["pitch"] else
               (-1 if seg[i + 1]["pitch"] < seg[i]["pitch"] else 0) for i in range(2)]
        shapes_dir.append(tuple(sgn))
        shapes_iv.append(tuple(seg[i + 1]["pitch"] - seg[i]["pitch"] for i in range(2)))
    if shapes_dir:
        m["opening_direction_concentration"] = Counter(shapes_dir).most_common(1)[0][1] / len(shapes_dir)
        m["opening_interval_concentration"] = Counter(shapes_iv).most_common(1)[0][1] / len(shapes_iv)
        m["opening_kinds_ratio"] = len(set(shapes_dir)) / len(shapes_dir)
    else:
        m["opening_direction_concentration"] = 0
        m["opening_interval_concentration"] = 0
        m["opening_kinds_ratio"] = 0

    # ── 窗口级问答与幅度（名字不写 bar：语料里没有可识别的真实小节）──
    peaks = [max(per_bar[b], key=lambda n: n["pitch"])["pitch"] for b in bars]
    if len(peaks) >= 3:
        diffs = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
        sgns = [1 if d > 0 else (-1 if d < 0 else 0) for d in diffs]
        alt = sum(1 for a, b2 in zip(sgns, sgns[1:]) if a != 0 and b2 != 0 and a != b2)
        m["window_peak_alternation"] = alt / (len(sgns) - 1) if len(sgns) > 1 else 0
    else:
        m["window_peak_alternation"] = 0
    amb = [max(n["pitch"] for n in per_bar[b]) - min(n["pitch"] for n in per_bar[b]) for b in bars]
    m["window_ambitus_ratio"] = (sum(amb) / len(amb)) / span if span else 0

    # ── 全曲重心走向 ───────────────────────────────────────
    cog = [sum(n["pitch"] for n in per_bar[b]) / len(per_bar[b]) for b in bars]
    m["cog_slope"] = _slope([float(b) for b in bars], cog)
    k = max(2, len(cog) // 4)
    m["cog_drift"] = sum(cog[-k:]) / k - sum(cog[:k]) / k

    # ── 长音的使用 ─────────────────────────────────────────
    longs = [n for n in ns if n["duration"] >= 2.0]
    m["long_note_count"] = len(longs)
    last = max(ns, key=lambda n: n["start_beat"] + n["duration"])
    m["longest_note_is_last"] = 1.0 if (longs and abs(last["duration"] - max(n["duration"] for n in ns)) < 1e-6) else 0.0
    m["final_note_duration"] = last["duration"]

    # ── 力度 ───────────────────────────────────────────────
    vels = [n["velocity"] for n in ns]
    m["velocity_kinds"] = len(set(vels))
    m["velocity_spread"] = max(vels) - min(vels)

    # ── 终止落点 ───────────────────────────────────────────
    tonic = None
    for r in range(12):
        if r in pcs:
            sc = MAJORS[r]
            if len(pcs & sc) / len(pcs) >= 0.9:
                tonic = r
                break
    if tonic is None:
        tonic = max(range(12), key=lambda r: len(pcs & MAJORS[r]))
    ends = [sorted(per_bar[b], key=lambda n: n["start_beat"] + n["duration"])[-1] for b in bars]
    m["tonic_ending_rate"] = sum(1 for e in ends if e["pitch"] % 12 == tonic) / len(ends)

    m["_bars"] = bars_n
    m["_notes"] = len(ns)
    return m


# ══════════════════════════════════════════════════════════════
# 分位数
# ══════════════════════════════════════════════════════════════
QUANTILES = [("p05", 0.05), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p95", 0.95)]


# ══════════════════════════════════════════════════════════════
# 计划层指标（把 plan.json 的每一项放到真人作品里量一遍）
#   用途：写计划时不再靠猜——"一句该走多远""呼吸点落在哪""动机该出现几次"
#   都有真人作品的分位数兜底。deriving 用 plan_check.derive（4 拍窗口 / 4 小节乐句）。
# ══════════════════════════════════════════════════════════════
PLAN_METRIC_ROLE = {
    "phrase_len_bars": ("descriptive", "乐句长度（本工具按 4 小节切）"),
    "phrase_travel_mean": ("diagnostic",
                           "每句「起音→目标音」的平均音程（半音）：过大=每句都在大跳，"
                           "过小=句子没有方向"),
    "phrase_travel_max": ("descriptive", "最远的一句走了多少半音"),
    "phrase_travel_span_ratio": ("diagnostic",
                                 "句内行程 / 全曲音域：接近 1 = 每句都跑遍全场（无音区层级）"),
    "breath_share": ("diagnostic", "有呼吸点的乐句占比：0 = 全曲不换气"),
    "breath_pos_in_phrase": ("descriptive", "呼吸点落在句内的相对位置（0=句首，1=句尾）"),
    "motif_recurrence": ("diagnostic",
                         "以同一手势起句的乐句占比：高 = 动机被反复使用（Wait Day 0.67）"),
    "climax_position": ("style", "全曲最高音的位置（占比）"),
    "section_non4_share": ("style", "长度不是 4 倍数的段落占比"),
    "energy_fluctuation": ("diagnostic",
                           "逐段能量（密度）相对均值的起伏：0 = 一条平线"),
}


def plan_metrics(plan):
    """从一个 plan.json 里提取计划层指标。"""
    ph = plan.get("phrases") or []
    if len(ph) < 2:
        return None
    import plan_check as PC
    root = PC.PC.index(plan["key"]["root"]) if plan.get("key", {}).get("root") in PC.PC else 0
    mode = plan.get("key", {}).get("mode", "major")
    m = {}
    travel, ratios = [], []
    spans = []
    for p in ph:
        s0, g0, c0 = PC.pnum(p.get("start")), PC.pnum(p.get("goal")), PC.pnum(p.get("cadence"))
        if s0 is None or g0 is None:
            continue
        travel.append(abs(g0 - s0))
        if c0 is not None:
            spans.append(c0)
    if not travel:
        return None
    # 全曲音域（用乐句起/目/止音近似）
    pts = [x for p in ph for x in (PC.pnum(p.get("start")), PC.pnum(p.get("goal")),
                                   PC.pnum(p.get("cadence"))) if x is not None]
    span = (max(pts) - min(pts)) if pts else 0
    m["phrase_len_bars"] = sum(int(p["bars"][1]) - int(p["bars"][0]) + 1
                               for p in ph if p.get("bars")) / float(len(ph))
    m["phrase_travel_mean"] = sum(travel) / float(len(travel))
    m["phrase_travel_max"] = max(travel)
    m["phrase_travel_span_ratio"] = (sum(travel) / len(travel)) / span if span else 0
    m["breath_share"] = sum(1 for p in ph if p.get("breath")) / float(len(ph))
    pos = []
    for p in ph:
        bt = p.get("breath")
        if isinstance(bt, str) and ":" in bt and p.get("bars"):
            try:
                bb, beat = bt.split(":")
                a, b = int(p["bars"][0]), int(p["bars"][1])
                tot = (b - a + 1) * float(plan.get("window_beats") or 4)
                pos.append(((int(bb) - a) * float(plan.get("window_beats") or 4) + float(beat))
                           / tot if tot else 0)
            except ValueError:
                pass
    m["breath_pos_in_phrase"] = sum(pos) / len(pos) if pos else 0
    # 动机复现：起句手势与全曲最常见手势相同的乐句占比
    shapes = []
    for p in ph:
        s0, g0 = PC.pnum(p.get("start")), PC.pnum(p.get("goal"))
        if s0 is not None and g0 is not None:
            shapes.append(1 if g0 > s0 else (-1 if g0 < s0 else 0))
    if shapes:
        from collections import Counter as _C
        m["motif_recurrence"] = _C(shapes).most_common(1)[0][1] / float(len(shapes))
    else:
        m["motif_recurrence"] = 0
    cl = plan.get("climax") or {}
    bars_total = max((int(s["bars"][1]) for s in plan.get("form") or [] if s.get("bars")),
                     default=0)
    m["climax_position"] = (cl.get("bar", 0) / float(bars_total)) if bars_total else 0
    secs = plan.get("form") or []
    m["section_non4_share"] = (sum(1 for s in secs if s.get("bars")
                                   and (int(s["bars"][1]) - int(s["bars"][0]) + 1) % 4 != 0)
                               / float(len(secs))) if secs else 0
    lv = [e.get("level") for e in plan.get("energy") or []
          if isinstance(e.get("level"), (int, float))]
    # 归一化后的极差恒为 1.0（最响段=1、空段=0），是退化量；改用相对均值的起伏
    mean_lv = (sum(lv) / len(lv)) if lv else 0
    m["energy_fluctuation"] = ((max(lv) - min(lv)) / mean_lv) if mean_lv else 0
    return m

# 每个指标的角色。这份表是标定跑出来之后才敢下的判断，依据见 reference/human-baseline.json：
#   diagnostic          —— 两端都可能是病，可用来提示异常；不设通过线
#   style               —— 个人风格差异；已知好作品会在分布外，禁止当判定
#   convention_dependent —— 量的是制作/量化/导出习惯，不是音乐（跨工具不可比）
METRIC_ROLE = {
    "breaths_per_beat": ("diagnostic",
                         "换气密度（按拍，与窗口无关）：0 = 完全不换气（四拍），"
                         ">0.45 = 碎到无法成句（霓虹夜行 0.50、晴朗日 0.66）；Wait Day 0.11 落在区间内"),
    "breaths_per_window": ("descriptive",
                           "同上的窗口版本，仅便于阅读（×1 窗口 = 4 拍 = 一个 4/4 小节）"),
    "step_share": ("diagnostic",
                   "过低 = 跳进碎片（霓虹夜行 0.38 < p05），过高 = 音阶练习曲（晴朗日 0.92 > p95）"),
    "breath_position_consistency": ("diagnostic",
                                    "0 = 呼吸位置完全随机（四拍）；按固定 4 拍网格算，与窗口解耦"),
    "window_ambitus_ratio": ("descriptive", "单窗口音域占比；描述用，随窗口变化（窗口变宽必然变大）"),
    "window_peak_alternation": ("style",
                                "Wait Day 0.73 与晚归 0.73 都 > p95，不具判别力——反映「音区问答」手法的有无"),
    "opening_direction_concentration": ("style",
                                        "Wait Day 0.75 与三首机写都 > p95，不具判别力"),
    "opening_interval_concentration": ("style",
                                       "Wait Day 0.50 > p95；是个人起句习惯"),
    "opening_kinds_ratio": ("descriptive", "起句型的分散度"),
    "cog_drift": ("style",
                  "全曲重心走向；Wait Day -1.83 < p05（下沉），机写全部在区间内——个人选择"),
    "cog_slope": ("style", "同上，按小节计的斜率"),
    "tonic_ending_rate": ("style",
                          "Wait Day 0.58 与四拍 0.50 都 > p95；不具判别力"),
    "long_note_count": ("style", "长音数量；Wait Day 1 首 < p05，POP909 中位 14"),
    "longest_note_is_last": ("style", "最长音是否在末尾"),
    "final_note_duration": ("style", "末音时值"),
    "asc_mean": ("descriptive", "上行平均音程"),
    "desc_mean": ("descriptive", "下行平均音程"),
    "desc_minus_asc": ("descriptive",
                       "POP909 中位 -0.27（下行略小），Wait Day +0.33 在 p75~p95 之间——倾向而非定律"),
    "span": ("style", "音域；Wait Day 12 < p05，窄音域是个人选择"),
    "pitch_class_count": ("descriptive", "用到的音级数"),
    "pentatonic_rate": ("descriptive", "无判别力：所有作品都在 0.62–0.71"),
    "diatonic_rate": ("descriptive", "调内率"),
    "duration_kinds": ("convention_dependent", "量的是量化精度（POP909 未量化，中位 76 种）"),
    "top_duration_share": ("convention_dependent",
                           "POP909 中位 0.079 vs Wait Day 0.789 —— 量的是量化习惯，不是节奏语汇"),
    "onset_grid": ("convention_dependent", "起音落在多少个拍内位置上；受量化影响"),
    "legato_rate": ("convention_dependent",
                    "POP909 中位 0.007 vs Wait Day 0.93 —— 相差两个数量级，量的是音符落点习惯"),
    "velocity_kinds": ("convention_dependent", "导出时是否拉平力度（本地 9 首里 5 首被拉平）"),
    "velocity_spread": ("convention_dependent", "同上"),
}


def percentile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def summarize(rows):
    keys = sorted({k for r in rows for k in r if not k.startswith("_")})
    out = {}
    for k in keys:
        vals = [r[k] for r in rows if r.get(k) is not None]
        if not vals:
            continue
        rec = {name: round(percentile(vals, q), 4) for name, q in QUANTILES}
        rec["mean"] = round(sum(vals) / len(vals), 4)
        out[k] = rec
    return out


# ══════════════════════════════════════════════════════════════
def main():
    global BEATS_PER_BAR
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="用人写语料标定结构指标的分位数（零依赖）")
    ap.add_argument("--corpus-dir", required=True, help="语料根目录（子目录或平铺 .mid）")
    ap.add_argument("--out", default=None, help="输出 JSON 路径；省略则写 stdout")
    ap.add_argument("--limit", type=int, default=0, help="只取前 N 首（0 = 全部）")
    ap.add_argument("--format", choices=["json", "md"], default="json")
    ap.add_argument("--source", default=None, help="语料来源说明（写进产出，便于追溯）")
    ap.add_argument("--window-beats", type=float, default=BEATS_PER_BAR,
                    help="分析窗口（拍），默认 4（即 4/4 的一小节）。"
                         "语料若没有可识别的真实小节，改这个只影响 window_* 系列指标")
    a = ap.parse_args()

    BEATS_PER_BAR = a.window_beats

    if not os.path.isdir(a.corpus_dir):
        raise SystemExit("语料目录不存在: %s" % a.corpus_dir)
    songs = find_songs(a.corpus_dir)
    if a.limit:
        songs = songs[:a.limit]
    if not songs:
        raise SystemExit("在 %s 下没找到任何 MIDI" % a.corpus_dir)

    rows, skipped, prows = [], [], []
    for name, path in songs:
        try:
            notes, bpm = load_melody(path)
        except Exception as e:                       # 单个样本坏掉不该中断标定
            skipped.append((name, "解析失败: %s" % e))
            continue
        m = metrics_for(notes or [], bpm or 120)
        if m is None:
            skipped.append((name, "旋律音数不足 %d" % MIN_NOTES))
            continue
        m["_name"] = name
        rows.append(m)
        try:                                     # 计划层：反推一份计划再量
            import plan_check as _PC
            pm = plan_metrics(_PC.derive(path, None, BEATS_PER_BAR))
            if pm:
                prows.append(pm)
        except Exception:
            pass                                 # 计划层算不出来不该拖垮音符层标定

    if not rows:
        raise SystemExit("没有可用样本（全部被跳过）")

    result = {
        "source": a.source or os.path.basename(os.path.abspath(a.corpus_dir)),
        "songs_used": len(rows),
        "songs_skipped": len(skipped),
        "generator": "aria-midi calibrate",
        "window_beats": a.window_beats,
        "note": "分位数来自真实人写语料，是「参照」不是「阈值」：已知好作品会落在分布之外"
                "（Wait Day 在 6 项指标上超出 p05~p95）。role=diagnostic 才可用于提示异常，"
                "role=style 禁止当判定，role=convention_dependent 连跨工具比较都不该做。"
                "名字里的 window 指 %g 拍的分析窗口——语料没有可识别的真实小节，"
                "window_* 系列指标随窗口变化，改窗口需重跑标定。" % a.window_beats,
        "roles": {k: {"role": r, "why": w} for k, (r, w) in METRIC_ROLE.items()},
        "metrics": summarize(rows),
        "plan_metrics": summarize(prows) if prows else {},
        "plan_metric_roles": {k: {"role": r, "why": w}
                              for k, (r, w) in PLAN_METRIC_ROLE.items()} if prows else {},
    }

    if a.format == "md":
        lines = ["# 人写语料结构基线", "",
                 "来源：%s ｜ 样本 %d 首（跳过 %d）" % (result["source"], result["songs_used"],
                                                    result["songs_skipped"]), "",
                 "| 指标 | p05 | p25 | p50 | p75 | p95 | 均值 |", "|---|---|---|---|---|---|---|"]
        for k, v in result["metrics"].items():
            lines.append("| `%s` | %s | %s | %s | %s | %s | %s |"
                         % (k, v["p05"], v["p25"], v["p50"], v["p75"], v["p95"], v["mean"]))
        text = "\n".join(lines) + "\n"
    else:
        text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("已写入 %s（%d 首，跳过 %d）" % (a.out, len(rows), len(skipped)), file=sys.stderr)
        for n, why in skipped[:5]:
            print("  跳过 %s：%s" % (n, why), file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
