"""Build the animated profile SVGs (light + dark) used by README.md.

Fonts are subset per SVG and embedded as WOFF2, because GitHub serves README
images as <img>, which cannot load external fonts. Colors and the body font
(LXGW Bright) follow the blog at dogogod.github.io.

    python assets/readme/src/build.py [FONT_DIR]

FONT_DIR must contain:
    from https://github.com/google/fonts
        InstrumentSerif-Regular.ttf, InstrumentSerif-Italic.ttf, JetBrainsMono[wght].ttf,
        MaShanZheng-Regular.ttf
    from the npm package @chinese-fonts/lxgwwenkaibright
        LXGWBright-Medium/  (the dist folder: result.css + chunked woff2 files)
"""

import base64
import io
import math
import random
import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

OUT = Path(__file__).resolve().parent.parent
FONT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "fonts"

# ---------------------------------------------------------------- palettes (from the blog's variables.css)

PALETTES = {
    "light": dict(
        bg="#FCFBF8", panel="#FFFFFF", card="#F5F2EC", ink="#211F1C", muted="#6D675F",
        faint="#ABA49A", line="#E8E4DC", accent="#CC7A5C", accent2="#F0D3C6",
        lang="#CC7A5C", ai="#4F63A8", robo="#5F7F3E", craft="#B8892E",
        paper=("#EDE5D6", "#DCCDB3", "#C4AE8C"), glow="#F0A65A",
        cover="#ECE7DE", cell="#FCFBF8", n1="#4F63A8", n2="#5F7F3E", n3="#B9583A",
    ),
    "dark": dict(
        bg="#171512", panel="#1D1B17", card="#1E1C18", ink="#EEE9DF", muted="#AAA399",
        faint="#5F5A52", line="#3C3831", accent="#D88C6E", accent2="#5A3A2E",
        lang="#D88C6E", ai="#93A3E6", robo="#A3C47A", craft="#E0B866",
        paper=("#2B2721", "#3A332A", "#4C4134"), glow="#F2B66D",
        cover="#2C2925", cell="#171512", n1="#93A3E6", n2="#A3C47A", n3="#E08A6A",
    ),
}

# ---------------------------------------------------------------- fonts

FONT_SPECS = {
    "serif": ("InstrumentSerif-Regular.ttf", None, "Georgia, serif"),
    "serif-i": ("InstrumentSerif-Italic.ttf", None, "Georgia, serif"),
    "body": ("LXGWBright-Medium", None, "'LXGW WenKai', 'Songti SC', serif"),  # chunked, see chunk_of()
    "mono": ("JetBrainsMono[wght].ttf", {"wght": 500}, "ui-monospace, Menlo, monospace"),
    "mono-b": ("JetBrainsMono[wght].ttf", {"wght": 760}, "ui-monospace, Menlo, monospace"),
    "brush": ("MaShanZheng-Regular.ttf", None, "'Kaiti SC', KaiTi, serif"),
}
CHUNKED = {"body"}
_fonts = {}


def _load(key, axes=None):
    if (key, axes) not in _fonts:
        f = TTFont(FONT_DIR / key)
        if axes:
            f = instancer.instantiateVariableFont(f, dict(axes))
        buf = io.BytesIO()
        f.flavor = None
        f.save(buf)
        _fonts[key, axes] = buf.getvalue()
    return _fonts[key, axes]


_ranges = {}


def chunk_of(cls, ch):
    """cn-font-split dist: map a character to the chunk file that holds it."""
    folder = FONT_SPECS[cls][0]
    if folder not in _ranges:
        css = (FONT_DIR / folder / "result.css").read_text(encoding="utf-8")
        table = []
        for url, ur in re.findall(r'url\("\./([^"]+)"\).*?unicode-range:([^;}]+)', css):
            for part in ur.split(","):
                lo, _, hi = part.strip()[2:].partition("-")
                table.append((int(lo, 16), int(hi or lo, 16), f"{folder}/{url}"))
        _ranges[folder] = table
    o = ord(ch)
    return next((f for lo, hi, f in _ranges[folder] if lo <= o <= hi), None)


def font_key(cls, ch=None):
    name, axes, _ = FONT_SPECS[cls]
    if cls in CHUNKED:
        return chunk_of(cls, ch or "a"), None
    return name, tuple(sorted(axes.items())) if axes else None


_metrics = {}


def measure(cls, text, size, spacing=0.0):
    w = 0
    for c in text:
        key, axes = font_key(cls, c)
        mk = (key, axes)
        if mk not in _metrics:
            f = TTFont(io.BytesIO(_load(key, axes)))
            _metrics[mk] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
        cmap, hmtx, upm = _metrics[mk]
        w += hmtx[cmap.get(ord(c), ".notdef")][0] * size / upm
    return w + spacing * len(text)


