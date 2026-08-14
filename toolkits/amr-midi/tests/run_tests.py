#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""amr_midi.py 冒烟测试（stdlib unittest + subprocess，无第三方依赖）。

运行：python tests/run_tests.py（从 amr-midi 目录）
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # amr-midi 目录
CLI = ROOT / "amr_midi.py"
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
