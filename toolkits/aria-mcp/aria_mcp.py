#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-mcp — 零依赖 MCP（Model Context Protocol）服务端（v1.0.0）

把 Aria 技能包的能力以 MCP 标准暴露给任意支持 MCP 的 Agent：
  - tools      11 个：音阶/和弦查表、校验、评分、生成 MIDI、解码、逆向分析报告
  - resources  知识层：skills/ 下的全部 Markdown（乐理体系/模式库/风格技法）按需拉取

设计要点：
  1. **零依赖**。MCP 的 stdio 传输本质是「按行分隔的 JSON-RPC 2.0」，
     这里用标准库手写实现，不引入官方 mcp SDK，保住本包「不装 pip 包」的卖点。
  2. **复用而非重写**。所有音乐计算走同包已发布的 CLI（subprocess + 其稳定的
     「JSON 进 JSON 出」契约），因此不改动 aria-midi / aria-decode / aria-report 任何代码。
  3. **传内容不传路径**。MCP 客户端可能与服务端不共享文件系统，故 MIDI 一律以
     base64 进出，中间用临时文件承接 CLI 的文件参数。
  4. **stdout 纯净**。stdout 只允许出现 JSON-RPC 消息；一切日志/诊断走 stderr，
     否则会破坏协议流。

用法（stdio 传输，由 MCP 客户端拉起）：
  python aria_mcp.py
自检：
  python aria_mcp.py --selftest
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile

__version__ = "1.0.0"

# 优先使用客户端请求的版本；不认识则回落到这个
PROTOCOL_DEFAULT = "2024-11-05"
PROTOCOL_KNOWN = ("2024-11-05", "2025-03-26", "2025-06-18")

SERVER_NAME = "aria-mcp"
ARIA_SKILL_PREFIX = "aria-"   # skills/ 下只认这些前缀的目录属于本包
TOOL_TIMEOUT = 120          # 单次工具调用上限（秒）
MAX_TEXT_CHARS = 400_000    # 单条返回文本上限，防上下文爆掉

SCALE_TYPES = ["major", "minor", "harmonic_minor", "melodic_minor", "dorian",
               "phrygian", "lydian", "mixolydian", "locrian",
               "pentatonic_major", "pentatonic_minor", "blues", "whole_tone"]
CHORD_TYPES = ["maj", "min", "dim", "aug", "maj7", "min7", "dom7", "m7b5",
               "dim7", "sus4", "sus2", "maj9", "min9", "add9"]

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKITS_DIR = os.path.dirname(HERE)


# ══════════════════════════════════════════════════════════════
# 定位同包资源
# ══════════════════════════════════════════════════════════════

def _script(sub, name):
    return os.path.join(TOOLKITS_DIR, sub, name)


ARIA_MIDI = _script("aria-midi", "aria_midi.py")
ARIA_DECODE = _script("aria-decode", "aria_decode.py")
ARIA_REPORT = _script("aria-report", "aria_report.py")


def find_skills_dir():
    """向上找 skills/ 目录。

    兼容两种布局：
      仓库检出   <root>/skills 与 <root>/toolkits/aria-mcp/
      ~/.agents  ~/.agents/skills 与 ~/.agents/toolkits/aria-mcp/
    两者都是「toolkits 的兄弟目录」。
    """
    cur = TOOLKITS_DIR
    for _ in range(4):
        cand = os.path.join(cur, "skills")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


SKILLS_DIR = find_skills_dir()


# ══════════════════════════════════════════════════════════════
# 调用同包 CLI
# ══════════════════════════════════════════════════════════════

class ToolError(Exception):
    """工具执行业务失败（回给客户端 isError=true，不是协议错误）。"""