def faces(cls, chars):
    """[(base64 woff2, unicode-range or None)] covering `chars`."""
    groups = {}
    for c in chars:
        if c.isspace():
            continue
        groups.setdefault(font_key(cls, c), set()).add(c)
    out = []
    for (key, axes), cs in groups.items():
        f = TTFont(io.BytesIO(_load(key, axes)))
        opts = subset.Options()
        opts.layout_features = ["kern", "liga", "calt"]
        opts.name_IDs = []
        s = subset.Subsetter(opts)
        s.populate(text="".join(sorted(cs)) + " ")
        s.subset(f)
        buf = io.BytesIO()
        f.flavor = "woff2"
        f.save(buf)
        rng = ",".join(f"U+{ord(c):X}" for c in sorted(cs | {" "})) if len(groups) > 1 else None
        out.append((base64.b64encode(buf.getvalue()).decode(), rng))
    return out


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- svg builder

BASE_CSS = """
.rise{animation:rise .9s cubic-bezier(.2,.7,.2,1) both}
.fade{animation:fade 1.2s ease both}
.draw{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.6s cubic-bezier(.6,0,.2,1) both}
.spin{transform-box:fill-box;transform-origin:center;animation:spin 40s linear infinite}
.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.8s ease-in-out infinite}
.blink{animation:blink 1.6s steps(1) infinite}
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{transform:scale(1);opacity:.9}50%{transform:scale(1.35);opacity:.35}}
@keyframes blink{50%{opacity:0}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;stroke-dashoffset:0!important}}
"""


class Svg:
    def __init__(self, w, h, title, p):
        self.w, self.h, self.title, self.p = w, h, title, p
        self.body, self.defs, self.css = [], [], [BASE_CSS]
        self.chars = {}

    def add(self, s):
        self.body.append(s)

    def text(self, x, y, cls, s, fill=None, size=16, anchor=None, ls=None, style="", add=""):
        self.chars.setdefault(cls, set()).update(s)
        attrs = f'x="{x:.1f}" y="{y:.1f}" class="{(cls + " " + add).strip()}" font-size="{size}" fill="{fill or self.p["ink"]}"'
        if anchor:
            attrs += f' text-anchor="{anchor}"'
        if ls is not None:
            attrs += f' letter-spacing="{ls}"'
        if style:
            attrs += f' style="{style}"'
        return f"<text {attrs}>{esc(s)}</text>"

    def t(self, *a, **k):
        self.add(self.text(*a, **k))

    def render(self):
        css = []
        for cls in sorted(self.chars):
            fam = f"g-{cls}"
            for b64, rng in faces(cls, self.chars[cls]):
                css.append(f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{b64}) format('woff2')"
                           + (f";unicode-range:{rng}" if rng else "") + "}")
            css.append(f".{cls}{{font-family:'{fam}',{FONT_SPECS[cls][2]}}}")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.title)}">'
            f"<title>{esc(self.title)}</title>"
            f"<style>{''.join(css)}{''.join(self.css)}</style>"
            f"<defs>{''.join(self.defs)}</defs>{''.join(self.body)}</svg>"
        )


def save(name, build):
    for theme, p in PALETTES.items():
        svg = build(p)
        path = OUT / f"{name}-{theme}.svg"
        path.write_text(svg.render(), encoding="utf-8")
        print(f"{path.name:28s} {path.stat().st_size / 1024:6.1f} KB")


def ellipse_path(rx, ry):
    return f"M{-rx},0a{rx},{ry} 0 1,0 {2 * rx},0a{rx},{ry} 0 1,0 {-2 * rx},0"


# ---------------------------------------------------------------- hero

PHRASES = [
    "agents that remember.",
    "robots that find their way.",
    "films out of paper & light.",
    "a notebook for memories.",
    "games in the terminal.",
]


