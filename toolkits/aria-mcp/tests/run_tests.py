#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-mcp 服务端 — 测试套件（零依赖，仅标准库）

运行：python tests/run_tests.py
全部通过退出码 0；任一失败退出码 1，并打印失败详情。

分两层：
  协议层 —— JSON-RPC 2.0 / MCP 握手、tools/resources、错误码、stdio 分帧、stdout 纯净性
  工具层 —— 11 个工具的正路与错路，以及与 CLI 直调的结果一致性（包装层不得改变结果）
"""

import base64
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import aria_mcp  # noqa: E402

SERVER = os.path.join(ROOT, "aria_mcp.py")

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


# ────────────────────────── 协议辅助 ──────────────────────────

def rpc(method, params=None, mid=1, notify=False):
    m = {"jsonrpc": "2.0", "method": method}
    if not notify:
        m["id"] = mid
    if params is not None:
        m["params"] = params
    return m


def call_tool(name, args=None, mid=1):
    return aria_mcp.handle(rpc("tools/call", {"name": name, "arguments": args or {}}, mid))


def tool_text(resp):
    return resp["result"]["content"][0]["text"]


def tool_json(resp):
    return json.loads(tool_text(resp))


def is_error(resp):
    return bool(resp.get("result", {}).get("isError"))


def run_stdio(messages, timeout=120):
    """真正拉起子进程走 stdio，返回 (returncode, 解析后的响应列表, stderr)。"""
    payload = b"".join(json.dumps(m, ensure_ascii=False).encode("utf-8") + b"\n"
                       for m in messages)
    p = subprocess.run([sys.executable, SERVER], input=payload,
                       capture_output=True, timeout=timeout)
    outs = []
    for line in p.stdout.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            outs.append(json.loads(line))
    return p.returncode, outs, p.stderr.decode("utf-8", errors="replace")


# ────────────────────────── 素材 ──────────────────────────

def mini_song():
    """4 小节两根轨的小素材，用来跑通全链路。"""
    mel = [62, 64, 65, 64, 62, 60, 62, 65, 67, 65, 64, 62]
    bass = [38, 38, 43, 43, 41, 41, 38, 38]
    return {
        "bpm": 72,
        "time_signature": {"numerator": 4, "denominator": 4},
        "tracks": [
            {"name": "旋律", "channel": 0, "program": 0,
             "notes": [{"pitch": p, "start_beat": i * 0.5, "duration": 0.5,
                        "velocity": 60 + (i % 4) * 6} for i, p in enumerate(mel)]},
            {"name": "低音", "channel": 1, "program": 33,
             "notes": [{"pitch": p, "start_beat": i * 2.0, "duration": 2.0,
                        "velocity": 70 + (i % 3) * 5} for i, p in enumerate(bass)]},
        ],
    }


def mini_chords():
    return {"chords": [
        {"root": 50, "type": "min", "start_beat": 0.0, "duration": 4.0},
        {"root": 50, "type": "min", "start_beat": 4.0, "duration": 4.0},
        {"root": 55, "type": "min", "start_beat": 8.0, "duration": 4.0},
        {"root": 53, "type": "maj", "start_beat": 12.0, "duration": 4.0},
    ]}


def gen_midi_b64():
    resp = call_tool("generate_midi", {"song": mini_song(), "bpm": 72})
    return tool_json(resp)["midi_base64"]


# ────────────────────────── 协议层 ──────────────────────────

def test_initialize():
    r = aria_mcp.handle(rpc("initialize", {"protocolVersion": aria_mcp.PROTOCOL_DEFAULT,
                                           "capabilities": {}}, 1))
    info = r["result"]["serverInfo"]
    check("initialize serverInfo", info["name"] == aria_mcp.SERVER_NAME
          and info["version"] == aria_mcp.__version__, str(info))
    caps = r["result"]["capabilities"]
    check("initialize capabilities", "tools" in caps and "resources" in caps, str(caps))
    check("initialize 带 instructions", isinstance(r["result"].get("instructions"), str),
          str(r["result"].get("instructions"))[:40])


def test_protocol_negotiation():
    for v in aria_mcp.PROTOCOL_KNOWN:
        r = aria_mcp.handle(rpc("initialize", {"protocolVersion": v}, 1))
        if r["result"]["protocolVersion"] != v:
            check(f"协议版本回显 {v}", False, r["result"]["protocolVersion"])
            return
    check("协议版本回显已知版本", True)
    r = aria_mcp.handle(rpc("initialize", {"protocolVersion": "1999-01-01"}, 1))
    check("未知版本回落到默认", r["result"]["protocolVersion"] == aria_mcp.PROTOCOL_DEFAULT,
          r["result"]["protocolVersion"])


def test_notification_no_response():
    check("通知不回响应（initialized）",
          aria_mcp.handle(rpc("notifications/initialized", notify=True)) is None)
    check("通知不回响应（未知通知）",
          aria_mcp.handle(rpc("notifications/whatever", notify=True)) is None)


def test_ping():
    r = aria_mcp.handle(rpc("ping", {}, 7))
    check("ping 返回空 result 且回显 id", r["id"] == 7 and r["result"] == {}, str(r))


def test_tools_list():
    r = aria_mcp.handle(rpc("tools/list", {}, 2))
    tools = r["result"]["tools"]
    check("tools/list 数量", len(tools) == len(aria_mcp.TOOLS), len(tools))
    check("tools/list 字段齐全",
          all({"name", "description", "inputSchema"} <= set(t) for t in tools), "缺字段")
    names = {t["name"] for t in tools}
    expect = {"scale_list", "chord_tones", "snap_pitches", "suggest_scale",
              "validate_song", "analyze_song", "generate_midi", "inspect_midi",
              "decode_midi", "compare_style", "report_midi"}
    check("tools/list 名称集合", names == expect, str(names ^ expect))


def test_schemas_self_consistent():
    bad = []
    for t in aria_mcp.TOOLS:
        s = t["inputSchema"]
        if s.get("type") != "object":
            bad.append((t["name"], "非 object"))
        props = s.get("properties", {})
        for req in s.get("required", []):
            if req not in props:
                bad.append((t["name"], f"required 的 {req} 不在 properties"))
        for k, v in props.items():
            if v.get("type") == "array" and "items" not in v:
                bad.append((t["name"], f"{k} 是 array 但缺 items"))
    check("inputSchema 自洽（required ⊆ properties，array 带 items）", not bad, str(bad))


def test_unknown_method():
    r = aria_mcp.handle(rpc("no/such/method", {}, 3))
    check("未知方法 -> -32601",
          r["error"]["code"] == aria_mcp.METHOD_NOT_FOUND, str(r.get("error")))


def test_bad_request_shape():
    r = aria_mcp.handle({"jsonrpc": "2.0", "id": 1})
    check("缺 method -> -32600",
          r["error"]["code"] == aria_mcp.INVALID_REQUEST, str(r.get("error")))
    r = aria_mcp.handle("not a dict")
    check("非对象消息 -> -32600",
          r["error"]["code"] == aria_mcp.INVALID_REQUEST, str(r.get("error")))


def test_unknown_tool():
    r = call_tool("no_such_tool", {})
    check("未知工具 -> -32602",
          r["error"]["code"] == aria_mcp.INVALID_PARAMS, str(r.get("error")))


def test_missing_required_arg():
    r = call_tool("scale_list", {})
    check("缺必填参数 -> isError", is_error(r), tool_text(r))
    r = call_tool("chord_tones", {"root": "C4"})
    check("缺 chord_type -> isError", is_error(r), tool_text(r))
    r = call_tool("validate_song", {})
    check("缺 song -> isError", is_error(r), tool_text(r))


def test_bad_base64():
    r = call_tool("inspect_midi", {"midi_base64": "!!!not base64!!!"})
    check("非法 base64 不崩且返回 isError 或结构化错误",
          is_error(r) or "error" in tool_json(r), tool_text(r)[:80])


def test_serve_framing():
    msgs = [rpc("initialize", {"protocolVersion": aria_mcp.PROTOCOL_DEFAULT}, 1),
            rpc("notifications/initialized", notify=True),
            rpc("ping", {}, 2),
            rpc("tools/list", {}, 3)]
    payload = b"".join(json.dumps(m).encode() + b"\n" for m in msgs[:1])
    payload += b"\n"                       # 空行应被忽略
    payload += b"   \n"                    # 空白行应被忽略
    payload += b"".join(json.dumps(m).encode() + b"\n" for m in msgs[1:])
    out = io.BytesIO()
    n = aria_mcp.serve(stdin=io.BytesIO(payload), stdout=out)
    got = [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]
    check("serve 处理条数（含通知）", n == 4, n)
    check("serve 通知不产出响应（4 进 3 出）", len(got) == 3, len(got))
    check("serve 回显 id 顺序", [g["id"] for g in got] == [1, 2, 3], [g["id"] for g in got])


def test_multiple_messages_one_line_each():
    """每条响应独占一行，且都是合法 JSON —— stdout 纯净性。"""
    out = io.BytesIO()
    aria_mcp.serve(stdin=io.BytesIO(b"".join(
        json.dumps(m).encode() + b"\n" for m in
        [rpc("initialize", {}, 1), rpc("tools/list", {}, 2), rpc("resources/list", {}, 3)])),
        stdout=out)
    lines = [l for l in out.getvalue().splitlines() if l.strip()]
    ok = True
    for l in lines:
        try:
            o = json.loads(l)
            ok &= o.get("jsonrpc") == "2.0"
        except Exception:
            ok = False
    check("stdout 每行都是合法 JSON-RPC", ok and len(lines) == 3, str(lines)[:120])


def test_parse_error_via_serve():
    out = io.BytesIO()
    aria_mcp.serve(stdin=io.BytesIO(b"{ not json }\n"), stdout=out)
    r = json.loads(out.getvalue().decode())
    check("非法 JSON -> -32700",
          r["error"]["code"] == aria_mcp.PARSE_ERROR, str(r.get("error")))


def test_handle_never_raises():
    """handle 对任何输入都应返回响应或 None，绝不抛异常。"""
    weird = [None, 0, "", [], {}, {"method": 1}, {"id": 1, "method": "initialize",
                                                  "params": "not a dict"},
             {"id": 1, "method": "tools/call", "params": {"name": "scale_list",
                                                          "arguments": "not a dict"}}]
    ok = True
    for w in weird:
        try:
            r = aria_mcp.handle(w)
            ok &= r is None or isinstance(r, dict)
        except Exception as e:
            ok = False
            print(f"      抛异常: {w!r} -> {type(e).__name__}: {e}")
    check("handle 对畸形输入不抛异常", ok)


# ────────────────────────── 资源层 ──────────────────────────

def test_resources_list():
    r = aria_mcp.handle(rpc("resources/list", {}, 4))
    res = r["result"]["resources"]
    check("resources 数量 > 0", len(res) > 0, len(res))
    check("resources 字段齐全",
          all({"uri", "name", "mimeType"} <= set(x) for x in res), "缺字段")
    check("resources URI 前缀",
          all(x["uri"].startswith("aria://knowledge/") for x in res), "前缀不符")
    check("resources 含作曲规则与模式库",
          any("composition-rules" in x["uri"] for x in res)
          and any("pattern-library" in x["uri"] for x in res), "缺关键文档")


def test_resources_scoped_to_aria_skills():
    """skills/ 是共享目录（~/.agents/skills 下常有别的技能），
    只应登记 aria- 前缀技能自己的文档，不能把别人的文档冒充成 Aria 知识库。"""
    res = aria_mcp.list_resources()
    tops = {x["uri"].split("/")[3] for x in res}     # aria://knowledge/<top>/...
    bad = {t for t in tops if not t.startswith(aria_mcp.ARIA_SKILL_PREFIX)}
    check("resources 只含 aria-* 技能", not bad, str(bad))
    check("resources 覆盖两个 aria 技能",
          {"aria-compose", "aria-music-theory"} <= tops, str(tops))


def test_resources_ignores_foreign_skills(tmpdir=None):
    """直接验证：skills/ 里混入无关技能目录时，不污染 resources。"""
    if not aria_mcp.SKILLS_DIR:
        check("混合技能目录（跳过：无 skills/）", True, "")
        return
    foreign = os.path.join(aria_mcp.SKILLS_DIR, "zz-not-aria-skill")
    made = False
    try:
        if not os.path.exists(foreign):
            os.makedirs(foreign)
            with open(os.path.join(foreign, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("# 无关技能\n")
            made = True
        res = aria_mcp.list_resources()
        leaked = [x["uri"] for x in res if "zz-not-aria-skill" in x["uri"]]
        check("无关技能目录不进入 resources", not leaked, str(leaked))
    finally:
        if made:
            import shutil as _sh
            _sh.rmtree(foreign, ignore_errors=True)


def test_resources_read():
    uri = "aria://knowledge/aria-compose/references/composition-rules.md"
    r = aria_mcp.handle(rpc("resources/read", {"uri": uri}, 5))
    txt = r["result"]["contents"][0]["text"]
    check("resources/read 返回正文", len(txt) > 1000 and "作曲" in txt, len(txt))
    check("resources/read mimeType",
          r["result"]["contents"][0]["mimeType"] == "text/markdown",
          r["result"]["contents"][0]["mimeType"])


def test_resources_read_unknown():
    r = aria_mcp.handle(rpc("resources/read", {"uri": "aria://knowledge/nope.md"}, 6))
    check("未知资源 -> -32602",
          r["error"]["code"] == aria_mcp.INVALID_PARAMS, str(r.get("error")))
    r = aria_mcp.handle(rpc("resources/read", {"uri": "file:///etc/passwd"}, 7))
    check("非 aria:// 前缀被拒",
          r["error"]["code"] == aria_mcp.INVALID_PARAMS, str(r.get("error")))


def test_resources_path_traversal():
    evil = ["aria://knowledge/../../../../etc/passwd",
            "aria://knowledge/..%2f..%2fsecret",
            "aria://knowledge/../../../install.py",
            "aria://knowledge/aria-compose/../../../LICENSE"]
    bad = []
    for u in evil:
        r = aria_mcp.handle(rpc("resources/read", {"uri": u}, 8))
        if "result" in r:
            bad.append(u)
    check("路径穿越被拒", not bad, str(bad))


# ────────────────────────── 工具层 ──────────────────────────

def test_scale_list():
    j = tool_json(call_tool("scale_list", {"root": "F#4", "scale_type": "major"}))
    names = [n["name"] for n in j["notes"]]
    check("scale_list F# 大调 7 音",
          names == ["F#4", "G#4", "A#4", "B4", "C#5", "D#5", "F5"], names)
    check("scale_list 带 MIDI 编号", [n["midi"] for n in j["notes"]] ==
          [66, 68, 70, 71, 73, 75, 77], str(j["notes"]))


def test_chord_tones():
    j = tool_json(call_tool("chord_tones", {"root": "D4", "chord_type": "min"}))
    check("chord_tones D 小三和弦", [t["name"] for t in j["tones"]] == ["D4", "F4", "A4"],
          str(j["tones"]))
    j = tool_json(call_tool("chord_tones", {"root": "G4", "chord_type": "dom7"}))
    check("chord_tones G7 四音", [t["midi"] for t in j["tones"]] == [67, 71, 74, 77],
          str(j["tones"]))


def test_snap_pitches():
    j = tool_json(call_tool("snap_pitches", {"root": "C4", "scale_type": "major",
                                             "pitches": [61, 66, 70]}))
    snapped = [x["midi"] for x in j["snapped"]]
    check("snap_pitches 把音阶外音吸附进 C 大调",
          snapped == [62, 67, 71], str(snapped))
    r = call_tool("snap_pitches", {"root": "C4", "pitches": []})
    check("snap_pitches 空数组 -> isError", is_error(r), tool_text(r))


def test_suggest_scale():
    j = tool_json(call_tool("suggest_scale", {"pitches": [66, 68, 70, 71, 73, 75, 77]}))
    check("suggest_scale 返回 5 条候选", len(j["suggestions"]) == 5, len(j["suggestions"]))
    check("suggest_scale 含覆盖率",
          all("coverage" in s and "scale" in s for s in j["suggestions"]),
          str(j["suggestions"][0]))
    check("suggest_scale 按覆盖率降序",
          all(j["suggestions"][i]["coverage"] >= j["suggestions"][i + 1]["coverage"]
              for i in range(len(j["suggestions"]) - 1)),
          str([s["coverage"] for s in j["suggestions"]]))
    check("suggest_scale 命中 F# 大调",
          any(s["root"] == "F#" and s["scale"] == "major" and s["coverage"] == 100.0
              for s in j["suggestions"]), str(j["suggestions"]))


def test_validate_ok():
    j = tool_json(call_tool("validate_song", {"song": mini_song(), "strict": True}))
    check("validate_song 合法素材 ok", j["ok"] is True and not j["errors"], str(j))
    check("validate_song 统计正确", j["stats"]["note_count"] == 20
          and j["stats"]["bpm"] == 72, str(j["stats"]))


def test_validate_business_failure_is_not_tool_error():
    """校验不通过是「业务结果」，应正常返回 ok:false，而不是 isError。"""
    bad = mini_song()
    bad["tracks"][0]["notes"][0]["start_beat"] = 0.1      # 破坏 0.25 网格
    r = call_tool("validate_song", {"song": bad, "strict": True})
    check("校验失败不是 isError", not is_error(r), "不应标记为工具错误")
    j = tool_json(r)
    check("校验失败返回 ok:false 且带 errors",
          j["ok"] is False and len(j["errors"]) > 0, str(j)[:160])


def test_analyze_song():
    j = tool_json(call_tool("analyze_song", {"song": mini_song(),
                                             "chords": mini_chords(),
                                             "key_root": "D4", "key_type": "minor"}))
    check("analyze_song 含评分三栏",
          all(k in j for k in ("score", "technical_score", "musicality_score",
                               "structure_score")), list(j)[:12])
    check("analyze_song 含结论与建议",
          "passed" in j and isinstance(j.get("suggestions"), list), list(j)[:12])
    check("analyze_song 给了 chords 就检查强拍和弦音",
          "strong_beat_chord_tone_rate" in j["details"], list(j["details"])[:12])


def test_generate_midi():
    j = tool_json(call_tool("generate_midi", {"song": mini_song(), "bpm": 72}))
    blob = base64.b64decode(j["midi_base64"])
    check("generate_midi 返回可解码 base64", True, "")
    check("generate_midi 是合法 MIDI（MThd 头）", blob[:4] == b"MThd", blob[:8])
    check("generate_midi 元信息", j["note_count"] == 20 and j["bpm"] == 72
          and j["format"] == "MIDI Type-1", str({k: j.get(k) for k in
                                                 ("note_count", "bpm", "format")}))
    check("generate_midi 不回传服务端临时路径", "output" not in j, str(j.get("output")))


def test_roundtrip_generate_inspect():
    b64 = gen_midi_b64()
    j = tool_json(call_tool("inspect_midi", {"midi_base64": b64}))
    n = sum(len(t["notes"]) for t in j["tracks"])
    check("generate -> inspect 往返音符数一致", n == 20, n)
    check("generate -> inspect BPM 一致", j["bpm"] == 72.0, j["bpm"])


def test_decode_midi():
    b64 = gen_midi_b64()
    j = tool_json(call_tool("decode_midi", {"midi_base64": b64, "include_events": False}))
    check("decode_midi 紧凑模式无 events",
          all("events" not in t for t in j["tracks"]), "仍带 events")
    check("decode_midi 音符数一致", len(j["notes"]) == 20, len(j["notes"]))
    j2 = tool_json(call_tool("decode_midi", {"midi_base64": b64}))
    check("decode_midi 完整模式带 events",
          any(t.get("events") for t in j2["tracks"]), "无 events")


def test_report_midi():
    b64 = gen_midi_b64()
    j = tool_json(call_tool("report_midi", {"files": [
        {"name": "a.mid", "midi_base64": b64},
        {"name": "b.mid", "midi_base64": b64}], "format": "json"}))
    check("report_midi 处理两个文件", isinstance(j, list) and len(j) == 2, str(type(j)))
    check("report_midi 字段齐全",
          all(k in j[0] for k in ("file", "ok", "bpm", "style", "key_inference", "motifs")),
          list(j[0])[:12])
    r = call_tool("report_midi", {"files": []})
    check("report_midi 空 files -> isError", is_error(r), tool_text(r))
    r = call_tool("report_midi", {"files": [{"name": "x.mid"}]})
    check("report_midi 缺 midi_base64 -> isError", is_error(r), tool_text(r))


def test_report_midi_blocks_traversal():
    """文件名里的目录穿越应被 basename 抹平，不写到临时目录之外。"""
    b64 = gen_midi_b64()
    j = tool_json(call_tool("report_midi", {"files": [
        {"name": "../../../../evil.mid", "midi_base64": b64}], "format": "json"}))
    check("report_midi 目录穿越被抹平", j[0]["file"] == "evil.mid", j[0]["file"])


def test_compare_style():
    b64 = gen_midi_b64()
    j = tool_json(call_tool("compare_style", {"song": mini_song(),
                                              "reference_midi_base64": b64}))
    check("compare_style 返回相似度与判定",
          "similarity" in j and "verdict" in j, list(j)[:10])
    check("compare_style 含各维度", "dimensions" in j and len(j["dimensions"]) >= 4,
          str(list(j.get("dimensions", {}))))


# ────────────────────────── 一致性（包装层不得改变结果） ──────────────────────────

def _cli(script, args, stdin_obj=None):
    data = json.dumps(stdin_obj, ensure_ascii=False).encode("utf-8") if stdin_obj else None
    p = subprocess.run([sys.executable, script, *args], input=data, capture_output=True)
    return json.loads(p.stdout.decode("utf-8"))


def test_parity_with_cli():
    """同一个输入，MCP 与 CLI 的结果必须逐字段相同。"""
    midi_cli = os.path.normpath(os.path.join(ROOT, "..", "aria-midi", "aria_midi.py"))
    if not os.path.isfile(midi_cli):
        check("CLI 对比（跳过：找不到 aria-midi）", True, "")
        return

    song = mini_song()
    cli_v = _cli(midi_cli, ["validate", "--input", "-", "--strict"], song)
    mcp_v = tool_json(call_tool("validate_song", {"song": song, "strict": True}))
    check("validate：MCP 与 CLI 逐字段一致", cli_v == mcp_v, "结果不同")

    cli_a = _cli(midi_cli, ["analyze", "--input", "-", "--key-root", "D4"], song)
    mcp_a = tool_json(call_tool("analyze_song", {"song": song, "key_root": "D4"}))
    check("analyze：MCP 与 CLI 逐字段一致", cli_a == mcp_a,
          str({k: (cli_a.get(k), mcp_a.get(k)) for k in ("score", "passed")
               if cli_a.get(k) != mcp_a.get(k)}))


# ────────────────────────── 子进程 / stdio 入口 ──────────────────────────

def test_stdio_end_to_end():
    rc, outs, err = run_stdio([
        rpc("initialize", {"protocolVersion": aria_mcp.PROTOCOL_DEFAULT}, 1),
        rpc("notifications/initialized", notify=True),
        rpc("tools/list", {}, 2),
    ])
    check("stdio 子进程退出码 0", rc == 0, f"rc={rc} err={err[:200]}")
    check("stdio 返回 2 条响应（通知不响应）", len(outs) == 2, len(outs))
    check("stdio 响应 id 正确", [o["id"] for o in outs] == [1, 2], [o.get("id") for o in outs])


def test_stdio_tool_call():
    rc, outs, _ = run_stdio([
        rpc("initialize", {}, 1),
        rpc("tools/call", {"name": "scale_list",
                           "arguments": {"root": "A4", "scale_type": "minor"}}, 2),
    ])
    j = json.loads(outs[1]["result"]["content"][0]["text"])
    check("stdio 工具调用可用", rc == 0 and len(j["notes"]) == 7, str(j)[:120])
    check("stdio A 小调正确",
          [n["name"] for n in j["notes"]] == ["A4", "B4", "C5", "D5", "E5", "F5", "G5"],
          str([n["name"] for n in j["notes"]]))


def test_cli_flags():
    p = subprocess.run([sys.executable, SERVER, "--version"], capture_output=True, text=True)
    check("--version", p.returncode == 0 and aria_mcp.__version__ in p.stdout, p.stdout)
    p = subprocess.run([sys.executable, SERVER, "--selftest"], capture_output=True, text=True)
    check("--selftest 通过", p.returncode == 0 and "自检通过" in p.stdout, p.stdout)
    p = subprocess.run([sys.executable, SERVER, "--help"], capture_output=True, text=True)
    check("--help", p.returncode == 0 and "MCP" in p.stdout, p.stdout[:60])


def test_eof_exits_cleanly():
    """stdin 关闭后应正常退出（客户端断开连接时的行为）。"""
    p = subprocess.run([sys.executable, SERVER], input=b"", capture_output=True, timeout=60)
    check("空 stdin 正常退出", p.returncode == 0, f"rc={p.returncode}")


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
