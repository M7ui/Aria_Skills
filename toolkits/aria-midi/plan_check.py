#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-midi plan_check —— 计划层检查器：**检查在写音符之前**。

为什么要有这一层：现行工作流是「写音符 → 看统计指标」，而统计指标在音符层面没有梯度
（把一个音移 ±7 半音，总分一分不动），于是只剩约束满足——能局部满足的禁令必然被局部满足，
叠加起来就是"什么都不违反、也什么都不说"。这里把检查对象换成**结构本身**：
计划里有没有目标、动机有没有再现、呼吸点在哪里、声部音区怎么分——这些换音高躲不掉。

三种用法：

  # 1) 只查计划是否完整、自洽（不写任何一个音符就能查）
  python plan_check.py --plan plan.json

  # 2) 计划 + 成品：查音符有没有把计划实现出来（骨架音/目标音/高潮/呼吸/动机/音区）
  python plan_check.py --plan plan.json --song song.json

  # 3) 从已有作品反推一份草稿计划（用于给旧作补计划，或学习结构）
  python plan_check.py --derive song.json [--chords chords.json] [--out plan.json]

设计原则（这一条比任何规则都重要）：
  **这个检查器必须能对已知的好作品判"通过"。** 实测 Wait Day 在 6 项统计指标上超出人写
  p05~p95，所以凡"统计分布类"的判断一律不进门；门只留"结构件在不在、自不自洽"。
  拿不准的项一律降为提示（advisory），不计入通过率。
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

PC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = (0, 2, 4, 5, 7, 9, 11)
NAT_MINOR = (0, 2, 3, 5, 7, 8, 10)
DEG_MAJOR = {0: 1, 2: 2, 4: 3, 5: 4, 7: 5, 9: 6, 11: 7}
DEG_MINOR = {0: 1, 2: 2, 3: 3, 5: 4, 7: 5, 8: 6, 10: 7}