def hero(p):
    s = Svg(1200, 640, "Guztchian — Software Engineering at SJTU. O ever youthful, O ever weeping.", p)
    s.defs.append(
        f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" fill="{p["line"]}"/></pattern>'
        '<linearGradient id="fadeR" x1="0" x2="1"><stop offset=".35" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>'
        '<mask id="dotMask"><rect width="1200" height="640" fill="url(#fadeR)"/></mask>'
    )
    s.css.append(
        ".ch{animation:rise 1s cubic-bezier(.2,.7,.2,1) both}"
        ".ph{opacity:0;animation:cycle 15s ease-in-out infinite both}.ph0{opacity:1}"
        "@keyframes cycle{0%{opacity:0;transform:translateY(14px)}2.5%,17%{opacity:1;transform:none}20%,100%{opacity:0;transform:translateY(-12px)}}"
    )
    s.add(f'<rect x=".5" y=".5" width="1199" height="639" rx="28" fill="{p["bg"]}" stroke="{p["line"]}"/>')
    s.add('<rect width="1200" height="640" rx="28" fill="url(#dots)" mask="url(#dotMask)"/>')

    # meta line
    s.add('<g class="fade">')
    s.t(64, 76, "mono", "31.02°N  121.43°E  ·  SHANGHAI", p["muted"], 14, ls=2.4)
    s.add(f'<circle class="blink" cx="{1136 - measure("mono", "SOFTWARE ENGINEERING @ SJTU", 14, 2.4) - 14}" cy="71" r="4" fill="{p["accent"]}"/>')
    s.t(1136, 76, "mono", "SOFTWARE ENGINEERING @ SJTU", p["muted"], 14, anchor="end", ls=2.4)
    s.add("</g>")

    # name, letter by letter
    x, size = 58, 172
    for i, c in enumerate("Guztchian"):
        s.t(x, 262, "serif", c, size=size, add="ch", style=f"animation-delay:{.15 + i * .055:.3f}s")
        x += measure("serif", c, size) - 3
    s.t(x + 2, 262, "serif-i", ".", p["accent"], size, add="ch", style="animation-delay:.7s")

    # rotating phrase
    s.t(64, 352, "serif", "I build", size=48, add="fade", style="animation-delay:.9s")
    px = 64 + measure("serif", "I build ", 48)
    assert max(px + measure("serif-i", ph, 48) for ph in PHRASES) < 770, "phrase runs into the orrery legend"
    for i, ph in enumerate(PHRASES):
        s.t(px, 352, "serif-i", ph, p["accent"], 48, add=f"ph ph{i}", style=f"animation-delay:{1.2 + i * 3}s")

    # about, in the blog's own words
    lines = [
        ("Software Engineering student at Shanghai Jiao Tong University.", p["ink"]),
        ("Wandering between technology and literature — describing the world with math,", p["muted"]),
        ("reshaping it with code, and occasionally trying to understand it with words.", p["muted"]),
    ]
    for i, (ln, col) in enumerate(lines):
        s.t(64, 424 + i * 34, "body", ln, col, 21, add="rise", style=f"animation-delay:{1 + i * .12:.2f}s")

    # orrery: SEE / THINK / MOVE
    cx, cy, tilt = 952, 232, -14
    orbits = [(76, 31, 9, p["ai"], "SEE", "vision"), (124, 51, 16, p["accent"], "THINK", "agents"), (170, 70, 27, p["robo"], "MOVE", "robotics")]
    s.add(f'<g transform="translate({cx} {cy}) rotate({tilt})">')
    for i, (rx, ry, *_) in enumerate(orbits):
        s.add(f'<path class="draw" pathLength="1" d="{ellipse_path(rx, ry)}" fill="none" stroke="{p["faint"]}" stroke-width="1.2" style="animation-delay:{.3 + i * .25}s"/>')
    for i, (rx, ry, dur, col, *_) in enumerate(orbits):
        d = ellipse_path(rx, ry)
        s.add(
            f'<circle r="{6 + i}" fill="{col}"><animateMotion dur="{dur}s" begin="-{i * 4 + 2}s" repeatCount="indefinite" path="{d}"/></circle>'
            f'<circle r="{14 + i * 2}" fill="{col}" opacity=".14"><animateMotion dur="{dur}s" begin="-{i * 4 + 2}s" repeatCount="indefinite" path="{d}"/></circle>'
        )
    s.add(f'<circle class="pulse" r="20" fill="{p["accent2"]}"/><circle r="10" fill="{p["accent"]}"/></g>')

    # legend: SEE vision -> THINK agents -> MOVE robotics
    parts, sz, ls = [], 11.5, 1.6
    for i, (*_, col, lab, sub) in enumerate(orbits):
        parts += [("dot", col), ("mono-b", lab + " ", col), ("mono", sub, p["muted"])]
        if i < 2:
            parts.append(("mono", "  → ", p["faint"]))
    width = sum(14 if k[0] == "dot" else measure(k[0], k[1], sz, ls) for k in parts)
    x = min(cx - width / 2, 1136 - width)
    s.add('<g class="fade" xml:space="preserve" style="animation-delay:1.6s">')
    for k in parts:
        if k[0] == "dot":
            s.add(f'<circle cx="{x + 4:.1f}" cy="358" r="4" fill="{k[1]}"/>')
            x += 14
        else:
            s.t(x, 362, k[0], k[1], k[2], sz, ls=ls)
            x += measure(k[0], k[1], sz, ls)
    s.add("</g>")

    # epigraph strip
    s.add(f'<line class="draw" pathLength="1" x1="64" y1="548" x2="1136" y2="548" stroke="{p["line"]}" style="animation-delay:1.2s"/>')
    s.add('<g class="fade" style="animation-delay:1.5s">')
    q = "O ever youthful, O ever weeping."
    s.t(64, 596, "serif-i", q, size=27)
    s.t(64 + measure("serif-i", q, 27) + 16, 594, "mono", "— JACK KEROUAC", p["faint"], 12, ls=2)
    s.t(1136, 594, "mono", "dogogod.github.io ↗", p["accent"], 14, anchor="end", ls=.5)
    s.add("</g>")
    return s


# ---------------------------------------------------------------- section headers

def header(title, italic, note):
    def build(p):
        s = Svg(1200, 120, f"{title} {italic}", p)
        s.t(4, 74, "serif", title, size=56)
        s.t(4 + measure("serif", title + " ", 56), 74, "serif-i", italic, p["accent"], 56)
        s.t(1196, 70, "mono", note, p["muted"], 13, anchor="end", ls=2.2)
        s.add(f'<line class="draw" pathLength="1" x1="4" y1="100" x2="1196" y2="100" stroke="{p["line"]}"/>')
        s.add(f'<rect x="4" y="98.5" width="40" height="3" fill="{p["accent"]}"/>')
        return s
    return build