def _run(script, args, stdin_bytes=None, allow_nonzero=False):
    """调用同包 CLI 并解析其 JSON 输出。

    allow_nonzero：CLI 用非零退出码表达「业务上的否」（典型是 validate 查出错误
    → 退出码 1，但 stdout 仍是一份完整的结构化结果）。对这类工具，非零退出码
    代表「工具成功执行并给出了否定结论」，不是执行失败 —— 若强行转成 isError，
    Agent 会把一次正常的校验当成工具崩溃，从而读不到它最需要的 errors 列表。
    """
    if not os.path.isfile(script):
        raise ToolError(f"找不到同包工具：{script}")
    try:
        p = subprocess.run([sys.executable, script, *args],
                           input=stdin_bytes, capture_output=True, timeout=TOOL_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ToolError(f"工具执行超时（>{TOOL_TIMEOUT}s）：{os.path.basename(script)}")
    out = p.stdout.decode("utf-8", errors="replace").strip()
    err = p.stderr.decode("utf-8", errors="replace").strip()

    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = None

    if p.returncode != 0:
        if allow_nonzero and parsed is not None:
            return parsed
        msg = ""
        for s in (err, out):                       # 结构化错误优先
            if not s:
                continue
            try:
                j = json.loads(s)
                if isinstance(j, dict) and j.get("error"):
                    msg = str(j["error"])
                    break
            except json.JSONDecodeError:
                pass
        raise ToolError(msg or err or out or f"退出码 {p.returncode}")

    if parsed is not None:
        return parsed
    if not out:
        raise ToolError("工具无输出")
    return {"_raw": out, "_stderr": err}


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _req(input_obj, what):
    if input_obj is None:
        raise ToolError(f"缺少必填参数：{what}")
    return input_obj


def _need(name, args):
    v = args.get(name)
    if v is None or v == "":
        raise ToolError(f"缺少必填参数：{name}")
    return v


def _midi_bytes_field(args, field="midi_base64"):
    """从 base64 字段取出 MIDI 字节。"""
    raw = _need(field, args)
    try:
        return base64.b64decode(raw, validate=False)
    except Exception as e:
        raise ToolError(f"{field} 不是合法 base64：{e}")


# ══════════════════════════════════════════════════════════════
# 工具实现
# ══════════════════════════════════════════════════════════════

def t_scale_list(args):
    root = _need("root", args)
    st = args.get("scale_type") or "major"
    return _run(ARIA_MIDI, ["scale", "--root", str(root), "--type", st, "--list"])


def t_chord_tones(args):
    root = _need("root", args)
    ct = _need("chord_type", args)
    st = args.get("scale_type") or "major"
    return _run(ARIA_MIDI, ["scale", "--root", str(root), "--type", st, "--chord", ct])


def t_snap_pitches(args):
    root = _need("root", args)
    pitches = args.get("pitches")
    if not isinstance(pitches, list) or not pitches:
        raise ToolError("pitches 必须是非空数组（MIDI 音高整数）")
    st = args.get("scale_type") or "major"
    return _run(ARIA_MIDI, ["scale", "--root", str(root), "--type", st, "--snap",
                            *[str(int(p)) for p in pitches]])


def t_suggest_scale(args):
    pitches = args.get("pitches")
    if not isinstance(pitches, list) or not pitches:
        raise ToolError("pitches 必须是非空数组（MIDI 音高整数）")
    csv = ",".join(str(int(p)) for p in pitches)
    return _run(ARIA_MIDI, ["scale", "--suggest", csv])


def t_validate_song(args):
    song = _req(args.get("song"), "song")
    cmd = ["validate", "--input", "-"]
    if args.get("strict"):
        cmd.append("--strict")
    # 校验查出错误时 CLI 退出码为 1，但结果要原样返回给 Agent 去修
    return _run(ARIA_MIDI, cmd, _json_bytes(song), allow_nonzero=True)


def t_analyze_song(args):
    song = _req(args.get("song"), "song")
    cmd = ["analyze", "--input", "-"]
    tmp = None
    try:
        if args.get("chords"):
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                              encoding="utf-8")
            json.dump(args["chords"], tmp, ensure_ascii=False)
            tmp.close()
            cmd += ["--chords", tmp.name]
        if args.get("key_root"):
            cmd += ["--key-root", str(args["key_root"])]
        if args.get("key_type"):
            cmd += ["--key-type", str(args["key_type"])]
        if args.get("style"):
            cmd += ["--style", str(args["style"])]
        if args.get("track"):
            cmd += ["--track", str(args["track"])]
        if args.get("all_tracks"):
            cmd.append("--all-tracks")
        if args.get("baseline"):
            cmd.append("--baseline")          # 用包内预置的人写语料基线（无参数）
        return _run(ARIA_MIDI, cmd, _json_bytes(song), allow_nonzero=True)
    finally:
        if tmp and os.path.exists(tmp.name):
            os.unlink(tmp.name)