def pname(p):
    return PC[p % 12] + str(p // 12 - 1)


def pnum(s):
    """'C4' → 60；非法返回 None。"""
    if not isinstance(s, str) or not s:
        return None
    i = 1 if len(s) > 1 and s[1] in "#b" else 0
    nm, oct_ = s[:i + 1], s[i + 1:]
    if nm not in PC or not oct_.lstrip("-").isdigit():
        return None
    return PC.index(nm) + (int(oct_) + 1) * 12


def scale_of(root_pc, mode):
    return {(root_pc + x) % 12 for x in (MAJOR if mode == "major" else NAT_MINOR)}


def degree_of(pitch, root_pc, mode):
    return (DEG_MAJOR if mode == "major" else DEG_MINOR).get((pitch - root_pc) % 12)


# ══════════════════════════════════════════════════════════════
# 计划层检查（不需要任何音符）
# ══════════════════════════════════════════════════════════════
def _sections(plan):
    return plan.get("form") or []


def _section_bars(plan):
    out = []
    for s in _sections(plan):
        b = s.get("bars")
        if isinstance(b, list) and len(b) == 2:
            out.append((int(b[0]), int(b[1]), s))
    return out


def check_plan(plan):
    """返回 [(检查项, 是否通过, 说明, 是否计入通过率)]。

    ⚠ 门（gate）只留"结构件在不在、自不自洽"。凡是描述"统计位置/风格选择"的，
    一律降为提示（advisory）——反向验收时 Wait Day 在下面这些项上会翻车，
    每一条都是被它纠正过的：
      · 段落长度非 4 倍数（它是 6×4）
      · 终止音逐句交替（它 4 小节级全落 C5，问答发生在 2 小节级）
      · 高潮位置 35%~90%（它的 A5 在 29%）
      · ≥2 声部 / ≥2 种织体（纯旋律草图天然只有 1 个）
      · 每句都要有呼吸点（它 6 句里只有 4 句有）
    """
    R = []
    key = plan.get("key") or {}
    root_pc = PC.index(key["root"]) if key.get("root") in PC else 0
    mode = key.get("mode") or "major"
    tonic = root_pc

    # ── 1 曲式层 ─────────────────────────────────────────
    secs = _section_bars(plan)
    ok = len(secs) >= 2 and all(s.get("label") and s.get("function") for _, _, s in secs)
    R.append(("曲式：≥2 段且每段有 label 与 function", ok,
              "共 %d 段 %s" % (len(secs), [s.get("label") for _, _, s in secs]), True))
    odd = [s.get("label") for a, b, s in secs if (b - a + 1) % 4 != 0]
    R.append(("曲式：至少一段长度不是 4 的倍数", True,
              "非 4 倍数段：%s" % (odd or "无——全曲都是 4/8 的倍增，听感容易方"
                                 "（Wait Day 即全 4 倍数，属合法写法）"), False))

    # ── 2 调性层 ─────────────────────────────────────────
    harm = plan.get("harmony")
    bars_total = max((b for _, b, _ in secs), default=0)
    no_chord_src = bool(plan.get("_harmony_unavailable"))
    if not harm and no_chord_src:
        R.append(("和声：逐小节声明了进行", True,
                  "源文件未提供和弦数据（反推不出），本项未评估", False))
    elif not harm:
        R.append(("和声：逐小节声明了进行", False,
                  "计划未声明 harmony（和声是结构的骨架，不能省）", True))
    else:
        have = {int(h.get("bar", 0)) for h in harm}
        missing = [b for b in range(1, bars_total + 1) if b not in have]
        R.append(("和声：逐小节声明了进行", not missing,
                  "缺 %s" % missing if missing else "覆盖 1-%d 小节" % bars_total, True))
    cads = plan.get("cadences") or []
    cad_bars = {int(c.get("bar", 0)) for c in cads}
    miss_cad = [s.get("label") for _, b, s in secs if b not in cad_bars]
    if no_chord_src:
        R.append(("和声：每段末尾标注了终止式", True, "源文件无和弦数据，本项未评估", False))
    else:
        R.append(("和声：每段末尾标注了终止式", bool(cads) and not miss_cad,
                  "缺终止式的段：%s" % miss_cad if miss_cad else
                  "共 %d 处 %s" % (len(cads), [c.get("type") for c in cads]), True))

    # ── 3 音区层（纯旋律草图只有 1 个声部，属合法）────────
    vs = plan.get("voices") or []
    banded = [(v.get("name"), v.get("band")) for v in vs
              if isinstance(v.get("band"), list) and len(v["band"]) == 2]
    derived_plan = bool(plan.get("_derived_from"))
    if len(banded) < 2:
        R.append(("音区：多声部时间隔 ≥7 半音", True,
                  "只声明了 %d 个声部——旋律草图可以，成品应有伴奏；"
                  "一旦有 ≥2 个声部就必须声明音区带" % len(banded), False))
    elif derived_plan:
        banded.sort(key=lambda x: x[1][0])
        gaps = [(n2, b2[0] - b1[1]) for (_, b1), (n2, b2) in zip(banded, banded[1:])]
        R.append(("音区：多声部时间隔 ≥7 半音", True,
                  "反推的音区带是实测 min/max（含一次性填充音），不是声明的「工作带」，"
                  "故只报不判：%s" % "、".join("%s %+d" % (n, g) for n, g in gaps), False))
    else:
        banded.sort(key=lambda x: x[1][0])
        gaps = [(n2, b2[0] - b1[1]) for (_, b1), (n2, b2) in zip(banded, banded[1:])]
        worst = min(g for _, g in gaps)
        R.append(("音区：多声部时间隔 ≥7 半音", worst >= 7,
                  "最小间隔 %d 半音（%s）" % (worst, "、".join("%s %+d" % (n, g) for n, g in gaps)), True))

    # ── 4 织体层（同上，单声部时不适用）──────────────────
    tex = plan.get("texture") or []
    figs = {t.get("figure") for t in tex if t.get("figure")}
    dens = [t.get("density") for t in tex if isinstance(t.get("density"), (int, float))]
    derived = bool(plan.get("_derived_from"))
    if not tex:
        R.append(("织体：≥2 种织体且密度随段落变化", True,
                  "计划未声明 texture（反推无法得到织体名称，需人工填）", False))
    elif derived:
        R.append(("织体：≥2 种织体且密度随段落变化", True,
                  "反推计划的织体层不作判定；密度曲线 %s" % dens, False))
    elif len(banded) < 2:
        R.append(("织体：≥2 种织体且密度随段落变化", True,
                  "单声部不适用；密度曲线 %s" % dens, False))
    else:
        R.append(("织体：≥2 种织体且密度随段落变化", len(figs) >= 2 and len(set(dens)) >= 2,
                  "织体 %s；密度 %s" % (sorted(figs), dens), True))

    # ── 5 乐句层 ─────────────────────────────────────────
    ph = plan.get("phrases") or []
    bad3 = [p.get("bars") for p in ph
            if not (p.get("start") and p.get("goal") and p.get("cadence"))]
    R.append(("乐句：每句都有起音 / 目标音 / 终止音", bool(ph) and not bad3,
              "共 %d 句；缺列的 %s" % (len(ph), bad3 or "无"), True))
    nbreath = sum(1 for p in ph if p.get("breath"))
    # 降为提示：POP909 300 首实测 37.7% 的真作品做不到"1/3 乐句有句内换气"，
    # 16.3% 一首都没有——句内换气是风格选择（唱得连 vs 说得分明），不是结构必需
    R.append(("乐句：≥1/3 的乐句声明了呼吸点", bool(ph) and nbreath * 3 >= len(ph),
              "%d/%d 句有呼吸点；真人语料中位 82%%、但有 16%% 的真作品一首里一次句内换气都没有，"
              "故只报不判" % (nbreath, len(ph)), False))
    ends = [pnum(p["cadence"]) for p in ph if p.get("cadence")]
    ends = [x for x in ends if x is not None]
    last_tonic = bool(ends) and ends[-1] % 12 == tonic
    R.append(("乐句：末句终止音落主音", last_tonic,
              "末句 %s%s；POP909 300 首实测只有 29%%落主音（关系调主音也算 57%%），"
              "其余在中音/下属音/下中音收束——**这是风格选择，不作判定**"
              % (pname(ends[-1]) if ends else "—",
                 "（主音）" if last_tonic else "（不是主音）"), False))
    R.append(("乐句：终止音逐句交替（问答感）", len({x % 12 for x in ends}) >= 2,
              "%d 种终止音——若全落同一个音，听感容易平；"
              "但问答也可以发生在更小的层级（Wait Day 的 4 小节级全落 C5，"
              "问答在 2 小节级）" % len({x % 12 for x in ends}), False))

    # ── 6 骨架层 / 高潮 ──────────────────────────────────
    cl = plan.get("climax") or {}
    note = pnum(cl.get("note"))
    bar = cl.get("bar")
    if note is None or not isinstance(bar, int) or bars_total <= 0:
        R.append(("骨架：声明了全曲最高音及其小节", False, "未声明 climax", True))
    else:
        pos = bar / float(bars_total)
        R.append(("骨架：声明了全曲最高音及其小节", True,
                  "%s 在第 %d 小节（%.0f%%）" % (cl["note"], bar, pos * 100), True))
        R.append(("骨架：最高音落在 35%~90%（常见拱形）", 0.35 <= pos <= 0.90,
                  "实际 %.0f%%——早现的单一高点也是合法写法（Wait Day 在 29%%），"
                  "只在你想做拱形时才需要调整" % (pos * 100), False))

    # ── 7 能量层 ─────────────────────────────────────────
    en = plan.get("energy") or []
    lv = [e.get("level") for e in en if isinstance(e.get("level"), (int, float))]
    R.append(("能量：曲线不是常数（至少一处起伏）", len(set(lv)) >= 2,
              "逐段能量 %s" % lv, True))

    # ── 8 动机层 ─────────────────────────────────────────
    mo = plan.get("motif") or {}
    degs = mo.get("degrees")
    apps = mo.get("appearances") or []
    ops = {a.get("op") for a in apps}
    ok = bool(degs) and len(apps) >= 2 and len(ops - {"state"}) >= 1
    R.append(("动机：已定义且 ≥2 次出现、含 ≥1 次非原样陈述", ok,
              "动机级数 %s；出现 %d 次，手法 %s" % (degs, len(apps), sorted(ops)), True))

    # ── 9 自洽性 ─────────────────────────────────────────
    sec_ranges = [(a, b) for a, b, _ in secs]
    orphan = [p.get("bars") for p in ph
              if not any(a <= int(p["bars"][0]) and int(p["bars"][1]) <= b
                         for a, b in sec_ranges if isinstance(p.get("bars"), list)
                         and len(p["bars"]) == 2)]
    R.append(("自洽：乐句都落在某段之内", not orphan,
              "越界的乐句 %s" % orphan if orphan else "全部命中", True))
    return R


# ══════════════════════════════════════════════════════════════
# 实现层检查（计划 vs 音符）
# ══════════════════════════════════════════════════════════════
def load_song_notes(path):
    """读 song.json 或 .mid，返回 (原始对象, {轨名: 音符列表})。"""
    if path.lower().endswith(".mid"):
        with open(path, "rb") as fh:
            data = fh.read()
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aria_midi
        parsed = aria_midi.parse_midi(data)
        song = {"name": os.path.splitext(os.path.basename(path))[0],
                "bpm": parsed.get("bpm"), "tracks": parsed["tracks"]}
    else:
        with open(path, encoding="utf-8") as fh:
            song = json.load(fh)
    out = {}
    for t in song.get("tracks", []):
        out[t.get("name") or "?%d" % len(out)] = sorted(
            t.get("notes") or [], key=lambda n: (n["start_beat"], n["pitch"]))
    return song, out


MELODY_SPAN_LIMIT = 24      # 跨度超过两个八度就认为这轨混了声部，需要先提旋律层


def melody_layer(notes):
    """单轨多声部时取旋律层：按起音取最高音（skyline），再丢掉远低于最高音的伴奏音。

    返回 (旋律音符, 是否做了提取)。零依赖；不追求完美，只求不再把低音当成旋律起点。
    """
    if not notes:
        return notes, False
    span = max(n["pitch"] for n in notes) - min(n["pitch"] for n in notes)
    if span <= MELODY_SPAN_LIMIT:
        return notes, False
    top = max(n["pitch"] for n in notes)
    floor_pitch = top - 19                      # 留一个八度半的余量给旋律自身的起伏
    out = []
    seen = set()
    for n in sorted(notes, key=lambda z: (z["start_beat"], -z["pitch"])):
        key = round(n["start_beat"] * 4)
        if key in seen:                         # 同一起音只保留最高的一个
            continue
        if n["pitch"] < floor_pitch:
            continue
        seen.add(key)
        out.append(n)
    return sorted(out, key=lambda n: (n["start_beat"], n["pitch"])), True


def check_realize(plan, song, notes_by_track, window=4.0):
    R = []
    key = plan.get("key") or {}
    root_pc = PC.index(key["root"]) if key.get("root") in PC else 0
    mode = key.get("mode") or "major"
    mel_name = None
    if notes_by_track:
        mel_name = max(notes_by_track,
                       key=lambda k: (sum(n["pitch"] for n in notes_by_track[k]) /
                                      max(1, len(notes_by_track[k]))))
    mel = notes_by_track.get(mel_name) or []
    if not mel:
        return [("实现：存在旋律轨", False, "没找到任何音符", True)]

    def in_bars(a, b, extend=0.0):
        # extend：向后多取一个窗口——句末的空当是"下一句第一个音之前"，
        # 不多取就看不出这个间隙
        return [n for n in mel if a - 1 <= n["start_beat"] / window < b + extend]

    # 骨架 / 目标音 / 呼吸
    miss_s, miss_g, miss_b = [], [], []
    for p in plan.get("phrases") or []:
        bars = p.get("bars")
        if not (isinstance(bars, list) and len(bars) == 2):
            continue
        a, b = int(bars[0]), int(bars[1])
        seg = in_bars(a, b)
        if not seg:
            miss_s.append(bars); continue
        ps = {n["pitch"] for n in seg}
        for lab, val, bucket in (("start", p.get("start"), miss_s),
                                 ("goal", p.get("goal"), miss_g)):
            pv = pnum(val)
            if pv is None or pv not in ps:
                bucket.append("%s-%s" % (bars, val))
        bt = p.get("breath")
        if isinstance(bt, str) and ":" in bt:
            try:
                bb, beat = bt.split(":")
                t = (int(bb) - 1) * window + float(beat)
            except ValueError:
                t = None
            if t is not None:
                # 呼吸点记的是"空隙之后那个音的起点"（--derive 的约定），
                # 也容忍记在空隙中间：只要该处前后确实有 ≥0.24 拍的空当
                # 用整条旋律找空当：呼吸点可能落在句末（下一句首音之前）或句首之前
                seg2 = sorted(mel, key=lambda n: n["start_beat"])
                hit = False
                for x, y in zip(seg2, seg2[1:]):
                    g = y["start_beat"] - (x["start_beat"] + x["duration"])
                    if x["start_beat"] + x["duration"] - 0.26 <= t <= y["start_beat"] + 0.26 and g >= 0.24:
                        hit = True
                        break
                if not hit:
                    miss_b.append(bt)
    R.append(("实现：每句的起音与终止音都真的出现", not miss_s,
              "缺失 %s" % miss_s if miss_s else "%d 句全部命中" % len(plan.get("phrases") or []), True))
    R.append(("实现：每句的目标音都真的出现", not miss_g,
              "缺失 %s" % miss_g if miss_g else "全部命中", True))
    R.append(("实现：每句声明的呼吸点真的是空隙", not miss_b,
              "不到位 %s" % miss_b if miss_b else "全部到位", True))

    # 高潮
    cl = plan.get("climax") or {}
    top = max(mel, key=lambda n: n["pitch"])
    want = pnum(cl.get("note"))
    R.append(("实现：全曲最高音等于计划声明的最高音", want is not None and abs(top["pitch"] - want) <= 1,
              "实际最高 %s（第 %d 小节），计划 %s" %
              (pname(top["pitch"]), int(top["start_beat"] / window) + 1, cl.get("note")), True))

    # 音区带：band 是「工作音区」，允许 ≤5% 的一次性填充音越界（越界幅度 ≤6 半音）
    bad_band, band_note = [], []
    for v in plan.get("voices") or []:
        band = v.get("band")
        if not (isinstance(band, list) and len(band) == 2):
            continue
        ns = notes_by_track.get(v.get("name"))
        if not ns:
            continue
        out = [n["pitch"] for n in ns
               if n["pitch"] < band[0] - 6 or n["pitch"] > band[1] + 6]
        out += [n["pitch"] for n in ns
                if (band[0] - 6 <= n["pitch"] < band[0]) or (band[1] < n["pitch"] <= band[1] + 6)]
        share = len(out) / float(len(ns))
        if share > 0.05:
            bad_band.append("%s 有 %d/%d 音越出 %s（%.0f%%）"
                            % (v.get("name"), len(out), len(ns), band, share * 100))
        elif out:
            band_note.append("%s 有 %d 个填充音越界（%.0f%%，在工作音区约定内）"
                             % (v.get("name"), len(out), share * 100))
    R.append(("实现：各声部音符落在声明的音区带内（容许 ≤5% 填充音）", not bad_band,
              "；".join(bad_band) if bad_band else ("全部在带内" if not band_note
                                                 else "；".join(band_note)), True))

    # 动机
    mo = plan.get("motif") or {}
    degs = mo.get("degrees")
    apps = mo.get("appearances") or []
    if degs and len(degs) >= 2 and apps:
        first = apps[0]
        bar = first.get("bar")
        seg = in_bars(int(bar), int(bar)) if bar else []
        seg = sorted(seg, key=lambda n: n["start_beat"])[:len(degs)]
        got = [degree_of(n["pitch"], root_pc, mode) for n in seg]
        want = [d % 7 for d in degs]
        hit = got[:len(want)] == [w if w else 7 for w in want]
        R.append(("实现：动机首次陈述按计划的级数出现", hit,
                  "计划级数 %s，实际 %s（第 %s 小节）" % (degs, got, bar), True))
    else:
        R.append(("实现：动机首次陈述按计划的级数出现", False, "计划未定义动机", True))
    return R


# ══════════════════════════════════════════════════════════════
# 反推草稿计划
# ══════════════════════════════════════════════════════════════
def derive(song_path, chords_path=None, window=4.0, phrase_bars=4):
    song, tracks = load_song_notes(song_path)
    named = [k for k in tracks if "MELODY" in k.upper() or "LEAD" in k.upper()]
    mel_name = named[0] if named else max(
        tracks, key=lambda k: (sum(n["pitch"] for n in tracks[k]) / max(1, len(tracks[k]))))
    mel, extracted = melody_layer(tracks[mel_name])
    total = max((n["start_beat"] + n["duration"] for n in mel), default=window)
    bars = max(1, int(total / window + 0.999))
    # 调：用最小二乘挑最贴的大调/小调
    pcs = Counter(n["pitch"] % 12 for n in mel)
    best, bests = None, -1
    for r in range(12):
        for mo in ("major", "minor"):
            sc = scale_of(r, mo)
            s = sum(v for k, v in pcs.items() if k in sc)
            if s > bests:
                best, bests = (r, mo), s
    root_pc, mode = best
    degmap = DEG_MAJOR if mode == "major" else DEG_MINOR

    def blocks():
        raw = [(i, min(i + phrase_bars - 1, bars)) for i in range(1, bars + 1, phrase_bars)]
        # 丢掉"没有任何起音"的块：最后一个音可能拖进下一小节，不该因此造出一个空段
        keep = [(a, b) for a, b in raw
                if any((a - 1) * window <= n["start_beat"] < b * window for n in mel)]
        return keep or raw[:1]

    form, phrases, energy, texture = [], [], [], []
    for i, (a, b) in enumerate(blocks(), 1):
        seg = [n for n in mel if (a - 1) * window <= n["start_beat"] < b * window]
        if not seg:
            continue
        form.append({"label": "A%d" % i, "bars": [a, b],
                     "function": "establish" if i == 1 else "develop"})
        srt = sorted(seg, key=lambda n: n["start_beat"])
        peak = max(seg, key=lambda n: n["pitch"])
        last = max(seg, key=lambda n: n["start_beat"] + n["duration"])
        # 最大空隙当呼吸点
        gap, gt = 0.0, None
        for x, y in zip(srt, srt[1:]):
            g = y["start_beat"] - (x["start_beat"] + x["duration"])
            if g > gap:
                gap, gt = g, y["start_beat"]
        if gap < 0.24:            # 太小的缝是断音不是换气
            gt = None
        phrases.append({
            "bars": [a, b], "start": pname(srt[0]["pitch"]),
            "goal": pname(peak["pitch"]),
            "breath": ("%d:%.2f" % (int(gt / window) + 1, gt % window)) if gt is not None else None,
            "cadence": pname(last["pitch"]),
        })
    dens_all = [len([n for n in mel if (a - 1) * window <= n["start_beat"] < b * window])
                for a, b in blocks()]
    dmax = max(dens_all) if dens_all else 1
    for (a, b), dv in zip(blocks(), dens_all):
        # 用密度而非力度：POP909 的力度常被导出拉平，用它量到的是导出方式
        energy.append({"bars": [a, b], "level": round(dv / float(dmax or 1), 2)})
        # 织体名反推不出来（留空 figure），只记密度——**必须用本块的 dv，不能用残留的 seg**
        texture.append({"bars": [a, b], "density": dv})

    # 和声：有 chords.json 就用，否则留空（检查器会报"未声明和声"）
    harmony = []
    chord_ok = bool(chords_path and os.path.exists(chords_path))
    if chord_ok:
        with open(chords_path, encoding="utf-8") as fh:
            chs = json.load(fh).get("chords") or []
        bybar = defaultdict(list)
        for c in chs:
            bybar[int(c["start_beat"] // window) + 1].append(
                [PC[c["root"] % 12], c.get("type", "maj"), c.get("duration", window)])
        harmony = [{"bar": b, "chords": bybar[b]} for b in sorted(bybar)]

    # 声部音区带
    voices = []
    for name, ns in tracks.items():
        if ns:
            voices.append({"name": name, "band": [min(n["pitch"] for n in ns),
                                                  max(n["pitch"] for n in ns)],
                           "role": "line" if name == mel_name else "support"})

    # 动机：最常见的开头两音程型 → 级数
    shapes = Counter()
    for a, b in blocks():
        seg = sorted([n for n in mel if (a - 1) * window <= n["start_beat"] < b * window],
                     key=lambda n: n["start_beat"])[:3]
        if len(seg) == 3:
            shapes[tuple(n["pitch"] for n in seg)] += 1
    motif = None
    if shapes:
        base = shapes.most_common(1)[0][0]
        degs = [degmap.get((p - root_pc) % 12) for p in base]
        apps = []
        for a, b in blocks():
            seg = sorted([n for n in mel if (a - 1) * window <= n["start_beat"] < b * window],
                         key=lambda n: n["start_beat"])[:3]
            if len(seg) == 3 and tuple(n["pitch"] for n in seg) == base:
                apps.append({"bar": a, "op": "state" if not apps else "state"})
        if len(apps) > 1:
            apps[-1]["op"] = "transpose"
        motif = {"degrees": degs, "appearances": apps}

    top = max(mel, key=lambda n: n["pitch"])
    plan = {
        "name": song.get("name") or os.path.basename(os.path.dirname(song_path)),
        "bpm": song.get("bpm"), "meter": "4/4",
        "key": {"root": PC[root_pc], "mode": mode},
        "window_beats": window,
        "_derived_from": os.path.basename(song_path),
        "_note": "由 plan_check --derive 反推的草稿：结构件齐全但目标是照现状抄的，"
                 "正式作曲应当先写计划再写音符，而不是反过来。"
                 + ("⚠ 源文件是单轨多声部，旋律层用 skyline 近似提取，起点/终点可能仍需手改。"
                    if extracted else ""),
        "form": form, "harmony": harmony, "cadences": [], "voices": voices,
        "_harmony_unavailable": not chord_ok,
        "texture": texture, "phrases": phrases, "motif": motif,
        "energy": energy,
        "climax": {"bar": int(top["start_beat"] // window) + 1, "note": pname(top["pitch"])},
    }
    # 终止式：段尾和弦若含主/属功能就标上
    if harmony:
        hb = {h["bar"]: h["chords"] for h in harmony}
        for _, b, _s in [(s["bars"][0], s["bars"][1], s) for s in form]:
            ch = hb.get(b)
            if ch:
                lastpc = PC.index(ch[-1][0]) if ch[-1][0] in PC else root_pc
                if lastpc == root_pc:
                    plan["cadences"].append({"bar": b, "type": "authentic"})
                elif lastpc == (root_pc + 7) % 12:
                    plan["cadences"].append({"bar": b, "type": "half"})
                else:
                    plan["cadences"].append({"bar": b, "type": "other"})
    return plan


# ══════════════════════════════════════════════════════════════
def report(rows, title):
    print("─" * 76)
    print(title)
    gates = [(n, ok, why) for n, ok, why, g in rows if g]
    adv = [(n, ok, why) for n, ok, why, g in rows if not g]
    for n, ok, why in gates + adv:
        tag = "通过" if ok else "不通过"
        print("  [%s] %-46s %s" % (tag, n, why))
    npass = sum(1 for _, ok, _ in gates if ok)
    print("  → 计分项 %d/%d 通过" % (npass, len(gates)))
    return npass, len(gates)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="计划层检查器（零依赖）")
    ap.add_argument("--plan", help="plan.json")
    ap.add_argument("--song", help="song.json（给出则追加「计划 vs 音符」一致性检查）")
    ap.add_argument("--derive", metavar="SONG", help="从 song.json 反推草稿计划")
    ap.add_argument("--chords", help="配合 --derive：chords.json")
    ap.add_argument("--out", help="配合 --derive：写入文件（默认 stdout）")
    ap.add_argument("--window-beats", type=float, default=4.0)
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    if a.derive:
        plan = derive(a.derive, a.chords, a.window_beats)
        txt = json.dumps(plan, ensure_ascii=False, indent=1)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                fh.write(txt + "\n")
            print("已写入 %s" % a.out, file=sys.stderr)
        else:
            sys.stdout.write(txt + "\n")
        return 0

    if not a.plan:
        ap.error("需要 --plan 或 --derive")
    with open(a.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    w = float(plan.get("window_beats") or a.window_beats)

    rows = check_plan(plan)
    realized = None
    if a.song:
        song, tracks = load_song_notes(a.song)
        realized = check_realize(plan, song, tracks, w)

    if a.json:
        print(json.dumps({
            "plan": plan.get("name"), "window_beats": w,
            "plan_checks": [{"check": n, "pass": ok, "detail": why, "gate": g}
                            for n, ok, why, g in rows],
            "realize_checks": ([{"check": n, "pass": ok, "detail": why, "gate": g}
                                for n, ok, why, g in realized] if realized else None),
        }, ensure_ascii=False, indent=1))
        return 0

    print("《%s》  %s %s  %s  %s  %d 小节" %
          (plan.get("name"), plan.get("bpm"), plan.get("meter"),
           (plan.get("key") or {}).get("root"), (plan.get("key") or {}).get("mode"),
           max((int(s.get("bars", [0, 0])[1]) for s in plan.get("form") or []), default=0)))
    p1, t1 = report(rows, "一、计划层：结构件在不在、自不自洽")
    if realized:
        report(realized, "二、实现层：音符有没有把计划做出来")
    return 0


if __name__ == "__main__":
    sys.exit(main())