# ---------------------------------------------------------------- project art (each draws into its own box)

def art_odom(s, p):
    """Foot contacts and an IMU trace feeding an odometry estimate that tracks ground truth."""
    s.defs.append('<clipPath id="sig"><rect x="14" y="0" width="136" height="76"/></clipPath>')
    s.css.append(".slide{animation:slide 1.4s linear infinite}@keyframes slide{to{transform:translateX(-50px)}}")
    out = []
    for i, (leg, ph) in enumerate([("L", 0), ("R", .5)]):
        y = 4 + i * 20
        out.append(s.text(0, y + 10, "mono-b", leg, p["muted"], 10))
        out.append(f'<rect x="14" y="{y}" width="136" height="13" rx="3" fill="{p["bg"]}" stroke="{p["line"]}"/>')
        blocks = "".join(f'<rect x="{14 + ph * 50 + k * 50 - 50:.1f}" y="{y + 2.5}" width="27" height="8" rx="2" fill="{p["robo"]}" '
                         f'opacity="{.95 if ph == 0 else .6}"/>' for k in range(5))
        out.append(f'<g clip-path="url(#sig)"><g class="slide">{blocks}</g></g>')
    pts = "L".join(f"{14 + k:.0f} {58 - 9 * (.7 * math.sin(2 * math.pi * k / 50) + .3 * math.sin(4 * math.pi * k / 50 + 1)):.1f}" for k in range(0, 191, 3))
    out.append(s.text(0, 61, "mono-b", "ω", p["muted"], 10))
    out.append(f'<g clip-path="url(#sig)"><path class="slide" d="M{pts}" fill="none" stroke="{p["ai"]}" stroke-width="1.5"/></g>')
    out.append(f'<rect x="0" y="80" width="150" height="70" rx="10" fill="{p["bg"]}" stroke="{p["line"]}"/>')
    gt = "M12 136C30 104 52 94 74 106S112 132 128 110 136 92 128 90"
    est = "M12 136C32 108 54 98 76 110S114 128 130 106 136 94 126 92"
    out.append(f'<path d="{gt}" fill="none" stroke="{p["muted"]}" stroke-width="1.4"/>')
    out.append(f'<path d="{est}" pathLength="1" fill="none" stroke="{p["robo"]}" stroke-width="2" stroke-dasharray="1" stroke-dashoffset="1">'
               '<animate attributeName="stroke-dashoffset" values="1;0;0;1" keyTimes="0;.7;.9;1" dur="6s" repeatCount="indefinite"/></path>')
    out.append(f'<circle r="4.5" fill="{p["robo"]}"><animateMotion dur="6s" repeatCount="indefinite" keyPoints="0;1;1;0" keyTimes="0;.7;.9;1" calcMode="linear" path="{est}"/></circle>')
    out.append(s.text(10, 96, "mono", "GT", p["muted"], 8.5, ls=1) + s.text(30, 96, "mono", "EST", p["robo"], 8.5, ls=1))
    return "".join(out)


def art_claw(s, p):
    out = [f'<circle class="spin" cx="75" cy="75" r="66" fill="none" stroke="{p["faint"]}" stroke-dasharray="2 6"/>']
    nodes = [(75 + 50 * math.cos(math.radians(a)), 75 + 50 * math.sin(math.radians(a))) for a in range(-90, 270, 60)]
    for i, (x, y) in enumerate(nodes):
        out.append(f'<path d="M75 75L{x:.1f} {y:.1f}" stroke="{p["line"]}" stroke-width="1.5"/>')
        out.append(f'<circle r="3" fill="{p["accent"]}"><animateMotion dur="3.6s" begin="{i * .6}s" repeatCount="indefinite" '
                   f'keyPoints="0;1;1" keyTimes="0;.35;1" calcMode="linear" path="M75 75L{x:.1f} {y:.1f}"/>'
                   f'<animate attributeName="opacity" values="0;1;0;0" keyTimes="0;.1;.35;1" dur="3.6s" begin="{i * .6}s" repeatCount="indefinite"/></circle>')
    for i, (x, y) in enumerate(nodes):
        out.append(f'<rect x="{x - 9:.1f}" y="{y - 9:.1f}" width="18" height="18" rx="5" fill="{p["panel"]}" stroke="{p["muted"]}" stroke-width="1.3"/>')
        out.append(f'<rect x="{x - 9:.1f}" y="{y - 9:.1f}" width="18" height="18" rx="5" fill="{p["accent"]}" opacity="0">'
                   f'<animate attributeName="opacity" values="0;0;.85;0;0" keyTimes="0;.3;.38;.6;1" dur="3.6s" begin="{i * .6}s" repeatCount="indefinite"/></rect>')
    out.append(f'<circle class="pulse" cx="75" cy="75" r="20" fill="{p["accent2"]}"/><circle cx="75" cy="75" r="13" fill="{p["accent"]}"/>')
    out.append(f'<path d="M69 70q6 4 4 12M75 68q6 5 3 13M81 70q5 5 1 12" fill="none" stroke="{p["bg"]}" stroke-width="1.8" stroke-linecap="round"/>')
    return "".join(out)


