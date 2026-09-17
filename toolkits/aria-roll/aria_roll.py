#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aria-roll — 零依赖钢琴卷帘渲染器（v1.0.0）

把 song.json 或任意 .mid 渲染成**自包含 HTML 卷帘**：双击即看（Canvas 卷帘 +
时间游标），按播放即听（Web Audio 现场合成，不需要 DAW、不需要插件、不需要音源）。

定位：MIDI 是谱不是声音，Aria 整条管线都是符号化的，人要看/听就只能开 DAW ——
本工具消掉这个往返。产物只有一个 HTML 文件，内地不依赖任何网络资源。

用法：
  python aria_roll.py roll --input song.json                 # → <歌名>.html
  python aria_roll.py roll --input x.mid --output x.html
  python aria_roll.py roll --input song.json --format svg    # 静态卷帘（Agent 可看）

退出码契约（与同包其他工具一致）：
  0 = 成功 / 1 = 数据错误 / 2 = 用法错误
"""

import argparse
import html
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ARIA_DECODE = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "aria-decode", "aria_decode.py"))

__version__ = "1.0.0"

# 轨道配色（按出现顺序循环）；GM 打击乐通道用中性灰
PALETTE = ["#4C8DFF", "#FF7A6B", "#22C55E", "#F5A524", "#A855F7",
           "#06B6D4", "#EC4899", "#84CC16"]
DRUM_COLOR = "#8B93A7"
DRUM_CHANNEL = 9


class DataError(Exception):
    pass


class UsageError(Exception):
    pass


# ══════════════════════════════════════════════════════════════
# 读取与归一化
# ══════════════════════════════════════════════════════════════

def _decode_midi(path):
    """调同级 aria-decode 把 .mid 解成 notes，再归一化成 song 形状。"""
    if not os.path.isfile(ARIA_DECODE):
        raise UsageError(f"找不到 aria-decode（应位于 {ARIA_DECODE}），无法读取 .mid")
    cmd = [sys.executable, ARIA_DECODE, "decode", "--no-events", "--output", "-"]
    cmd += ["--input", "-"] if path == "-" else ["--input", path]
    stdin = sys.stdin.buffer.read() if path == "-" else None
    p = subprocess.run(cmd, input=stdin, capture_output=True, timeout=120)
    if p.returncode != 0:
        raise DataError("aria-decode 解码失败：" +
                        p.stderr.decode("utf-8", errors="replace").strip()[:300])
    return json.loads(p.stdout.decode("utf-8"))


def load_song(path):
    """读取 song.json 或 .mid，统一成内部结构。

    返回 {title, bpm, time_signature, tracks:[{name,channel,program,notes}], total_beats}
    """
    is_mid = path != "-" and path.lower().endswith((".mid", ".midi"))
    if is_mid:
        return _from_decode(_decode_midi(path), path)
    try:
        text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    except OSError as e:
        raise UsageError(f"无法读取输入：{e}")
    try:
        song = json.loads(text)
    except json.JSONDecodeError as e:
        raise DataError(f"JSON 解析失败：{e}")
    return _from_song(song, path)


def _from_song(song, path):
    tracks = song.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        if isinstance(song.get("notes"), list):          # 旧版单轨格式
            tracks = [{"name": "Piano", "channel": 0, "program": 0,
                       "notes": song["notes"]}]
        else:
            raise DataError("song.json 里没有 tracks（或旧版 notes）")
    out = []
    for i, t in enumerate(tracks):
        notes = t.get("notes") or []
        if not notes:
            continue
        out.append({
            "name": str(t.get("name") or f"Track {i+1}"),
            "channel": int(t.get("channel") or 0),
            "program": t.get("program"),
            "notes": [{"pitch": int(n["pitch"]),
                       "start_beat": float(n.get("start_beat", 0)),
                       "duration": float(n.get("duration", 0.25)),
                       "velocity": int(n.get("velocity", 80))} for n in notes],
        })
    if not out:
        raise DataError("所有音轨都没有音符")
    title = song.get("name") or _stem(path)
    ts = song.get("time_signature") or {}
    return {
        "title": str(title),
        "bpm": float(song.get("bpm", 120)),
        "time_signature": "%s/%s" % (ts.get("numerator", 4), ts.get("denominator", 4)),
        "tracks": out,
        "total_beats": _total_beats(out),
    }


def _from_decode(dec, path):
    """把 aria-decode 的输出（tracks + 扁平 notes）归一化。"""
    if not dec.get("notes"):
        raise DataError("解码结果里没有音符")
    by_track = {}
    for n in dec["notes"]:
        by_track.setdefault(n.get("track", 0), []).append(n)
    out = []
    for t in dec.get("tracks", []):
        idx = t.get("index")
        if idx not in by_track:
            continue
        out.append({
            "name": str(t.get("name") or f"Track {idx}"),
            "channel": t.get("channel") if t.get("channel") is not None else 0,
            "program": t.get("program"),
            "notes": [{"pitch": int(n["pitch"]),
                       "start_beat": float(n.get("start_beat", 0)),
                       "duration": float(n.get("duration", 0.25)),
                       "velocity": int(n.get("velocity", 80))} for n in by_track[idx]],
        })
    if not out:                                  # 兜底：按 channel 分组
        by_ch = {}
        for n in dec["notes"]:
            by_ch.setdefault(n.get("channel", 0), []).append(n)
        for ch, ns in sorted(by_ch.items()):
            out.append({"name": f"Channel {ch}", "channel": ch, "program": None,
                        "notes": [{"pitch": int(n["pitch"]),
                                   "start_beat": float(n.get("start_beat", 0)),
                                   "duration": float(n.get("duration", 0.25)),
                                   "velocity": int(n.get("velocity", 80))} for n in ns]})
    return {
        "title": _stem(path) if path != "-" else "MIDI",
        "bpm": float(dec.get("global", {}).get("bpm") or 120),
        "time_signature": dec.get("global", {}).get("time_signature") or "4/4",
        "tracks": out,
        "total_beats": _total_beats(out),
    }


def _stem(path):
    if not path or path == "-":
        return "roll"
    return os.path.splitext(os.path.basename(path))[0]


def _total_beats(tracks):
    end = 0.0
    for t in tracks:
        for n in t["notes"]:
            end = max(end, n["start_beat"] + n["duration"])
    return max(end, 1.0)


def _pitch_range(song):
    ps = [n["pitch"] for t in song["tracks"] for n in t["notes"]]
    return min(ps), max(ps)


def _colorize(song):
    """给每条轨配色，并打包成前端用的精简结构。"""
    out = []
    ci = 0
    for t in song["tracks"]:
        if t["channel"] == DRUM_CHANNEL:
            color = DRUM_COLOR
        else:
            color = PALETTE[ci % len(PALETTE)]
            ci += 1
        out.append({"name": t["name"], "channel": t["channel"],
                    "program": t["program"], "color": color, "notes": t["notes"]})
    return out


def _pack(song):
    """把音符压成整数四元组 [pitch, start*4, dur*4, velocity]。

    网格是 0.25 拍，所以 start/duration 乘 4 必为整数 —— 用位置数组代替
    带键名的对象，内嵌体积约为原来的 1/4（2142 音符的文件 144KB → ~45KB）。
    """
    out = []
    for t in _colorize(song):
        out.append({
            "name": t["name"], "channel": t["channel"], "program": t["program"],
            "color": t["color"],
            "n": [[int(n["pitch"]), int(round(n["start_beat"] * 4)),
                   int(round(n["duration"] * 4)), int(n["velocity"])]
                  for n in t["notes"]],
        })
    return out


def _js_json(obj):
    """安全嵌入 <script>：转义 </ 防止提前闭合，并保证非 ASCII 可读。"""
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            .replace("</", "<\\/"))


# ══════════════════════════════════════════════════════════════
# HTML 渲染
# ══════════════════════════════════════════════════════════════

_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — 钢琴卷帘</title>
<style>
  :root{--bg:#0f1115;--panel:#171a21;--line:#262b36;--fg:#e6e9ef;--dim:#8b93a7}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:#e6e9ef;font:14px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif}
  header{padding:14px 18px;background:var(--panel);border-bottom:1px solid #262b36;position:sticky;top:0;z-index:5}
  h1{margin:0 0 4px;font-size:17px;font-weight:600}
  .meta{color:#8b93a7;font-size:12.5px}
  .row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:10px}
  button{background:#242a35;color:#e6e9ef;border:1px solid #333b4a;border-radius:7px;padding:7px 15px;font-size:13.5px;cursor:pointer}
  button:hover{background:#2c333f}
  button.on{background:#2f6df6;border-color:#2f6df6}
  label{color:#8b93a7;font-size:12.5px;display:flex;align-items:center;gap:7px}
  input[type=range]{width:130px;accent-color:#2f6df6}
  .legend{display:flex;gap:13px;flex-wrap:wrap;font-size:12.5px;color:#b9c0cd;margin-top:9px}
  .legend span{display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
  .legend i{width:11px;height:11px;border-radius:3px;display:inline-block}
  .legend span.off{opacity:.32;text-decoration:line-through}
  #wrap{overflow:auto;max-height:calc(100vh - 178px);padding:12px 0 18px}
  canvas{display:block}
  #pos{color:#8b93a7;font-variant-numeric:tabular-nums;font-size:12.5px}
  .hint{color:#6b7285;font-size:12px;margin-top:8px}
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="meta">__META__</div>
  <div class="row">
    <button id="play">▶ 播放</button>
    <button id="stop">■ 停止</button>
    <button id="loop" class="on">↻ 循环</button>
    <label>缩放 <input id="zoom" type="range" min="6" max="90" value="__ZOOM__"></label>
    <span id="pos">0.0 拍 · 0.0s</span>
  </div>
  <div class="legend" id="legend"></div>
  <div class="hint" id="hint">空格播放/停止 · 点击图例可独奏该轨 · 声音由浏览器现场合成（Web Audio），无需 DAW 与音源</div>
</header>
<div id="wrap"><canvas id="roll"></canvas></div>
<script>
const SONG = __SONG__;
// 解包：音符以整数四元组 [pitch, start*4, dur*4, vel] 内嵌，这里还原成具名字段
for (const t of SONG.tracks)
  t.notes = t.n.map(a => ({pitch:a[0], start_beat:a[1]/4, duration:a[2]/4, velocity:a[3]}));
const ROW = 9, KEYS = 40, HEAD = 60;   // 每半音行高 / 左侧琴键宽 / 顶部标尺高
const cv = document.getElementById('roll'), cx = cv.getContext('2d');
const wrap = document.getElementById('wrap');
let ppb = __ZOOM__, lo = SONG.lo, hi = SONG.hi, solo = null, manualZoom = false;
const MIN_PPB = 5;                     // 自适应时的下限，再小音符就糊了
const rows = hi - lo + 1;
const px = n => n.start_beat * ppb;
const py = p => HEAD + (hi - p) * ROW;
const cols = t => t.color;

function drawGrid(){
  const W = Math.max(wrap.clientWidth - 24, SONG.total * ppb + KEYS + 20), H = HEAD + rows * ROW + 8;
  const dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + 'px'; cv.style.height = H + 'px';
  cx.setTransform(dpr,0,0,dpr,0,0);
  cx.fillStyle = '#0f1115'; cx.fillRect(0,0,W,H);

  // 黑键行底色（方便定位）
  for (let p = lo; p <= hi; p++){
    if ([1,3,6,8,10].includes(((p % 12) + 12) % 12)){
      cx.fillStyle = '#141821'; cx.fillRect(KEYS, py(p), W - KEYS, ROW);
    }
  }
  // 横向半音线
  cx.strokeStyle = '#1b202a'; cx.lineWidth = 1;
  for (let p = lo; p <= hi + 1; p++){
    cx.beginPath(); cx.moveTo(KEYS, py(p) + .5); cx.lineTo(W, py(p) + .5); cx.stroke();
  }
  // 纵向：拍线 / 小节线（按拍号）
  const beatsPerBar = SONG.beats_per_bar;
  for (let b = 0; b <= Math.ceil(SONG.total); b++){
    const isBar = b % beatsPerBar === 0;
    cx.strokeStyle = isBar ? '#39414f' : '#1f2530';
    cx.beginPath(); cx.moveTo(KEYS + b * ppb + .5, HEAD); cx.lineTo(KEYS + b * ppb + .5, HEAD + rows * ROW); cx.stroke();
    if (isBar){
      cx.fillStyle = '#6b7285'; cx.font = '10px ui-monospace,monospace';
      cx.fillText(String(b / beatsPerBar + 1), KEYS + b * ppb + 4, HEAD - 13);
    }
  }
  // 左侧琴键
  cx.fillStyle = '#171a21'; cx.fillRect(0, HEAD, KEYS, rows * ROW);
  for (let p = lo; p <= hi; p++){
    const black = [1,3,6,8,10].includes(((p % 12) + 12) % 12);
    cx.fillStyle = black ? '#232833' : '#e8ebf1';
    cx.fillRect(0, py(p), black ? KEYS * 0.62 : KEYS, ROW - 1);
    if (((p % 12) + 12) % 12 === 0){
      cx.fillStyle = '#6b7285'; cx.font = '9.5px ui-monospace,monospace';
      cx.fillText('C' + (Math.floor(p / 12) - 1), KEYS * 0.66 + 2, py(p) + ROW - 1);
    }
  }
  // 顶部标尺
  cx.fillStyle = '#171a21'; cx.fillRect(0, 0, W, HEAD);
  cx.strokeStyle = '#262b36'; cx.beginPath(); cx.moveTo(0, HEAD + .5); cx.lineTo(W, HEAD + .5); cx.stroke();
}
function drawNotes(){
  for (let ti = 0; ti < SONG.tracks.length; ti++){
    const t = SONG.tracks[ti];
    if (solo !== null && solo !== ti) continue;
    for (const n of t.notes){
      const x = KEYS + px(n), y = py(n.pitch), w = Math.max(1.5, n.duration * ppb - 1);
      cx.globalAlpha = 0.42 + 0.58 * (n.velocity / 127);
      cx.fillStyle = cols(t);
      cx.fillRect(x, y + 1, w, ROW - 2);
    }
  }
  cx.globalAlpha = 1;
}
function drawPlayhead(beat){
  if (beat == null) return;
  const x = KEYS + beat * ppb;
  cx.strokeStyle = '#ffd84d'; cx.lineWidth = 1.5;
  cx.beginPath(); cx.moveTo(x, HEAD); cx.lineTo(x, HEAD + rows * ROW); cx.stroke();
}
function redraw(beat){ drawGrid(); drawNotes(); drawPlayhead(beat); }
function fitWidth(){
  // 默认铺满可视宽度，让整首一览无余；低于下限则保持缩放并横向滚动。
  // 用户动过缩放滑块后不再自动改（manualZoom）。
  if (manualZoom) return;
  const avail = wrap.clientWidth - KEYS - 44;
  if (avail <= 0) return;
  ppb = Math.max(MIN_PPB, avail / SONG.total);
  document.getElementById('zoom').value = Math.min(90, Math.max(6, Math.round(ppb)));
}
// ── 图例 ──
const legend = document.getElementById('legend');
SONG.tracks.forEach((t, i) => {
  const s = document.createElement('span');
  s.innerHTML = '<i style="background:' + t.color + '"></i>' + t.name + ' · ' + t.notes.length;
  s.title = '点击独奏 / 再点取消';
  s.onclick = () => { solo = (solo === i) ? null : i;
    [...legend.children].forEach((c, j) => c.classList.toggle('off', solo !== null && solo !== j));
    redraw(lastBeat); };
  legend.appendChild(s);
});

// ── Web Audio 现场合成 ──
let actx = null, sched = [], t0 = 0, t0w = 0, playing = false, raf = 0, lastBeat = null;
const SPB = () => 60 / SONG.bpm;
function voiceFor(program, channel){
  if (channel === 9) return {kind:'drum'};
  if (program == null) program = 0;
  if (program < 8)   return {kind:'piano',  type:'triangle', a:0.004, d:0.5,  s:0.05, r:0.28, g:1.0};
  if (program < 16)  return {kind:'bell',   type:'sine',     a:0.003, d:0.7,  s:0.02, r:0.35, g:0.9};
  if (program < 24)  return {kind:'organ',  type:'square',   a:0.02,  d:0.1,  s:0.75, r:0.12, g:0.5};
  if (program < 32)  return {kind:'guitar', type:'triangle', a:0.004, d:0.45, s:0.06, r:0.25, g:0.95};
  if (program < 40)  return {kind:'bass',   type:'sine',     a:0.008, d:0.35, s:0.35, r:0.16, g:1.15};
  if (program < 48)  return {kind:'strings',type:'sawtooth', a:0.11,  d:0.2,  s:0.7,  r:0.35, g:0.34};
  if (program < 56)  return {kind:'ens',    type:'sawtooth', a:0.07,  d:0.2,  s:0.65, r:0.3,  g:0.36};
  if (program < 80)  return {kind:'reed',   type:'square',   a:0.03,  d:0.2,  s:0.6,  r:0.2,  g:0.42};
  if (program < 88)  return {kind:'lead',   type:'sawtooth', a:0.012, d:0.12, s:0.72, r:0.14, g:0.42};
  if (program < 96)  return {kind:'pad',    type:'sine',     a:0.14,  d:0.3,  s:0.7,  r:0.5,  g:0.5};
  return {kind:'pluck', type:'triangle', a:0.005, d:0.35, s:0.04, r:0.2, g:0.9};
}
function noiseBuf(ctx){
  if (ctx._nb) return ctx._nb;
  const b = ctx.createBuffer(1, ctx.sampleRate * 0.2, ctx.sampleRate), d = b.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return ctx._nb = b;
}
function schedule(track, n, when){
  const v = voiceFor(track.program, track.channel);
  const dur = Math.max(0.05, n.duration * SPB());
  const amp = (n.velocity / 127) * (v.g || 1) * 0.28;
  if (v.kind === 'drum'){
    const src = actx.createBufferSource(); src.buffer = noiseBuf(actx);
    const hp = actx.createBiquadFilter(); hp.type = (n.pitch < 40 ? 'lowpass' : 'highpass');
    hp.frequency.value = n.pitch < 40 ? 120 : 4000;
    const g = actx.createGain();
    g.gain.setValueAtTime(amp * 1.1, when);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.13);
    src.connect(hp).connect(g).connect(actx.destination); src.start(when); src.stop(when + 0.2);
    sched.push(src); return;
  }
  const o = actx.createOscillator(); o.type = v.type;
  o.frequency.value = 440 * Math.pow(2, (n.pitch - 69) / 12);
  const s = Math.max(dur, 0.08), rel = v.r;
  const g = actx.createGain();
  g.gain.setValueAtTime(0.0001, when);
  g.gain.linearRampToValueAtTime(amp, when + v.a);
  g.gain.exponentialRampToValueAtTime(Math.max(amp * v.s, 0.0001), when + v.a + v.d);
  g.gain.setValueAtTime(Math.max(amp * v.s, 0.0001), when + s);
  g.gain.exponentialRampToValueAtTime(0.0001, when + s + rel);
  o.connect(g).connect(actx.destination);
  o.start(when); o.stop(when + s + rel + 0.05);
  sched.push(o);
}
async function play(){
  if (playing) return;
  actx = actx || new (window.AudioContext || window.webkitAudioContext)();
  if (actx.state !== 'running'){ try{ await actx.resume(); }catch(e){} }
  const audible = actx.state === 'running';
  // 音频调度用 AudioContext 时钟；播放头走 wall clock。
  // 两者解耦：即使自动播放策略把 AudioContext 挂起（currentTime 冻结），
  // 卷帘依然能走，不会出现负数的播放头。
  t0 = actx.currentTime + 0.12;
  t0w = performance.now() + 120;
  playing = true;
  document.getElementById('play').textContent = '⏸ 暂停';
  if (!audible) document.getElementById('hint').textContent =
    '⚠ 浏览器阻止了自动播放，当前为静音预览（再点一次播放通常即可出声）';
  if (audible) for (let ti = 0; ti < SONG.tracks.length; ti++){
    if (solo !== null && solo !== ti) continue;
    const t = SONG.tracks[ti];
    for (const n of t.notes) schedule(t, n, t0 + n.start_beat * SPB());
  }
  tick();
}
function stopAll(){
  for (const s of sched){ try{ s.stop(); }catch(e){} }
  sched = []; playing = false; lastBeat = null;
  document.getElementById('play').textContent = '▶ 播放';
  document.getElementById('pos').textContent = '0.0 拍 · 0.0s';
  cancelAnimationFrame(raf); redraw(null);
}
function tick(){
  if (!playing) return;
  const el = Math.max(0, (performance.now() - t0w) / 1000);
  let beat = el / SPB();
  if (beat >= SONG.total){
    if (document.getElementById('loop').classList.contains('on')){ stopAll(); play(); return; }
    stopAll(); return;
  }
  lastBeat = beat;
  document.getElementById('pos').textContent =
    beat.toFixed(1) + ' 拍 · ' + el.toFixed(1) + 's';
  redraw(beat);
  const x = KEYS + beat * ppb;
  if (x < wrap.scrollLeft + KEYS + 40 || x > wrap.scrollLeft + wrap.clientWidth - 80)
    wrap.scrollLeft = Math.max(0, x - wrap.clientWidth * 0.4);
  raf = requestAnimationFrame(tick);
}
// 诊断钩子：便于在控制台确认音频状态（排「为什么没声音」时有用）
window.__aria = () => ({state: actx && actx.state, sched: sched.length, playing,
                        beat: lastBeat, ppb, manualZoom});
document.getElementById('play').onclick = () => playing ? stopAll() : play();
document.getElementById('stop').onclick = stopAll;
document.getElementById('loop').onclick = e => e.target.classList.toggle('on');
document.getElementById('zoom').oninput = e => { manualZoom = true; ppb = +e.target.value; redraw(lastBeat); };
addEventListener('keydown', e => {
  if (e.code === 'Space'){ e.preventDefault(); playing ? stopAll() : play(); }
});
addEventListener('resize', () => { fitWidth(); redraw(lastBeat); });
fitWidth(); redraw(null);
</script>
</body>
</html>
"""


