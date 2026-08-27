# 真实 MIDI 案例

用于拆解真实编曲、测试 `aria-decode` / `aria-midi`、以及做风格提示词参考。

## 文件

| 文件 | 风格 | 来源 |
|------|------|------|
| `deephouse-demo.mid` | Deep House，126 BPM | 本机 `AiMidi-Skills/e2e-demo/deephouse-demo` |
| `tropical-demo.mid` | Tropical House，112 BPM | 本机 `AiMidi-Skills/e2e-demo/tropical-demo` |
| `lofi-demo.mid` | Lo-fi，75 BPM | 本机 `AiMidi-Skills/e2e-demo/lofi-demo` |

这些文件来自本地工作区的端到端演示项目，作为技能包内教学/测试案例收录；用于正式发布前请自行确认原始授权。

## 快速使用

```bash
python <技能包根目录>/toolkits/aria-decode/aria_decode.py decode --input examples/midi/deephouse-demo.mid --no-events
python <技能包根目录>/toolkits/aria-midi/aria_midi.py inspect --input examples/midi/deephouse-demo.mid
```

拆解模板见 `skills/aria-music-theory/references/house-melody-analysis.md`。

## 网络补充来源

本会话外网不可达，因此优先收录本机真实 MIDI。联网后可补充：

- Hugging Face `ronantakizawa/sampleflip-midi`：3764 个 MIDI 和弦进行，含 House / Trance / Progressive 目录
- GitHub `ldrolez/free-midi-chords`：13000+ 免费 MIDI 和弦/进行，MIT 许可
- GitHub `BenLeon2001/Free-Chord-Progressions`：免费和弦进行，无授权要求