def art_letters(s, p):
    s.defs.append(
        '<clipPath id="frame"><rect x="2" y="6" width="146" height="138" rx="14"/></clipPath>'
        f'<radialGradient id="lamp"><stop offset="0" stop-color="{p["glow"]}" stop-opacity=".95"/><stop offset=".45" stop-color="{p["glow"]}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="{p["glow"]}" stop-opacity="0"/></radialGradient>'
    )
    s.css.append(
        ".flick{animation:flick 3.2s infinite}@keyframes flick{0%,100%{opacity:1}22%{opacity:.82}25%{opacity:.96}48%{opacity:.88}70%{opacity:1}74%{opacity:.78}}"
        ".drift{animation:drift 7s ease-in-out infinite alternate}.drift2{animation:drift 9s ease-in-out -3s infinite alternate-reverse}"
        "@keyframes drift{from{transform:translateX(-4px)}to{transform:translateX(4px)}}"
        ".ember{animation:ember 3s ease-out infinite both}@keyframes ember{from{opacity:0;transform:none}15%{opacity:.9}to{opacity:0;transform:translate(6px,-46px)}}"
    )
    c1, c2, c3 = p["paper"]
    out = [f'<g clip-path="url(#frame)"><rect x="0" y="0" width="150" height="150" fill="{p["bg"]}"/>',
           f'<circle class="flick" cx="104" cy="52" r="46" fill="url(#lamp)"/><circle cx="104" cy="52" r="7" fill="{p["glow"]}"/>']
    for i in range(5):
        out.append(f'<circle class="ember" cx="{40 + i * 9}" cy="{100 - (i % 2) * 6}" r="1.6" fill="{p["accent"]}" style="animation-delay:{i * .6}s"/>')
    out.append(f'<path class="drift2" d="M-10 104C20 84 38 98 58 86S96 70 120 84 160 80 160 80V160H-10Z" fill="{c1}"/>')
    out.append(f'<g class="drift"><path d="M-10 122C18 106 40 116 64 108S108 96 160 110V160H-10Z" fill="{c2}"/>'
               f'<path d="M84 104h18v-12l9-8 9 8v12" fill="{c2}"/><rect x="99" y="96" width="5" height="6" fill="{p["glow"]}" class="flick"/></g>')
    out.append(f'<path d="M-10 140C30 126 60 140 90 132S140 128 160 134V160H-10Z" fill="{c3}"/></g>')
    out.append(f'<rect x="2" y="6" width="146" height="138" rx="14" fill="none" stroke="{p["line"]}"/>')
    return "".join(out)


def art_blog(s, p):
    """A notebook page writing itself, with the corner music player's record spinning."""
    s.css.append(".write{stroke-dasharray:1;stroke-dashoffset:1;animation:write 7s ease-in-out infinite both}"
                 "@keyframes write{0%{stroke-dashoffset:1;opacity:1}14%,82%{stroke-dashoffset:0;opacity:1}92%,100%{stroke-dashoffset:0;opacity:0}}"
                 ".vinyl{transform-box:fill-box;transform-origin:center;animation:spin 6s linear infinite}"
                 ".note{animation:note 3.5s ease-out infinite both}@keyframes note{from{opacity:0;transform:none}20%{opacity:1}to{opacity:0;transform:translate(10px,-34px)}}")
    out = [f'<rect x="10" y="6" width="104" height="132" rx="8" fill="{p["panel"]}" stroke="{p["muted"]}" stroke-width="1.2"/>',
           f'<path d="M26 6V138" stroke="{p["accent"]}" stroke-opacity=".5"/>']
    rnd = random.Random(3)
    for k in range(6):
        y = 30 + k * 17
        out.append(f'<path d="M30 {y + 3}H104" stroke="{p["line"]}"/>')
        end = 100 - (22 if k in (2, 5) else rnd.randint(0, 10))
        pts = " ".join(f"{x} {y + (1.6 if (x // 6) % 2 else -1.6):.1f}" for x in range(34, end, 6))
        out.append(f'<path class="write" pathLength="1" d="M{pts}" '
                   f'fill="none" stroke="{p["ink"] if k else p["accent"]}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" '
                   f'style="animation-delay:{k * .55:.2f}s"/>')
    out.append(f'<g class="vinyl"><circle cx="116" cy="114" r="30" fill="{p["ink"]}"/>'
               + "".join(f'<circle cx="116" cy="114" r="{r}" fill="none" stroke="{p["bg"]}" stroke-opacity=".18"/>' for r in (24, 19, 14))
               + f'<circle cx="116" cy="114" r="9" fill="{p["accent"]}"/><circle cx="116" cy="114" r="2" fill="{p["bg"]}"/>'
               f'<path d="M98 102a22 22 0 0 1 10-8" stroke="{p["bg"]}" stroke-opacity=".5" stroke-width="2" fill="none"/></g>')
    for i, x in enumerate((128, 140)):
        out.append(f'<g class="note" style="animation-delay:{i * 1.7}s"><path d="M{x} 80v-14l8-2v12" fill="none" stroke="{p["accent"]}" stroke-width="1.6"/>'
                   f'<circle cx="{x - 2}" cy="80" r="3" fill="{p["accent"]}"/><circle cx="{x + 6}" cy="76" r="3" fill="{p["accent"]}"/></g>')
    return "".join(out)