def render_html(song, zoom=16):
    lo, hi = _pitch_range(song)
    body = {
        "title": song["title"], "bpm": song["bpm"],
        "beats_per_bar": int(song["time_signature"].split("/")[0].split(".")[0] or 4),
        "total": round(song["total_beats"], 3), "lo": lo, "hi": hi,
        "tracks": _pack(song),
    }
    notes = sum(len(t["notes"]) for t in song["tracks"])
    bpb = max(1, body["beats_per_bar"])
    bars = int(song["total_beats"] // bpb) + (1 if song["total_beats"] % bpb else 0)
    meta = "钢琴卷帘 · %g BPM · %s · %d 小节 · %d 音符 · %d 轨" % (
        song["bpm"], song["time_signature"], bars, notes, len(song["tracks"]))
    return (_HTML
            .replace("__TITLE__", html.escape(song["title"])).replace("__META__", meta)
            .replace("__SONG__", _js_json(body)).replace("__ZOOM__", str(int(zoom))))


# ══════════════════════════════════════════════════════════════
# SVG 渲染（静态，适合喂给可读图的 Agent 或嵌文档）
# ══════════════════════════════════════════════════════════════

def render_svg(song, row=6, ppb=14, keys=34, head=26, max_width=6000):
    lo, hi = _pitch_range(song)
    rows = hi - lo + 1
    beats = int(song["total_beats"])
    bpb = int(song["time_signature"].split("/")[0]) or 4
    width = min(max_width, keys + beats * ppb + 16)
    height = head + rows * row + 26
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d" font-family="ui-monospace,Menlo,Consolas,monospace">'
         % (width, height, width, height)]
    s.append('<rect width="100%%" height="100%%" fill="#0f1115"/>')
    y = lambda p: head + (hi - p) * row
    x = lambda b: keys + b * ppb
    for p in range(lo, hi + 1):                      # 黑键行
        if ((p % 12) + 12) % 12 in (1, 3, 6, 8, 10):
            s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#141821"/>'
                     % (keys, y(p), width - keys - 8, row))
    for b in range(beats + 1):                       # 拍线 / 小节线
        is_bar = b % bpb == 0
        s.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1"/>'
                 % (x(b), head, x(b), head + rows * row, "#39414f" if is_bar else "#1f2530"))
        if is_bar:
            s.append('<text x="%d" y="%d" fill="#6b7285" font-size="9">%d</text>'
                     % (x(b) + 3, head - 8, b // bpb + 1))
    for ti, t in enumerate(_colorize(song)):         # 音符：按轨 + 力度档分组
        buckets = {}
        for n in t["notes"]:
            b = 0 if n["velocity"] < 70 else (1 if n["velocity"] < 100 else 2)
            buckets.setdefault(b, []).append(n)
        for b in sorted(buckets):
            s.append('<g fill="%s" opacity="%s">' % (t["color"], ("0.5", "0.75", "1")[b]))
            for n in buckets[b]:
                s.append('<rect x="%g" y="%g" width="%g" height="%d"/>'
                         % (x(n["start_beat"]), y(n["pitch"]) + 1,
                            max(1.5, n["duration"] * ppb - 1), row - 2))
            s.append('</g>')
    for ti, t in enumerate(_colorize(song)):         # 图例
        lx = keys + 4 + ti * 150
        s.append('<rect x="%d" y="%d" width="9" height="9" rx="2" fill="%s"/>'
                 % (lx, height - 17, t["color"]))
        s.append('<text x="%d" y="%d" fill="#b9c0cd" font-size="10">%s · %d</text>'
                 % (lx + 13, height - 9, html.escape(t["name"]), len(t["notes"])))
    s.append('<text x="8" y="%d" fill="#e6e9ef" font-size="11">%s</text>'
             % (14, html.escape(song["title"])))
    s.append('<text x="%d" y="14" fill="#8b93a7" font-size="10" text-anchor="end">%s · %g BPM · %s</text>'
             % (width - 8, song["time_signature"], song["bpm"],
                sum(len(t["notes"]) for t in song["tracks"]) and
                "%d 音符" % sum(len(t["notes"]) for t in song["tracks"])))
    s.append('</svg>')
    return "".join(s)


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def _default_output(input_path, song, fmt):
    if not input_path or input_path == "-":
        return "-"
    d = os.path.dirname(os.path.abspath(input_path))
    name = song["title"] or "roll"
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    name = name.strip().strip(". ") or "roll"
    return os.path.join(d, name + "." + fmt)


def cmd_roll(args):
    song = load_song(args.input)
    if args.title:
        song["title"] = args.title
    fmt = "svg" if args.format == "svg" else "html"
    text = render_svg(song) if fmt == "svg" else render_html(song, args.zoom)
    out = args.output or _default_output(args.input, song, fmt)
    if out and out != "-":
        try:
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            raise UsageError(f"无法写入输出文件：{e}")
        print(json.dumps({
            "ok": True, "output": out, "format": fmt,
            "title": song["title"], "bpm": song["bpm"],
            "tracks": [{"name": t["name"], "notes": len(t["notes"])} for t in song["tracks"]],
            "note_count": sum(len(t["notes"]) for t in song["tracks"]),
            "total_beats": round(song["total_beats"], 3),
            "bytes": len(text.encode("utf-8")),
        }, ensure_ascii=False))
    else:
        sys.stdout.write(text)
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="aria-roll",
        description="Aria 技能包 — 钢琴卷帘渲染（song.json / .mid → 自包含 HTML 或 SVG）")
    p.add_argument("--version", action="version", version=f"aria-roll {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<子命令>")

    r = sub.add_parser("roll", help="渲染钢琴卷帘")
    r.add_argument("--input", required=True, help="song.json 或 .mid 路径，'-' 读 stdin（JSON）")
    r.add_argument("--output", help="输出路径；省略时按歌名派生 <歌名>.html/.svg 到输入同目录")
    r.add_argument("--format", choices=["html", "svg"], default="html",
                   help="html（自包含可播放，默认）/ svg（静态，Agent 可读图）")
    r.add_argument("--title", help="覆盖标题")
    r.add_argument("--zoom", type=int, default=16, help="HTML 初始像素/拍（6-90，默认 16）")
    r.set_defaults(handler=cmd_roll)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args(argv)
    if not getattr(args, "handler", None):
        build_parser().print_help()
        return 2
    try:
        return args.handler(args)
    except UsageError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (DataError, OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