def t_generate_midi(args):
    song = _req(args.get("song"), "song")
    cmd = ["generate", "--input", "-"]
    if args.get("bpm") is not None:
        cmd += ["--bpm", str(int(args["bpm"]))]
    if args.get("name_encoding"):
        cmd += ["--name-encoding", str(args["name_encoding"])]
    fd, path = tempfile.mkstemp(suffix=".mid")
    os.close(fd)
    try:
        cmd += ["--output", path]
        meta = _run(ARIA_MIDI, cmd, _json_bytes(song))
        with open(path, "rb") as f:
            data = f.read()
        meta.pop("output", None)          # 服务端临时路径无意义，不回传
        meta["midi_base64"] = base64.b64encode(data).decode("ascii")
        meta["size_bytes"] = len(data)
        meta["hint"] = ("把 midi_base64 解码为二进制即为标准 MIDI 文件；"
                        "若客户端与服务端共享文件系统，也可直接用 aria-midi generate 写盘。")
        return meta
    finally:
        if os.path.exists(path):
            os.unlink(path)


def t_inspect_midi(args):
    data = _midi_bytes_field(args)
    return _run(ARIA_MIDI, ["inspect", "--input", "-"], data)


def t_decode_midi(args):
    data = _midi_bytes_field(args)
    cmd = ["decode", "--input", "-"]
    if args.get("include_events") is False:
        cmd.append("--no-events")
    if args.get("include_notes") is False:
        cmd.append("--no-notes")
    return _run(ARIA_DECODE, cmd, data)


def t_compare_style(args):
    song = _req(args.get("song"), "song")
    ref = _midi_bytes_field(args, "reference_midi_base64")
    fd, path = tempfile.mkstemp(suffix=".mid")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(ref)
        return _run(ARIA_MIDI, ["compare", "--input", "-", "--reference", path],
                    _json_bytes(song))
    finally:
        if os.path.exists(path):
            os.unlink(path)


def t_report_midi(args):
    files = args.get("files")
    if not isinstance(files, list) or not files:
        raise ToolError("files 必须是非空数组，每项 {name, midi_base64}")
    fmt = args.get("format") or "json"
    workdir = tempfile.mkdtemp(prefix="aria-mcp-")
    try:
        for i, item in enumerate(files):
            if not isinstance(item, dict) or "midi_base64" not in item:
                raise ToolError(f"files[{i}] 需要 midi_base64 字段")
            name = item.get("name") or f"track{i}.mid"
            if not name.lower().endswith(".mid"):
                name += ".mid"
            name = os.path.basename(name)          # 防目录穿越
            try:
                blob = base64.b64decode(item["midi_base64"], validate=False)
            except Exception as e:
                raise ToolError(f"files[{i}].midi_base64 非法：{e}")
            with open(os.path.join(workdir, name), "wb") as f:
                f.write(blob)
        return _run(ARIA_REPORT, ["report", "--input", workdir, "--format", fmt])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
# 工具注册表
# ══════════════════════════════════════════════════════════════

def _schema(props, required):
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


_ROOT = {"type": "string",
         "description": "根音：音名（C4 / F#3 / Bb4）或 MIDI 编号（60）"}
_SCALE_TYPE = {"type": "string", "enum": SCALE_TYPES, "default": "major",
               "description": "音阶类型，默认 major"}
_PITCHES = {"type": "array", "items": {"type": "integer"},
            "description": "MIDI 音高整数数组，如 [60,62,64,65,67,69,71]"}
_SONG = {"type": "object",
         "description": ("song.json 结构：{bpm, time_signature?, tracks:[{name, channel, "
                         "program, notes:[{pitch, start_beat, duration, velocity}]}]}")}