def art_sync(s, p):
    s.css.append(".spin2{transform-box:fill-box;transform-origin:center;animation:spin 6s linear infinite}")

    def pt(a, r):
        return 75 + r * math.cos(math.radians(a)), 75 + r * math.sin(math.radians(a))

    out = [f'<circle cx="75" cy="75" r="66" fill="none" stroke="{p["line"]}" stroke-dasharray="1 5"/>', '<g class="spin2">']
    for a0, a1, col in [(-160, -20, p["ai"]), (20, 160, p["accent"])]:
        (x0, y0), (x1, y1) = pt(a0, 50), pt(a1, 50)
        out.append(f'<path d="M{x0:.1f} {y0:.1f}A50 50 0 0 1 {x1:.1f} {y1:.1f}" fill="none" stroke="{col}" stroke-width="5" stroke-linecap="round"/>')
        tx, ty = pt(a1 + 9, 50)
        (bx, by), (cx_, cy_) = pt(a1 - 2, 59), pt(a1 - 2, 41)
        out.append(f'<path d="M{tx:.1f} {ty:.1f}L{bx:.1f} {by:.1f}L{cx_:.1f} {cy_:.1f}Z" fill="{col}"/>')
    out.append("</g>")
    out.append(f'<rect x="59" y="70" width="32" height="26" rx="5" fill="{p["ink"]}"/>'
               f'<path d="M64 70v-7a11 11 0 0 1 22 0v7" fill="none" stroke="{p["ink"]}" stroke-width="4"/>'
               f'<circle cx="75" cy="81" r="3.4" fill="{p["accent"]}"/><rect x="73.6" y="82" width="2.8" height="7" rx="1" fill="{p["accent"]}"/>')
    out.append(s.text(0, 148, "mono", "VAULT", p["muted"], 9, ls=1.4) + s.text(150, 148, "mono", "SJTU CLOUD", p["muted"], 9, anchor="end", ls=1.4))
    return "".join(out)


def art_mines(s, p):
    mines = {(0, 4), (3, 1), (4, 3)}
    s.css.append(".cov{animation:cov 7s ease infinite both}@keyframes cov{0%,8%{opacity:1}14%,82%{opacity:0}90%,100%{opacity:1}}"
                 ".flag{animation:flag 7s ease infinite both}@keyframes flag{0%,40%{opacity:0;transform:translateY(-6px)}46%,82%{opacity:1;transform:none}88%,100%{opacity:0}}")
    out, size, gap, ox = [], 24, 4, 7
    nc = {1: p["n1"], 2: p["n2"], 3: p["n3"]}
    for r in range(5):
        for c in range(5):
            x, y = ox + c * (size + gap), ox + r * (size + gap)
            out.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="4" fill="{p["cell"]}" stroke="{p["line"]}"/>')
            if (r, c) in mines:
                out.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="4" fill="{p["cover"]}" stroke="{p["muted"]}" stroke-opacity=".5"/>'
                           f'<g class="flag" style="animation-delay:{(r + c) * .05:.2f}s"><path d="M{x + 9} {y + 18}V{y + 6}l8 3.5-8 3.5" fill="{p["accent"]}" stroke="{p["accent"]}" stroke-width="1.6" stroke-linejoin="round"/></g>')
                continue
            n = sum((r + dr, c + dc) in mines for dr in (-1, 0, 1) for dc in (-1, 0, 1))
            if n:
                out.append(s.text(x + size / 2, y + 17, "mono-b", str(n), nc[n], 14, anchor="middle"))
            dist = math.hypot(r - 2, c - 1)
            out.append(f'<rect class="cov" x="{x}" y="{y}" width="{size}" height="{size}" rx="4" fill="{p["cover"]}" stroke="{p["muted"]}" stroke-opacity=".5" style="animation-delay:{dist * .14:.2f}s"/>')
    return "".join(out)


# ---------------------------------------------------------------- project cards

