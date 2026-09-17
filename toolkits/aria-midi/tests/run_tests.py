#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aria_midi.py 冒烟测试（stdlib unittest + subprocess，无第三方依赖）。

运行：python tests/run_tests.py（从 aria-midi 目录）
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # aria-midi 目录
CLI = ROOT / "aria_midi.py"
FIXTURE = Path(__file__).resolve().parent / "sample-song.json"


def run_cli(*argv, stdin=None):
    return subprocess.run(
        [sys.executable, str(CLI), *argv],
        input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace")


class TestScale(unittest.TestCase):
    def test_list_c_major(self):
        r = run_cli("scale", "--root", "C4", "--type", "major", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        midis = [n["midi"] for n in json.loads(r.stdout)["notes"]]
        self.assertEqual(midis, [60, 62, 64, 65, 67, 69, 71])  # C D E F G A B

    def test_snap_sharp_prefers_upper_neighbor(self):
        r = run_cli("scale", "--root", "C4", "--type", "major", "--snap", "66")
        self.assertEqual(r.returncode, 0, r.stderr)
        snapped = json.loads(r.stdout)["snapped"][0]
        self.assertEqual(snapped["midi"], 67)  # F# → G

    def test_chord_tones_maj7(self):
        r = run_cli("scale", "--root", "C4", "--chord", "maj7")
        midis = [t["midi"] for t in json.loads(r.stdout)["tones"]]
        self.assertEqual(midis, [60, 64, 67, 71])  # C E G B

    def test_suggest_finds_c_major(self):
        r = run_cli("scale", "--suggest", "60,62,64,65,67,69,71")
        top = json.loads(r.stdout)["suggestions"][0]
        self.assertEqual(top["root"], "C")
        self.assertEqual(top["scale"], "major")
        self.assertEqual(top["coverage"], 100.0)


class TestValidate(unittest.TestCase):
    def _validate(self, song):
        return run_cli("validate", "--input", "-", stdin=json.dumps(song))

    def test_sample_passes(self):
        r = run_cli("validate", "--input", str(FIXTURE), "--strict")
        self.assertEqual(r.returncode, 0, r.stdout)
        data = json.loads(r.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["stats"]["note_count"], 20)
        self.assertEqual(data["stats"]["track_count"], 2)

    def test_pitch_out_of_range(self):
        r = self._validate({"notes": [{"pitch": 128, "start_beat": 0, "duration": 1}]})
        self.assertEqual(r.returncode, 1)
        self.assertIn("音高越界", r.stdout)

    def test_velocity_zero_and_high(self):
        r = self._validate({"notes": [{"pitch": 60, "start_beat": 0, "duration": 1, "velocity": 0}]})
        self.assertEqual(r.returncode, 1)
        self.assertIn("力度越界", r.stdout)
        r = self._validate({"notes": [{"pitch": 60, "start_beat": 0, "duration": 1, "velocity": 128}]})
        self.assertEqual(r.returncode, 1)

    def test_off_grid_warning_vs_strict(self):
        song = {"notes": [{"pitch": 60, "start_beat": 0.3, "duration": 1}]}
        r = self._validate(song)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(json.loads(r.stdout)["warnings"])
        r = run_cli("validate", "--input", "-", "--strict", stdin=json.dumps(song))
        self.assertEqual(r.returncode, 1)
        self.assertIn("0.25 拍网格", r.stdout)

    def test_same_pitch_overlap(self):
        song = {"notes": [
            {"pitch": 60, "start_beat": 0, "duration": 1},
            {"pitch": 60, "start_beat": 0.5, "duration": 1},
        ]}
        r = self._validate(song)
        self.assertEqual(r.returncode, 1)
        self.assertIn("同音高重叠", r.stdout)

    def test_adjacent_same_pitch_is_ok(self):
        song = {"notes": [
            {"pitch": 60, "start_beat": 0, "duration": 1},
            {"pitch": 60, "start_beat": 1, "duration": 1},
        ]}
        r = self._validate(song)
        self.assertEqual(r.returncode, 0, r.stdout)


class TestGenerateInspect(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            mid = Path(td) / "song.mid"
            r = run_cli("generate", "--input", str(FIXTURE), "--output", str(mid))
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertTrue(mid.exists() and mid.stat().st_size > 0)

            r = run_cli("inspect", "--input", str(mid))
            self.assertEqual(r.returncode, 0, r.stdout)
            data = json.loads(r.stdout)
            self.assertEqual(data["format"], 1)
            self.assertEqual(data["bpm"], 120.0)
            self.assertEqual(len(data["tracks"]), 2)
            self.assertEqual(data["tracks"][0]["name"], "旋律")
            self.assertEqual(data["tracks"][0]["program"], 0)
            self.assertEqual(data["tracks"][1]["name"], "低音")
            self.assertEqual(data["tracks"][1]["program"], 32)
            self.assertEqual(len(data["tracks"][0]["notes"]), 12)
            self.assertEqual(len(data["tracks"][1]["notes"]), 8)

            n0 = data["tracks"][0]["notes"][0]
            self.assertEqual(n0["pitch"], 67)
            self.assertEqual(n0["start_beat"], 0.0)
            self.assertEqual(n0["duration"], 0.5)
            self.assertEqual(n0["velocity"], 95)

            n_last = data["tracks"][0]["notes"][-1]
            self.assertEqual(n_last["pitch"], 64)
            self.assertEqual(n_last["start_beat"], 7.75)
            self.assertEqual(n_last["duration"], 0.5)

    def test_legacy_notes_input(self):
        with tempfile.TemporaryDirectory() as td:
            song = {"notes": [{"pitch": 60, "start_beat": 0, "duration": 1, "velocity": 90}]}
            mid = Path(td) / "legacy.mid"
            r = run_cli("generate", "--input", "-", "--output", str(mid),
                        stdin=json.dumps(song))
            self.assertEqual(r.returncode, 0, r.stdout)
            data = json.loads(run_cli("inspect", "--input", str(mid)).stdout)
            self.assertEqual(len(data["tracks"][0]["notes"]), 1)
            self.assertEqual(data["tracks"][0]["notes"][0]["pitch"], 60)

    def test_inspect_rejects_non_midi(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.mid"
            bad.write_bytes(b"this is not a midi file at all")
            r = run_cli("inspect", "--input", str(bad))
            self.assertEqual(r.returncode, 1)
            self.assertIn("MThd", r.stdout)


class TestAnalyze(unittest.TestCase):
    def test_sample_scores_well(self):
        r = run_cli("analyze", "--input", str(FIXTURE))
        self.assertEqual(r.returncode, 0, r.stdout)
        data = json.loads(r.stdout)
        self.assertGreaterEqual(data["score"], 6)
        self.assertEqual(data["details"]["total_notes"], 20)

    def test_flat_velocity_dense_notes_score_low(self):
        """力度全相同 + 连续无休止 → 低分且建议命中「力度变化/呼吸空间」。"""
        notes = [{"pitch": 60 + i, "start_beat": i, "duration": 1, "velocity": 100}
                 for i in range(16)]  # 每个音符恰好首尾相接，无休止
        r = run_cli("analyze", "--input", "-", stdin=json.dumps({"bpm": 120, "notes": notes}))
        self.assertEqual(r.returncode, 0, r.stdout)
        data = json.loads(r.stdout)
        self.assertLess(data["score"], 6)
        joined = " ".join(data["suggestions"])
        self.assertIn("力度变化", joined)
        self.assertIn("呼吸", joined)

    def test_analyze_with_chords(self):
        chords = {"chords": [
            {"root": 60, "type": "maj", "start_beat": 0, "duration": 32},
        ]}
        with tempfile.TemporaryDirectory() as td:
            cj = Path(td) / "chords.json"
            cj.write_text(json.dumps(chords), encoding="utf-8")
            r = run_cli("analyze", "--input", str(FIXTURE), "--chords", str(cj))
            self.assertEqual(r.returncode, 0, r.stdout)
            data = json.loads(r.stdout)
            self.assertNotEqual(data["details"]["chord_tone_rate"], "无和弦定义")

    def test_leapy_melody_scores_low(self):
        """跳进为主（级进占比 <40%）→ 断裂惩罚，分数应显著低于级进为主的旋律。"""
        leaps = [{"pitch": 60 + (i % 2) * 5, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(16)]
        steps = [{"pitch": 60 + i, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(16)]
        r_leap = run_cli("analyze", "--input", "-", stdin=json.dumps({"bpm": 120, "notes": leaps}))
        r_step = run_cli("analyze", "--input", "-", stdin=json.dumps({"bpm": 120, "notes": steps}))
        self.assertEqual(r_leap.returncode, 0, r_leap.stdout)
        data_leap = json.loads(r_leap.stdout)
        data_step = json.loads(r_step.stdout)
        self.assertLess(data_leap["score"], data_step["score"])
        self.assertLess(float(data_leap["details"]["step_ratio"].rstrip("%")), 40)

    def test_style_arpeggio_exempts_leaps(self):
        """--style arpeggio 豁免跳进约束，分数应回升。"""
        leaps = [{"pitch": 60 + (i % 2) * 5, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(16)]
        base = run_cli("analyze", "--input", "-", stdin=json.dumps({"bpm": 120, "notes": leaps}))
        exempt = run_cli("analyze", "--input", "-", "--style", "arpeggio",
                         stdin=json.dumps({"bpm": 120, "notes": leaps}))
        self.assertGreater(json.loads(exempt.stdout)["score"], json.loads(base.stdout)["score"])

    def test_track_selection_and_all_tracks(self):
        """--track 指定轨 / --all-tracks 合并 / 默认选平均音高最高的旋律轨。"""
        song = {"tracks": [
            {"name": "旋律", "notes": [{"pitch": 72, "start_beat": 0, "duration": 1, "velocity": 90},
                                       {"pitch": 74, "start_beat": 1, "duration": 1, "velocity": 90}]},
            {"name": "低音", "notes": [{"pitch": 36, "start_beat": 0, "duration": 1, "velocity": 90},
                                       {"pitch": 43, "start_beat": 1, "duration": 1, "velocity": 90}]},
        ]}
        dft = json.loads(run_cli("analyze", "--input", "-", stdin=json.dumps(song)).stdout)
        self.assertEqual(dft["details"]["analyzed_track"], "旋律")
        bass = json.loads(run_cli("analyze", "--input", "-", "--track", "低音",
                                  stdin=json.dumps(song)).stdout)
        self.assertEqual(bass["details"]["analyzed_track"], "低音")
        all_t = json.loads(run_cli("analyze", "--input", "-", "--all-tracks",
                                   stdin=json.dumps(song)).stdout)
        self.assertEqual(all_t["details"]["analyzed_track"], "全部音轨")
        self.assertEqual(all_t["details"]["total_notes"], 4)

    def test_sub_scores_split_technical_and_musicality(self):
        """技术分/音乐性分拆栏：跳进旋律技术分与音乐性分都低，passed 应为 false。"""
        leaps = [{"pitch": 60 + (i % 2) * 5, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(16)]
        d = json.loads(run_cli("analyze", "--input", "-", stdin=json.dumps({"bpm": 120, "notes": leaps})).stdout)
        self.assertIn("technical_score", d)
        self.assertIn("musicality_score", d)
        self.assertIn("passed", d)
        self.assertLess(d["musicality_score"], 6.0)
        self.assertFalse(d["passed"])

    def test_structure_block_present(self):
        """analyze 输出应含 structure_score 与 details.structure（乐句结构分析）。"""
        r = run_cli("analyze", "--input", str(FIXTURE))
        self.assertEqual(r.returncode, 0, r.stdout)
        d = json.loads(r.stdout)
        self.assertIn("structure_score", d)
        self.assertIn("structure", d["details"])
        self.assertIn("phrase_count", d["details"]["structure"])

    def test_structured_melody_scores_higher_structure(self):
        """起承转合式四句（同头异尾+休止分句+落主音）结构分应高于一气呵成的流水旋律。"""
        # 4 个乐句：共享开头轮廓 (+,+,-)，句间 1 拍休止，末句落主音 C4
        phrases = [
            [(60, 0.0), (62, 0.5), (64, 1.0), (62, 1.5)],
            [(60, 3.0), (62, 3.5), (64, 4.0), (67, 4.5)],   # 承：同头，尾落属音 G
            [(65, 7.0), (67, 7.5), (69, 8.0), (65, 8.5)],   # 转：换头
            [(60, 11.0), (62, 11.5), (64, 12.0), (60, 12.5)],  # 合：同头，尾落主音 C
        ]
        notes = [{"pitch": p, "start_beat": b, "duration": 0.5, "velocity": 85 + (i % 4) * 5}
                 for i, ph in enumerate(phrases) for p, b in ph]
        flow = [{"pitch": 60 + (i % 7), "start_beat": i * 0.5, "duration": 0.5, "velocity": 85 + (i % 4) * 5}
                for i in range(16)]
        d1 = json.loads(run_cli("analyze", "--input", "-", "--key-root", "C4",
                                stdin=json.dumps({"bpm": 120, "notes": notes})).stdout)
        d2 = json.loads(run_cli("analyze", "--input", "-", "--key-root", "C4",
                                stdin=json.dumps({"bpm": 120, "notes": flow})).stdout)
        self.assertEqual(d1["details"]["structure"]["phrase_count"], 4)
        self.assertGreaterEqual(d1["details"]["structure"]["contour_reuse_pairs"], 2)
        self.assertGreater(d1["structure_score"], d2["structure_score"])

    def test_structure_suggestion_for_single_phrase(self):
        """全程无休止/长音的流水旋律应收到「只切出 1 个乐句」建议。"""
        flow = [{"pitch": 60 + (i % 7), "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                for i in range(16)]
        d = json.loads(run_cli("analyze", "--input", "-",
                               stdin=json.dumps({"bpm": 120, "notes": flow})).stdout)
        self.assertIn("乐句", " ".join(d["suggestions"]))


class TestBarStructure(unittest.TestCase):
    """小节级结构指标 —— 固定窗口取样，不依赖休止切分。

    动机：乐句级切分靠「音隔 ≥0.5 拍」，循环式作品（旋律几乎无休止）会被合并成
    一两个巨型乐句，小节内的同头结构落不进切分，于是高重复度的作品被误判为
    「缺少同头复用」。这组用例锁住修复。
    """

    @staticmethod
    def _loop_notes(bars=8):
        """连续八分音符 + 每小节固定的开头三音（模拟循环式写法，全程无休止）。"""
        heads = [[72, 74, 76], [69, 72, 74]]
        notes = []
        for b in range(bars):
            seq = (heads[b % 2] + [79, 76, 74, 72, 71])[:8]
            for i, p in enumerate(seq):
                notes.append({"pitch": p, "start_beat": b * 4 + i * 0.5,
                              "duration": 0.5, "velocity": 86 + (i % 3) * 4})
        return {"bpm": 120, "tracks": [{"name": "旋律", "channel": 0, "program": 0,
                                        "notes": notes}]}

    def test_detects_head_cell_reuse(self):
        r = run_cli("analyze", "--input", "-", stdin=json.dumps(self._loop_notes()))
        self.assertEqual(r.returncode, 0, r.stdout)
        bs = json.loads(r.stdout)["details"]["structure"]["bar_structure"]
        self.assertIsNotNone(bs, "小节级结构应被计算")
        self.assertEqual(bs["bars_with_melody"], 8)
        self.assertEqual(bs["head_cell_count"], 2, bs)
        self.assertEqual(bs["head_reuse"], 0.75, bs)

    def test_no_false_missing_head_suggestion(self):
        """全程无休止 → 乐句级 contour_reuse=0，但小节级重复成立，不应误报缺少同头。"""
        r = run_cli("analyze", "--input", "-", stdin=json.dumps(self._loop_notes()))
        d = json.loads(r.stdout)
        self.assertEqual(d["details"]["structure"]["contour_reuse_pairs"], 0,
                         "本 fixture 应切不出多个乐句（用于验证兜底分支）")
        joined = " ".join(d["suggestions"])
        self.assertNotIn("缺少「同头」", joined)
        self.assertIn("小节级结构明确", joined)     # 改为报出识别到的结构类型

    def test_through_composed_is_not_mislabelled_as_loop(self):
        """两轴重复都接近 0 时应判「通谱式」，而不是「双轴并重（严格循环）」——
        零重复与严格循环含义正相反，只用两轴差值会搞反。"""
        notes = []
        for b in range(8):                      # 每小节音高与节奏都唯一 → 两轴零重复
            head = [60 + b * 3, 62 + b * 3, 64 + b * 3]
            offs = [0.0, 0.5, 1.0 + b * 0.25, 2.0, 3.0]
            for p, o in zip(head + [74, 76], offs):
                notes.append({"pitch": p, "start_beat": b * 4 + o,
                              "duration": 0.5, "velocity": 88})
        r = run_cli("analyze", "--input", "-",
                    stdin=json.dumps({"bpm": 120, "tracks": [
                        {"name": "m", "channel": 0, "program": 0, "notes": notes}]}))
        self.assertEqual(r.returncode, 0, r.stdout)
        bs = json.loads(r.stdout)["details"]["structure"]["bar_structure"]
        self.assertLess(max(bs["head_reuse"], bs["rhythm_reuse"]), 0.3, bs)
        self.assertEqual(bs["structure_kind"], "通谱式（无小节级重复）", bs)

    def test_bar_structure_absent_for_short_melody(self):
        """少于 4 个可用小节时不产出该字段（避免用噪声下结论）。"""
        notes = [{"pitch": 60 + i, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(6)]                      # 不足 4 小节
        r = run_cli("analyze", "--input", "-",
                    stdin=json.dumps({"bpm": 120, "tracks": [
                        {"name": "m", "channel": 0, "program": 0, "notes": notes}]}))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIsNone(json.loads(r.stdout)["details"]["structure"]["bar_structure"])


class TestMultiVoiceGuard(unittest.TestCase):
    """单轨多声部守卫：低音+和弦+旋律挤在同一轨时，应提示拆声部而不是判「旋律断裂」。"""

    def test_mixed_voice_track_flagged(self):
        notes = []
        for b in range(8):                                  # 每小节：低音 + 中声部 + 旋律
            notes.append({"pitch": 41, "start_beat": b * 4, "duration": 4, "velocity": 90})
            notes.append({"pitch": 53 + b % 3, "start_beat": b * 4 + 0.5, "duration": 3, "velocity": 88})
            notes.append({"pitch": 60 + b % 4, "start_beat": b * 4 + 1.0, "duration": 2.5, "velocity": 86})
            notes.append({"pitch": 76 - b % 5, "start_beat": b * 4 + 2.0, "duration": 0.5, "velocity": 92})
        r = run_cli("analyze", "--input", "-",
                    stdin=json.dumps({"bpm": 120, "tracks": [
                        {"name": "MIDI Out", "channel": 0, "program": 0, "notes": notes}]}))
        self.assertEqual(r.returncode, 0, r.stdout)
        joined = " ".join(json.loads(r.stdout)["suggestions"])
        self.assertIn("同一个音轨", joined, joined)
        self.assertNotIn("旋律断裂", joined, "已识别为拆声部问题，不应再报旋律断裂")

    def test_normal_melody_not_flagged(self):
        """三度跳进为主的正常旋律（平均音程 <7 半音）不应被误判为多声部。"""
        notes = [{"pitch": p, "start_beat": i * 0.5, "duration": 0.5, "velocity": 88}
                 for i, p in enumerate([72, 76, 79, 76, 72, 76, 74, 71, 74, 79, 76, 72])]
        r = run_cli("analyze", "--input", "-",
                    stdin=json.dumps({"bpm": 120, "tracks": [
                        {"name": "Lead", "channel": 0, "program": 0, "notes": notes}]}))
        joined = " ".join(json.loads(r.stdout)["suggestions"])
        self.assertNotIn("同一个音轨", joined, joined)


class TestCompare(unittest.TestCase):
    def _tmp_song(self, td, notes, bpm=120, name="s.json"):
        p = Path(td) / name
        p.write_text(json.dumps({"bpm": bpm, "notes": notes}), encoding="utf-8")
        return p

    def test_compare_matches_self_generated_reference(self):
        """产出经 generate 得到 .mid 后，compare 自比应高度匹配。"""
        notes = [{"pitch": 60 + i, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(12)]
        with tempfile.TemporaryDirectory() as td:
            song = self._tmp_song(td, notes)
            mid = Path(td) / "ref.mid"
            run_cli("generate", "--input", str(song), "--output", str(mid))
            r = run_cli("compare", "--input", str(song), "--reference", str(mid))
            self.assertEqual(r.returncode, 0, r.stdout)
            d = json.loads(r.stdout)
            self.assertEqual(d["verdict"], "风格匹配")

    def test_compare_detects_style_divergence(self):
        """级进旋律 vs 跳进参考（音域跨度大）→ 判风格偏离。"""
        steps = [{"pitch": 60 + i, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(12)]
        leaps = [{"pitch": 60 + (i % 2) * 12, "start_beat": i * 0.5, "duration": 0.5, "velocity": 90}
                 for i in range(12)]
        with tempfile.TemporaryDirectory() as td:
            song = self._tmp_song(td, steps, name="steps.json")
            refsong = self._tmp_song(td, leaps, bpm=120, name="leaps.json")
            mid = Path(td) / "ref.mid"
            run_cli("generate", "--input", str(refsong), "--output", str(mid))
            r = run_cli("compare", "--input", str(song), "--reference", str(mid))
            self.assertEqual(r.returncode, 0, r.stdout)
            d = json.loads(r.stdout)
            self.assertEqual(d["verdict"], "风格偏离")
            self.assertFalse(d["dimensions"]["step_ratio"]["ok"])

    def test_compare_missing_reference_exit2(self):
        with tempfile.TemporaryDirectory() as td:
            song = self._tmp_song(td, [{"pitch": 60, "start_beat": 0, "duration": 1}])
            r = run_cli("compare", "--input", str(song), "--reference", str(Path(td) / "nope.mid"))
            self.assertEqual(r.returncode, 2)


class TestBpmOverride(unittest.TestCase):
    def test_bpm_flag_overrides_song_bpm(self):
        """--bpm 显式传入时必须覆盖 song.json 中的 bpm（回归：旧版 song 优先）。"""
        with tempfile.TemporaryDirectory() as td:
            song = {"bpm": 120,
                    "notes": [{"pitch": 60, "start_beat": 0, "duration": 1, "velocity": 90}]}
            mid = Path(td) / "t.mid"
            r = run_cli("generate", "--input", "-", "--output", str(mid), "--bpm", "95",
                        stdin=json.dumps(song))
            self.assertEqual(r.returncode, 0, r.stdout)
            data = json.loads(run_cli("inspect", "--input", str(mid)).stdout)
            self.assertEqual(data["bpm"], 95.0)

    def test_song_bpm_used_when_no_flag(self):
        with tempfile.TemporaryDirectory() as td:
            song = {"bpm": 95,
                    "notes": [{"pitch": 60, "start_beat": 0, "duration": 1, "velocity": 90}]}
            mid = Path(td) / "t.mid"
            r = run_cli("generate", "--input", "-", "--output", str(mid), stdin=json.dumps(song))
            self.assertEqual(r.returncode, 0, r.stdout)
            data = json.loads(run_cli("inspect", "--input", str(mid)).stdout)
            self.assertEqual(data["bpm"], 95.0)


class TestNameEncoding(unittest.TestCase):
    SONG = {"bpm": 95, "tracks": [{
        "name": "右手旋律", "channel": 0, "program": 0,
        "notes": [{"pitch": 60, "start_beat": 0, "duration": 1, "velocity": 90}],
    }]}

    def test_gbk_name_roundtrip(self):
        """GBK 写入（中文 Windows 工具标准）→ inspect 自动检测解码回原文。"""
        with tempfile.TemporaryDirectory() as td:
            mid = Path(td) / "t.mid"
            r = run_cli("generate", "--input", "-", "--output", str(mid),
                        "--name-encoding", "gbk", stdin=json.dumps(self.SONG))
            self.assertEqual(r.returncode, 0, r.stdout)
            data = json.loads(run_cli("inspect", "--input", str(mid)).stdout)
            self.assertEqual(data["tracks"][0]["name"], "右手旋律")

    def test_utf8_name_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            mid = Path(td) / "t.mid"
            r = run_cli("generate", "--input", "-", "--output", str(mid),
                        "--name-encoding", "utf-8", stdin=json.dumps(self.SONG))
            self.assertEqual(r.returncode, 0, r.stdout)
            data = json.loads(run_cli("inspect", "--input", str(mid)).stdout)
            self.assertEqual(data["tracks"][0]["name"], "右手旋律")

    def test_long_name_truncated_without_split_char(self):
        """超过 64 字节的音轨名截断后不得出现被切碎的字符。
        「旋律」= 2 个汉字 = 6 UTF-8 字节；×30 = 180 字节 → 截断到 63 字节 = 21 个汉字。"""
        with tempfile.TemporaryDirectory() as td:
            name = "旋律" * 30
            song = {"tracks": [{"name": name,
                                "notes": [{"pitch": 60, "start_beat": 0, "duration": 1}]}]}
            mid = Path(td) / "t.mid"
            r = run_cli("generate", "--input", "-", "--output", str(mid),
                        "--name-encoding", "utf-8", stdin=json.dumps(song))
            self.assertEqual(r.returncode, 0, r.stdout)
            got = json.loads(run_cli("inspect", "--input", str(mid)).stdout)["tracks"][0]["name"]
            self.assertNotIn("\ufffd", got)
            self.assertEqual(got, name[:21])  # 21 字符 = 63 字节 ≤ 64，且未切断汉字

    def test_unknown_encoding_rejected(self):
        r = run_cli("generate", "--input", "-", "--output", "x.mid",
                    "--name-encoding", "no-such-enc", stdin=json.dumps(self.SONG))
        self.assertEqual(r.returncode, 2)
        self.assertIn("未知编码", r.stdout)


class TestNegativeStart(unittest.TestCase):
    def test_negative_start_rejected(self):
        """负 start_beat 会破坏 VLQ 时间流，generate 必须拒绝而非静默写坏。"""
        song = {"notes": [{"pitch": 60, "start_beat": -1, "duration": 1}]}
        with tempfile.TemporaryDirectory() as td:
            mid = Path(td) / "t.mid"
            r = run_cli("generate", "--input", "-", "--output", str(mid),
                        stdin=json.dumps(song))
            self.assertEqual(r.returncode, 1)
            self.assertIn("start_beat", r.stdout)


class TestSongNameAndOutputDerivation(unittest.TestCase):
    """歌曲名 → 文件名派生 + 序列名写入（「每首歌一个目录」布局的基础）。"""

    SIMPLE = {"bpm": 100, "tracks": [{"name": "t", "channel": 0, "program": 0,
                                      "notes": [{"pitch": 60, "start_beat": 0,
                                                 "duration": 1, "velocity": 80}]}]}

    def _write_song(self, td, name=None, fname="song.json"):
        song = dict(self.SIMPLE)
        if name is not None:
            song["name"] = name
        p = Path(td) / fname
        p.write_text(json.dumps(song, ensure_ascii=False), encoding="utf-8")
        return p

    # ---------- slugify 边界 ----------
    def test_slugify_illegal_chars(self):
        sys.path.insert(0, str(ROOT))
        import aria_midi
        self.assertEqual(aria_midi.slugify("Wait Day"), "Wait Day")   # 空格保留
        self.assertEqual(aria_midi.slugify("a/b\\c:d*e?f"), "a_b_c_d_e_f")
        self.assertEqual(aria_midi.slugify(" x "), "x")
        self.assertEqual(aria_midi.slugify("第1首."), "第1首")          # 结尾点会坑 Windows
        self.assertEqual(aria_midi.slugify(".."), "song")              # 防路径穿越
        self.assertEqual(aria_midi.slugify(""), "song")
        self.assertEqual(aria_midi.slugify("   "), "song")
        self.assertEqual(aria_midi.slugify("未寄出的信"), "未寄出的信")   # 中文原样保留

    def test_slugify_length_cap(self):
        sys.path.insert(0, str(ROOT))
        import aria_midi
        out = aria_midi.slugify("あ" * 200)
        self.assertLessEqual(len(out), 60)
        self.assertTrue(out)

    # ---------- 输出路径派生 ----------
    def test_output_derived_from_song_name(self):
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, "未寄出的信")
            r = run_cli("generate", "--input", str(src))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)["output"]
            self.assertEqual(Path(out).name, "未寄出的信.mid")
            self.assertEqual(Path(out).parent, Path(td))          # 落在输入同目录
            self.assertTrue(Path(out).exists())

    def test_name_flag_overrides_song_name(self):
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, "原名")
            r = run_cli("generate", "--input", str(src), "--name", "新名")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(json.loads(r.stdout)["output"]).name, "新名.mid")

    def test_outdir_flag(self):
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, "歌")
            sub = Path(td) / "out"
            sub.mkdir()
            r = run_cli("generate", "--input", str(src), "--outdir", str(sub))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(json.loads(r.stdout)["output"]).parent, sub)

    def test_explicit_output_wins(self):
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, "歌")
            explicit = Path(td) / "whatever.mid"
            r = run_cli("generate", "--input", str(src), "--output", str(explicit))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(explicit.exists())

    def test_no_name_and_no_output_is_usage_error(self):
        """向后兼容：未命名作品仍必须显式给 --output。"""
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, name=None)
            r = run_cli("generate", "--input", str(src))
            self.assertEqual(r.returncode, 2)
            self.assertIn("--output", r.stderr + r.stdout)

    def test_outdir_missing_is_usage_error(self):
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, "歌")
            r = run_cli("generate", "--input", str(src),
                        "--outdir", str(Path(td) / "nope"))
            self.assertEqual(r.returncode, 2)

    # ---------- 序列名写入 ----------
    @staticmethod
    def _conductor_bytes(raw):
        """取出指挥轨（第一个 MTrk）的字节。

        不能用 `b"\\xff\\x03" in raw` 判断：每个音符轨自己也有 ff 03 音轨名事件，
        子串匹配分不清是哪一个。MThd 头固定 14 字节，其后第一个 MTrk 即指挥轨。
        """
        assert raw[:4] == b"MThd", raw[:8]
        off = 14
        assert raw[off:off + 4] == b"MTrk", raw[off:off + 8]
        length = int.from_bytes(raw[off + 4:off + 8], "big")
        return raw[off + 8:off + 8 + length]

    def test_sequence_name_written_when_named(self):
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, "My Song")
            out = Path(td) / "o.mid"
            self.assertEqual(run_cli("generate", "--input", str(src),
                                     "--output", str(out)).returncode, 0)
            conductor = self._conductor_bytes(out.read_bytes())
            self.assertIn(b"\xff\x03", conductor)
            self.assertIn("My Song".encode("utf-8"), conductor)

    def test_sequence_name_absent_when_unnamed(self):
        """未命名作品的输出必须与旧版一致 —— 指挥轨不写序列名事件。"""
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, name=None)
            out = Path(td) / "o.mid"
            self.assertEqual(run_cli("generate", "--input", str(src),
                                     "--output", str(out)).returncode, 0)
            self.assertNotIn(b"\xff\x03", self._conductor_bytes(out.read_bytes()))

    def test_sequence_name_truncated_without_split_char(self):
        """序列名超 64 字节时截断，且不切断多字节字符。"""
        long_name = "あ" * 40          # UTF-8 每字 3 字节 = 120 字节
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, long_name)
            out = Path(td) / "o.mid"
            self.assertEqual(run_cli("generate", "--input", str(src),
                                     "--output", str(out)).returncode, 0)
            conductor = self._conductor_bytes(out.read_bytes())
            # ff 03 <len> <payload>
            idx = conductor.index(b"\xff\x03")
            n = conductor[idx + 2]
            self.assertLessEqual(n, 64)
            self.assertEqual(conductor[idx + 3:idx + 3 + n].decode("utf-8"),
                             long_name[:n // 3])

    def test_generated_mid_reports_name_field(self):
        with tempfile.TemporaryDirectory() as td:
            src = self._write_song(td, "带标题的歌")
            data = json.loads(run_cli("generate", "--input", str(src)).stdout)
            self.assertEqual(data["name"], "带标题的歌")


if __name__ == "__main__":
    unittest.main(verbosity=2)