TOOLS = [
    {
        "name": "scale_list",
        "description": "列出指定调式的音阶音（含 MIDI 编号）。写旋律前查音阶一律用本工具，不要心算。",
        "inputSchema": _schema({"root": _ROOT, "scale_type": _SCALE_TYPE}, ["root"]),
        "handler": t_scale_list,
    },
    {
        "name": "chord_tones",
        "description": "列出指定和弦的和弦音（含 MIDI 编号）。写和声/配和弦时用来确定强拍该落哪些音。",
        "inputSchema": _schema({"root": _ROOT,
                                "chord_type": {"type": "string", "enum": CHORD_TYPES,
                                               "description": "和弦类型"},
                                "scale_type": _SCALE_TYPE}, ["root", "chord_type"]),
        "handler": t_chord_tones,
    },
    {
        "name": "snap_pitches",
        "description": "把一组音高吸附到指定调式内，返回吸附后的音高。用于修正「音阶外」的音。",
        "inputSchema": _schema({"root": _ROOT, "scale_type": _SCALE_TYPE,
                                "pitches": _PITCHES}, ["root", "pitches"]),
        "handler": t_snap_pitches,
    },
    {
        "name": "suggest_scale",
        "description": "由一组音高反推可能的调式（13 种音阶 × 12 根音按覆盖率降序，返回前 5 条候选）。",
        "inputSchema": _schema({"pitches": _PITCHES}, ["pitches"]),
        "handler": t_suggest_scale,
    },
    {
        "name": "validate_song",
        "description": ("校验 song.json：量化(0.25 拍网格)、音域、力度、同音高重叠、轨道完整性。"
                        "**每次写完或改完音符都必须调用**，要求 ok=true 且 errors 为空。"),
        "inputSchema": _schema({"song": _SONG,
                                "strict": {"type": "boolean", "default": False,
                                           "description": "严格模式：越界/量化偏差一律报错而非警告"}},
                               ["song"]),
        "handler": t_validate_song,
    },
    {
        "name": "analyze_song",
        "description": ("旋律诊断（技术分/音乐性分/乐句结构分 + 细节指标 + 中文建议）。"
                        "注意这是诊断不是闸门：总分在音符层面没有梯度（单个音移 ±7 半音分数不变），"
                        "不要为了拉分改旋律。硬闸只有 validate_song。"
                        "baseline=true 时额外返回本曲在人写语料分位数中的落点——"
                        "只看 role=diagnostic 的三项，且只在两端都是病时才当问题；"
                        "role=style / convention_dependent 一律不判（已知好作品会落在分布外）。"),
        "inputSchema": _schema({
            "song": _SONG,
            "chords": {"type": "object",
                       "description": "chords.json：{chords:[{root, type, start_beat, duration}]}，给出后才会检查强拍和弦音匹配"},
            "key_root": {"type": "string", "description": "调式根音（如 F#4），给出后检查终止稳定性"},
            "key_type": {"type": "string", "enum": SCALE_TYPES},
            "style": {"type": "string", "enum": ["melodic", "jazz", "arpeggio", "blues", "edm", "lofi"],
                      "description": "跳进型风格用 jazz/arpeggio 等显式豁免级进占比约束"},
            "track": {"type": "string", "description": "按名称指定评分音轨（默认取平均音高最高的旋律轨）"},
            "all_tracks": {"type": "boolean", "default": False},
            "baseline": {"type": "boolean", "default": False,
                         "description": "对照包内预置的人写语料分位数（POP909 300 首）"},
        }, ["song"]),
        "handler": t_analyze_song,
    },
    {
        "name": "generate_midi",
        "description": ("把 song.json 生成标准 MIDI 文件（Type-1, TPQN=480），返回 base64。"
                        "生成后建议再用 inspect_midi 回读核对音符数/BPM 是否一致。"),
        "inputSchema": _schema({
            "song": _SONG,
            "bpm": {"type": "integer", "description": "覆盖 song.json 里的 bpm（40-300）"},
            "name_encoding": {"type": "string", "description": "音轨名编码，中文 Windows 建议 gbk"},
        }, ["song"]),
        "handler": t_generate_midi,
    },
    {
        "name": "inspect_midi",
        "description": "解析 MIDI 为音符列表/音轨/BPM（有损，只提取音符与轨道信息）。做往返自检用。",
        "inputSchema": _schema({"midi_base64": {"type": "string", "description": "MIDI 文件的 base64"}},
                               ["midi_base64"]),
        "handler": t_inspect_midi,
    },
    {
        "name": "decode_midi",
        "description": ("无损解码 MIDI 为结构化 JSON，保留每一个事件（meta/CC/弯音/歌词/SysEx/系统消息）。"
                        "需要检查 Tempo 变化、CC、弯音或做事件级调试时用它（inspect_midi 会丢这些）。"),
        "inputSchema": _schema({
            "midi_base64": {"type": "string"},
            "include_events": {"type": "boolean", "default": True,
                               "description": "false 时只要头部+全局+音符（体积最小）"},
            "include_notes": {"type": "boolean", "default": True,
                              "description": "false 时只要事件明细"},
        }, ["midi_base64"]),
        "handler": t_decode_midi,
    },
    {
        "name": "compare_style",
        "description": "风格锚定：把产出与参考 MIDI 做多维参数对比（BPM/级进占比/音域/力度极差/密度），给出相似度与判定。",
        "inputSchema": _schema({
            "song": _SONG,
            "reference_midi_base64": {"type": "string", "description": "参考 MIDI 的 base64"},
        }, ["song", "reference_midi_base64"]),
        "handler": t_compare_style,
    },
    {
        "name": "report_midi",
        "description": ("批量逆向分析：对一批 MIDI 做「风格识别 + 调式推测 + 旋律动机提取」，"
                        "输出报告。拿到人类编曲的 MIDI 想看清它是什么风格、动机怎么发展时用。"),
        "inputSchema": _schema({
            "files": {"type": "array", "description": "每个元素 {name, midi_base64}",
                      "items": {"type": "object",
                                "properties": {"name": {"type": "string"},
                                               "midi_base64": {"type": "string"}},
                                "required": ["midi_base64"]}},
            "format": {"type": "string", "enum": ["json", "md"], "default": "json"},
        }, ["files"]),
        "handler": t_report_midi,
    },
]