PROJECTS = [
    ("AutoOdom", None, "LEGGED ROBOTICS", ["Autodom reproduced: RL locomotion in", "Isaac Sim, odometry from joints & IMU."],
     "ISAAC SIM · RL · ROS2", "Python", "#3572A5", art_odom),
    ("SJTUClaw", None, "AGENT RUNTIME", ["A local-first AI agent runtime: tools,", "memory, skills, cron and a desktop pet."],
     "AGENTS · MEMORY · WEB / TUI / CLI", "Python", "#3572A5", art_claw),
    ("Letters Home", "家书", "A FILM MADE OF CODE", ["A 13-minute anti-war short from five", "real letters, lit like a paper lamp."],
     "WEBGL · PAPER-CUT · STORY", "JavaScript", "#F1E05A", art_letters),
    ("Guztchian's Blog", None, "THE NOTEBOOK", ["Coder by craft, writer by choice —", "where projects and life land on the page."],
     "ASTRO · BILINGUAL · MUSIC", "Astro", "#FF5A03", art_blog),
    ("SJTU Cloud Sync", None, "OBSIDIAN PLUGIN", ["Recoverable two-way sync between", "Obsidian and SJTU Cloud, with E2EE."],
     "SYNC · CONFLICTS · ENCRYPTION", "TypeScript", "#3178C6", art_sync),
    ("MineSweeper", None, "CONSOLE GAME", ["Cross-platform C++ Minesweeper for", "the terminal, with mouse and sound."],
     "C++ · CGT · CONSOLE UI", "C++", "#F34B7D", art_mines),
]


def card_footer(s, p, x0, x1, y, tags, lang, lang_col):
    s.add(f'<line x1="{x0}" y1="{y - 32}" x2="{x1}" y2="{y - 32}" stroke="{p["line"]}"/>')
    s.t(x0, y, "mono", tags, p["muted"], 12.5, ls=1.4)
    s.t(x1 - 12, y, "mono", "↗", p["accent"], 16, anchor="end")
    s.t(x1 - 36, y, "mono", lang, p["ink"], 13, anchor="end")
    s.add(f'<circle cx="{x1 - 36 - measure("mono", lang, 13) - 11:.1f}" cy="{y - 4.5}" r="5" fill="{lang_col}"/>')


def card(i, proj):
    title, cjk, kind, desc, tags, lang, lang_col, art = proj

    def build(p):
        s = Svg(580, 300, f"{cjk + ' ' if cjk else ''}{title} — {' '.join(desc)}", p)
        s.add(f'<rect x=".5" y=".5" width="579" height="299" rx="22" fill="{p["bg"]}" stroke="{p["line"]}"/>')
        s.t(34, 54, "mono-b", f"{i + 1:02d}", p["accent"], 14, ls=1)
        s.t(64, 54, "mono", kind, p["muted"], 12.5, ls=2.2)
        x = 31
        if cjk:
            s.t(x, 128, "brush", cjk, size=58)
            x += measure("brush", cjk, 58) + 12
            s.t(x, 124, "serif-i", title, p["accent"], 44)
        else:
            size = 50
            while 31 + measure("serif", title, size) > 390:
                size -= 1
            s.t(x, 124, "serif", title, size=size)
        for k, ln in enumerate(desc):
            s.t(34, 168 + k * 28, "body", ln, p["muted"], 18)
        card_footer(s, p, 34, 546, 268, tags, lang, lang_col)
        s.add(f'<g transform="translate(404 34)">{art(s, p)}</g>')
        return s
    return build


# ---------------------------------------------------------------- periodic table

TOOLS = [
    ("Cp", "C++", "lang"), ("Py", "Python", "lang"), ("Ts", "TypeScript", "lang"), ("Js", "JavaScript", "lang"),
    ("Pt", "PyTorch", "ai"), ("Cv", "OpenCV", "ai"), ("Yo", "YOLO", "ai"), ("Ag", "LLM Agents", "ai"),
    ("Is", "Isaac Sim", "robo"), ("Il", "Isaac Lab", "robo"), ("Ro", "ROS2", "robo"), ("Rl", "RL", "robo"),
    ("As", "Astro", "craft"), ("Gt", "Git", "craft"), ("Lx", "Linux", "craft"), ("Ob", "Obsidian", "craft"),
]
GROUPS = [("lang", "LANGUAGES"), ("ai", "AI & VISION"), ("robo", "ROBOTICS"), ("craft", "CRAFT")]