TOOL_MAP = {t["name"]: t for t in TOOLS}


# ══════════════════════════════════════════════════════════════
# 知识库资源（skills/ 下的 Markdown）
# ══════════════════════════════════════════════════════════════

def list_resources():
    """把 Aria 自己的技能文档登记为 MCP resources，客户端按需拉取。

    只认 `aria-` 前缀的技能目录。`skills/` 在真实安装环境下是**共享目录**
    （~/.agents/skills/ 往往还装着别的技能），若整棵子树照单全收，就会把
    brainstorming、systematic-debugging 之类无关文档冒充成 Aria 的知识库。
    """
    out = []
    if not SKILLS_DIR:
        return out
    for entry in sorted(os.listdir(SKILLS_DIR)):
        if not entry.startswith(ARIA_SKILL_PREFIX):
            continue
        sub = os.path.join(SKILLS_DIR, entry)
        if not os.path.isdir(sub):
            continue
        for root, _dirs, names in os.walk(sub):
            for n in sorted(names):
                if not n.lower().endswith(".md"):
                    continue
                full = os.path.join(root, n)
                rel = os.path.relpath(full, SKILLS_DIR).replace(os.sep, "/")
                out.append({
                    "uri": f"aria://knowledge/{rel}",
                    "name": rel,
                    "description": _describe(rel),
                    "mimeType": "text/markdown",
                })
    out.sort(key=lambda r: r["uri"])
    return out


_DESC = {
    "aria-compose/SKILL.md": "作曲工作流入口：五步工作流 + 七大作曲规则 + 质量检查清单",
    "aria-compose/references/composition-rules.md": "作曲规则总纲：段落规范/和弦规范/7 大规则",
    "aria-compose/references/pattern-library.md": "模式库：和弦进行配方/伴奏织体/节奏律动/旋律发展技法/结构模板/情绪映射",
    "aria-compose/references/melody-chord-writing.md": "旋律与和弦写作：强拍和弦音骨架/和弦外音分型/真实案例",
    "aria-compose/references/midi-schema.md": "song.json 与 chords.json 数据规范 + GM 音色表",
    "aria-compose/references/examples.md": "完整范例：流行副歌/EDM Build-up/爵士 Walking Bass",
    "aria-compose/references/anti-formula.md": "反公式化：默认规则豁免清单，写第二稿时读",
    "aria-compose/references/web-research-guide.md": "联网检索机制与质量门槛",
    "aria-music-theory/SKILL.md": "乐理问答入口：音阶/和弦/进行查表与解释",
    "aria-music-theory/references/theory-arrangement.md": "乐理功能 + 声部进行 + 风格化编曲提示词模板",
    "aria-music-theory/references/electronic-arrangement.md": "电子音乐编曲：EDM 乐理 + 舞曲结构",
    "aria-music-theory/references/house-melody-analysis.md": "House 旋律分析：真实 MIDI 拆解 + 多风格对照",
}


def _describe(rel):
    if rel in _DESC:
        return _DESC[rel]
    base = os.path.basename(rel)
    if base.startswith("styles/"):
        return f"风格知识：{base[:-3]}"
    return f"知识库文档：{rel}"


def read_resource(uri):
    if not uri.startswith("aria://knowledge/"):
        raise ToolError(f"未知资源 URI：{uri}")
    rel = uri[len("aria://knowledge/"):]
    if not SKILLS_DIR:
        raise ToolError("未找到 skills/ 知识库目录（应与 toolkits/ 同级）")
    # 防目录穿越
    target = os.path.normpath(os.path.join(SKILLS_DIR, rel))
    root = os.path.normpath(SKILLS_DIR)
    if not target.startswith(root + os.sep) or not os.path.isfile(target):
        raise ToolError(f"资源不存在：{rel}")
    with open(target, "r", encoding="utf-8") as f:
        return f.read()


# ══════════════════════════════════════════════════════════════
# JSON-RPC 2.0 / MCP 协议层
# ══════════════════════════════════════════════════════════════

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _too_large_text(result, text):
    """结果超过上限时，返回**合法 JSON** 的说明信封。

    绝不能直接截断序列化后的 JSON —— 半截 JSON 客户端无法解析，表现成
    「工具返回了垃圾」而不是「结果太大」。信封里给出实际大小、可读预览，
    以及怎么缩小结果的提示。
    """
    hint = ("结果过大，已不返回完整内容。缩小方式："
            "decode_midi 用 include_events:false（或 include_notes:false）取所需的一半；"
            "report_midi 减少 files 数量；inspect_midi 换用 decode_midi 的紧凑模式。")
    if isinstance(result, list):
        hint = "结果是数组，请减少请求的文件数量。 " + hint
    return json.dumps({
        "ok": False,
        "truncated": True,
        "reason": "result_too_large",
        "actual_chars": len(text),
        "limit_chars": MAX_TEXT_CHARS,
        "hint": hint,
        "preview": text[:2000],
    }, ensure_ascii=False, indent=2)


def _log(*a):
    """诊断信息一律走 stderr —— stdout 只能有 JSON-RPC 消息。"""
    print("[aria-mcp]", *a, file=sys.stderr)
    sys.stderr.flush()


def _text_result(text, is_error=False):
    obj = {"content": [{"type": "text", "text": text}]}
    if is_error:
        obj["isError"] = True
    return obj