def toolkit(p):
    s = Svg(1200, 392, "Toolkit: " + ", ".join(t[1] for t in TOOLS), p)
    s.css.append(".tile{transform-box:fill-box;transform-origin:center;animation:pop .7s cubic-bezier(.3,1.4,.5,1) both}"
                 "@keyframes pop{from{opacity:0;transform:scale(.86)}to{opacity:1;transform:none}}"
                 ".exc{opacity:0;animation:exc 9.6s ease-in-out infinite}@keyframes exc{0%{opacity:0}3%{opacity:1}10%,100%{opacity:0}}")
    s.add(f'<rect x=".5" y=".5" width="1199" height="391" rx="24" fill="{p["bg"]}" stroke="{p["line"]}"/>')
    x = 62
    for key, label in GROUPS:
        s.add(f'<rect x="{x}" y="38" width="12" height="12" rx="3" fill="{p[key]}"/>')
        s.t(x + 20, 49, "mono", label, p["muted"], 12.5, ls=1.8)
        x += 20 + measure("mono", label, 12.5, 1.8) + 30
    s.t(1138, 49, "mono", "16 ELEMENTS · 4 GROUPS · STABLE", p["faint"], 12, anchor="end", ls=1.8)
    for n, (sym, name, key) in enumerate(TOOLS):
        col = p[key]
        tx, ty = 62 + (n % 8) * 136, 80 + (n // 8) * 146
        s.add(f'<g transform="translate({tx} {ty})"><g class="tile" style="animation-delay:{.05 * n + .1:.2f}s">'
              f'<rect width="124" height="130" rx="14" fill="{col}" fill-opacity=".08" stroke="{col}" stroke-opacity=".45"/>'
              f'<rect class="exc" width="124" height="130" rx="14" fill="{col}" fill-opacity=".14" stroke="{col}" stroke-width="2" style="animation-delay:{1.5 + n * .6:.1f}s"/>')
        s.t(14, 26, "mono-b", str(n + 1), col, 13)
        s.add(f'<circle cx="108" cy="21" r="3" fill="{col}" opacity=".7"/>')
        s.t(62, 84, "serif", sym, size=58, anchor="middle")
        s.t(62, 113, "mono", name.upper(), p["muted"], 10.5, anchor="middle", ls=1.2)
        s.add("</g></g>")
    return s


# ---------------------------------------------------------------- footer

def footer(p):
    s = Svg(1200, 300, "Stay hungry. Stay foolish. 求知若饥，虚心若愚", p)
    s.css.append(".tw{animation:tw 3.4s ease-in-out infinite}@keyframes tw{0%,100%{opacity:1}50%{opacity:.35}}")
    rnd = random.Random(42)
    for _ in range(46):
        x, y = rnd.uniform(720, 1196), rnd.uniform(10, 290)
        s.add(f'<circle class="tw" cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(.6, 1.4):.2f}" fill="{p["faint"]}" style="animation-delay:-{rnd.uniform(0, 3.4):.2f}s"/>')
    stars = dict(dubhe=(905, 150), merak=(872, 212), phecda=(948, 240), megrez=(966, 184), alioth=(1030, 196), mizar=(1086, 214), alkaid=(1140, 262))
    polaris = (963, 42)  # on the Merak -> Dubhe line
    chain = ["merak", "dubhe", "megrez", "phecda", "merak"]
    handle = ["megrez", "alioth", "mizar", "alkaid"]
    for k, seq in enumerate([chain, handle]):
        d = "M" + "L".join(f"{stars[n][0]} {stars[n][1]}" for n in seq)
        s.add(f'<path class="draw" pathLength="1" d="{d}" fill="none" stroke="{p["muted"]}" stroke-width="1.2" style="animation-delay:{.3 + k * .9}s;animation-duration:1.8s"/>')
    mx, my = stars["merak"]
    s.add(f'<path class="draw" pathLength="1" d="M{mx} {my}L{polaris[0]} {polaris[1]}" stroke="{p["accent"]}" stroke-width="1" stroke-dasharray="1" '
          f'opacity=".75" style="animation-delay:2.2s;animation-duration:1.4s"/>')
    for i, (n, (x, y)) in enumerate(stars.items()):
        s.add(f'<circle class="tw" cx="{x}" cy="{y}" r="{4.2 if n in ("dubhe", "merak") else 3.4}" fill="{p["ink"]}" style="animation-delay:-{i * .45:.2f}s"/>')
    s.add(f'<circle class="pulse" cx="{polaris[0]}" cy="{polaris[1]}" r="12" fill="{p["accent2"]}"/><circle cx="{polaris[0]}" cy="{polaris[1]}" r="5" fill="{p["accent"]}"/>')
    s.add('<g class="fade" style="animation-delay:3s">')
    s.t(polaris[0] + 18, polaris[1] + 4, "mono-b", "POLARIS", p["accent"], 11, ls=2)
    s.t(polaris[0] + 18, polaris[1] + 20, "mono", "the pointers always lead north", p["muted"], 10.5)
    s.add("</g>")

    s.t(8, 92, "mono", "— SIGNING OFF FROM SHANGHAI", p["muted"], 13, ls=2.4)
    s.t(4, 172, "serif-i", "Stay hungry. Stay foolish.", size=70, add="rise", style="animation-delay:.2s")
    s.t(8, 224, "body", "求知若饥，虚心若愚。", p["muted"], 24, ls=6, add="fade", style="animation-delay:.6s")
    s.add('<g class="fade" style="animation-delay:1s">')
    x = 8
    for txt, col in [("dogogod.github.io", p["accent"]), ("  ·  ", p["faint"]), ("aetherpulse@sjtu.edu.cn", p["muted"]),
                     ("  ·  ", p["faint"]), ("SJTU", p["muted"])]:
        s.add(s.text(x, 270, "mono", txt, col, 13, ls=1).replace("<text ", '<text xml:space="preserve" '))
        x += measure("mono", txt, 13, 1)
    s.add("</g>")
    return s


if __name__ == "__main__":
    save("hero", hero)
    save("section-work", header("Selected", "work", "SIX REPOS · ONE CURIOSITY"))
    for i, proj in enumerate(PROJECTS):
        save(f"card-{i + 1:02d}", card(i, proj))
    save("section-tools", header("The", "toolkit", "A PERIODIC TABLE OF THINGS I REACH FOR"))
    save("toolkit", toolkit)
    save("footer", footer)