def handle(msg):
    """处理一条 JSON-RPC 消息，返回响应对象；通知类返回 None。"""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": INVALID_REQUEST, "message": "消息必须是 JSON 对象"}}
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    is_notification = "id" not in msg

    if not isinstance(method, str):
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": INVALID_REQUEST, "message": "缺少 method"}}

    # ---- 通知：不响应 ----
    if is_notification:
        if method not in ("notifications/initialized", "notifications/cancelled",
                          "notifications/roots/list_changed"):
            _log("忽略未知通知:", method)
        return None

    try:
        if method == "initialize":
            want = params.get("protocolVersion")
            ver = want if want in PROTOCOL_KNOWN else PROTOCOL_DEFAULT
            return _ok(mid, {
                "protocolVersion": ver,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME, "version": __version__},
                "instructions": (
                    "Aria 音乐技能包。写歌流程：scale_list/chord_tones 查表 → validate_song 校验"
                    "（这是唯一的硬闸）→ analyze_song 诊断（可加 baseline 对照人写分位数）→ "
                    "generate_midi 生成 → inspect_midi 回读自检。"
                    "注意 analyze_song 的分数不参与放行：它在音符层面没有梯度，"
                    "不要为了拉分改旋律；好不好听只能靠人耳，交付前务必回放试听。"
                    "知识库（作曲规则/模式库/风格技法）见 resources。"
                ),
            })

        if method == "ping":
            return _ok(mid, {})

        if method == "tools/list":
            return _ok(mid, {"tools": [
                {"name": t["name"], "description": t["description"],
                 "inputSchema": t["inputSchema"]} for t in TOOLS]})

        if method == "tools/call":
            name = params.get("name")
            if name not in TOOL_MAP:
                return {"jsonrpc": "2.0", "id": mid,
                        "error": {"code": INVALID_PARAMS, "message": f"未知工具：{name}"}}
            try:
                result = TOOL_MAP[name]["handler"](params.get("arguments") or {})
            except ToolError as e:
                return _ok(mid, _text_result(str(e), is_error=True))
            except Exception as e:                      # noqa: BLE001 — 兜住一切，别让循环崩
                return _ok(mid, _text_result(f"{type(e).__name__}: {e}", is_error=True))
            text = json.dumps(result, ensure_ascii=False, indent=2)
            if len(text) > MAX_TEXT_CHARS:
                text = _too_large_text(result, text)
            return _ok(mid, _text_result(text))

        if method == "resources/list":
            return _ok(mid, {"resources": list_resources()})

        if method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return {"jsonrpc": "2.0", "id": mid,
                        "error": {"code": INVALID_PARAMS, "message": "缺少 uri"}}
            try:
                text = read_resource(uri)
            except ToolError as e:
                return {"jsonrpc": "2.0", "id": mid,
                        "error": {"code": INVALID_PARAMS, "message": str(e)}}
            return _ok(mid, {"contents": [{"uri": uri, "mimeType": "text/markdown",
                                           "text": text}]})

        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": METHOD_NOT_FOUND, "message": f"未实现的方法：{method}"}}

    except Exception as e:                              # noqa: BLE001
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": INTERNAL_ERROR, "message": f"{type(e).__name__}: {e}"}}


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _write(obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(data + b"\n")
    sys.stdout.buffer.flush()


def serve(stdin=None, stdout=None):
    """按行读 JSON-RPC 消息，逐条处理。返回处理过的消息数。"""
    inp = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout.buffer
    n = 0
    for raw in inp:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": PARSE_ERROR, "message": f"JSON 解析失败: {e}"}}
            out.write(json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\n")
            out.flush()
            continue
        resp = handle(msg)
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\n")
            out.flush()
        n += 1
    return n


# ══════════════════════════════════════════════════════════════
# 自检
# ══════════════════════════════════════════════════════════════

def selftest():
    import io
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": PROTOCOL_DEFAULT, "capabilities": {},
                    "clientInfo": {"name": "selftest", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "scale_list", "arguments": {"root": "F#4", "scale_type": "major"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
    ]
    buf = io.BytesIO(b"".join(
        json.dumps(m, ensure_ascii=False).encode("utf-8") + b"\n" for m in lines))
    outbuf = io.BytesIO()
    n = serve(stdin=buf, stdout=outbuf)
    ok = True
    for raw in outbuf.getvalue().splitlines():
        r = json.loads(raw)
        rid = r.get("id")
        if rid == 1:
            ok &= r["result"]["serverInfo"]["name"] == SERVER_NAME
        if rid == 2:
            ok &= len(r["result"]["tools"]) == len(TOOLS)
            print(f"  tools: {len(r['result']['tools'])} 个")
        if rid == 3:
            payload = json.loads(r["result"]["content"][0]["text"])
            tones = [t["name"] for t in payload["notes"]]
            ok &= tones == ["F#4", "G#4", "A#4", "B4", "C#5", "D#5", "F5"]
            print(f"  scale_list(F#4 major): {' '.join(tones)}")
        if rid == 4:
            print(f"  resources: {len(r['result']['resources'])} 个")
    print(f"  处理消息 {n} 条（含 1 条通知）")
    print("自检通过" if ok else "自检失败")
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if "--version" in argv:
        print(f"{SERVER_NAME} {__version__}")
        return 0
    if "--selftest" in argv:
        return selftest()
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    n = serve()
    _log(f"输入结束，共处理 {n} 条消息，退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
