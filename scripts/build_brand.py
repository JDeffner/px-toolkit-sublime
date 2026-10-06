"""Build PX/ST SVG and PNG assets. Requires resvg-py, fonttools, and Segoe UI."""
import argparse
import base64
from html import escape
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
import resvg_py

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".github/assets"
INK, CREAM, GOLD, MUTED = "#17161A", "#F2EDE3", "#C8952F", "#C2BBAF"
CAP, GAP = 1466, 200
# P, X and T come from PXTK's scripts/brandFace.ts.
# S uses matching round-stroke weight, with upright bowls and level terminals.
FACE = {
    "P": ("M0 0L0 1466L700 1466Q1010 1466 1140 1362Q1270 1258 1270 1040Q1270 822 1140 719Q1010 616 700 616L453 616L453 0Z"
          "M453 946L690 946Q900 946 900 1040Q900 1136 690 1136L453 1136Z", 1270),
    "X": ("M0 1466L560 1466L750 1169.7L940 1466L1500 1466L1030 733L1500 0L940 0L750 296.3L560 0L0 0L470 733Z", 1500),
    "T": ("M0 1466H1377V1104H915V0H462V1104H0Z", 1377),
    "S": ("M1130 1030H770Q760 1150 565 1150Q365 1150 365 1050"
          "Q365 965 610 915Q870 860 1005 745Q1130 630 1130 410"
          "Q1130 180 977.5 77.5Q825 -25 565 -25Q300 -25 150 100"
          "Q0 225 0 436H360Q370 316 565 316Q765 316 765 416"
          "Q765 501 520 551Q260 606 125 721Q0 836 0 1056"
          "Q0 1286 152.5 1388.5Q305 1491 565 1491Q830 1491 980 1366"
          "Q1130 1241 1130 1030Z", 1130),
}


def word(text, baseline, fill):
    scale = 34 / CAP
    width = sum(FACE[c][1] for c in text) + GAP * (len(text) - 1)
    paths, offset = [], 0
    for char in text:
        path, advance = FACE[char]
        paths.append(f'<path transform="translate({offset} 0)" d="{path}"/>')
        offset += advance + GAP
    return (f'<g transform="translate({(128 - width * scale) / 2:.5f} {baseline:.5f}) '
            f'scale({scale:.9f} {-scale:.9f})" fill="{fill}" fill-rule="evenodd">'
            + "".join(paths) + "</g>")


def icon_body():
    # Center the complete ink block, including the S's lower overshoot.
    below = 25 * 34 / CAP
    baseline = (128 - (68 + 6 + below)) / 2 + 34
    return (f'<rect width="128" height="128" rx="26" fill="{INK}"/>'
            + word("PX", baseline, CREAM) + word("ST", baseline + 40, GOLD))


def svg(width, height, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">'
            f'<title>{escape(title)}</title>{body}</svg>\n')


def outlined_text(font, text, x, y, size, color):
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale, offset, paths = size / font["head"].unitsPerEm, 0, []
    for char in text:
        glyph = glyphs[cmap[ord(char)]]
        pen = SVGPathPen(glyphs)
        glyph.draw(pen)
        if pen.getCommands():
            paths.append(f'<path transform="translate({offset} 0)" d="{pen.getCommands()}"/>')
        offset += glyph.width
    return (f'<g aria-label="{escape(text, quote=True)}" fill="{color}" '
            f'transform="translate({x} {y}) scale({scale} {-scale})">'
            + "".join(paths) + "</g>")


def data_url(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def build(font_dir):
    OUT.mkdir(parents=True, exist_ok=True)
    icon = svg(128, 128, icon_body(), "PX ST, PX for Sublime Text")
    (OUT / "px-st-icon.svg").write_text(icon, encoding="utf-8")
    for size in (128, 512, 1024):
        (OUT / f"px-st-icon-{size}.png").write_bytes(resvg_py.svg_to_bytes(svg_string=icon, width=size, height=size))

    regular = TTFont(font_dir / "segoeui.ttf")
    bold = TTFont(font_dir / "segoeuib.ttf")
    parts = [f'<rect width="1280" height="640" fill="{INK}"/>',
             f'<g transform="translate(27 24) scale(.875)">{icon_body()}</g>']

    def text(value, x, y, size, color=CREAM, weight=False):
        parts.append(outlined_text(bold if weight else regular, value, x, y, size, color))

    text("PX for Sublime Text", 152, 83, 54, weight=True)
    text("Crusader Kings III modding", 154, 123, 27, GOLD)
    parts.append('<path d="M48 160H1232" stroke="#494239"/>')
    text("Script editing", 48, 235, 31, weight=True)
    text("Context-aware completion", 48, 278, 25, MUTED)
    text("Hover docs and navigation", 48, 315, 25, MUTED)
    text("Diagnostics and localization", 48, 352, 25, MUTED)
    text("Native Sublime tools", 48, 438, 31, weight=True)
    text("Event and GUI reports", 48, 481, 25, MUTED)
    text("Tiger validation", 48, 518, 25, MUTED)
    text("CONTEXT-AWARE COMPLETION", 512, 200, 21, GOLD, True)
    screenshot = data_url(ROOT / "screenshots/wiki/completion.png")
    parts.append(f'<image x="512" y="216" width="720" height="387" xlink:href="{screenshot}"/>')
    parts.append('<rect x="512" y="216" width="720" height="387" fill="none" stroke="#494239" stroke-width="2"/>')
    text("Part of Paradox Modding Toolkit", 48, 603, 21, MUTED)
    social = svg(1280, 640, "".join(parts), "PX for Sublime Text: Crusader Kings III modding")
    (OUT / "github-social-preview.svg").write_text(social, encoding="utf-8")
    (OUT / "github-social-preview.png").write_bytes(resvg_py.svg_to_bytes(svg_string=social))
    regular.close()
    bold.close()

    icon_url = data_url(OUT / "px-st-icon-512.png")
    social_url = data_url(OUT / "github-social-preview.png")
    guide = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PX ST brand assets</title>
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:{INK};color:{CREAM};font:18px/1.65 "Segoe UI",sans-serif}}main{{max-width:1120px;margin:auto;padding:56px 32px}}h1,h2{{line-height:1.2}}h1{{font-size:44px;margin:0 0 16px}}h2{{font-size:28px;margin-top:44px}}p{{max-width:72ch}}a{{color:#E1B75E}}.muted{{color:{MUTED}}}.icons{{display:flex;align-items:end;gap:32px;flex-wrap:wrap;padding:30px;background:#222126;border-radius:16px}}figure{{margin:0}}figcaption{{font-size:14px;color:{MUTED};margin-top:10px}}img{{display:block;max-width:100%;height:auto}}.preview{{border:1px solid #494239;width:100%}}code{{font:15px Consolas,monospace;overflow-wrap:anywhere}}.swatches{{display:flex;gap:24px;flex-wrap:wrap}}.swatch{{display:inline-block;width:20px;height:20px;border:1px solid #766E62;vertical-align:middle;margin-right:8px}}.spec{{background:#222126;border-radius:16px;padding:24px 28px;margin:22px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}}
</style><main>
<p class="muted">Paradox Modding Toolkit / Sublime Text</p><h1>PX ST</h1>
<p>The icon uses <strong>PX / ST</strong>. Use <strong>PX for Sublime Text</strong> when the full name is needed. The package identifier stays <code>LSP-px</code>.</p>
<div class="icons">{''.join(f'<figure><img src="{icon_url}" width="{n}" height="{n}" alt="PX ST icon at {n} pixels"><figcaption>{n} px</figcaption></figure>' for n in (256,128,64,32))}</div>
<h2>Social preview</h2><img class="preview" src="{social_url}" width="1280" height="640" alt="PX for Sublime Text social preview with a real completion screenshot">
<h2>Global style guide</h2><p>Keep the parent PXTK brand: a charcoal tile with rounded corners, cream PX lettering, and gold ST lettering. Use the original P, X, and T shapes, with an upright S that has level terminals. Use Segoe UI for supporting text. Keep layouts flat, with clear spacing and no gradients or decorative symbols.</p>
<div class="swatches">{''.join(f'<span><i class="swatch" style="background:{color}"></i>{name} <code>{color}</code></span>' for name,color in [('Ink',INK),('Cream',CREAM),('Gold',GOLD)])}</div>
<p>Keep at least one quarter of the icon width clear around the icon when it sits next to other content. Use the icon at 32 px or larger. Use the SVG for scaling. Do not stretch it or replace ST with the Sublime Text logo.</p>
<div class="spec"><h2 style="margin-top:0">Icon</h2><p><strong>Files:</strong> <code>.github/assets/px-st-icon.svg</code> and <code>px-st-icon-128.png</code>, <code>px-st-icon-512.png</code>, <code>px-st-icon-1024.png</code> in the same folder.</p><p><strong>Dimensions:</strong> square; PNG exports at 128, 512, and 1024 px. The corners outside the rounded tile are transparent.</p><p><strong>Prompt:</strong> Adapt the existing PXTK vector icon. Keep its charcoal rounded square and original cream PX outlines. Replace the gold TK line with ST. Keep the original T and use an upright S with level terminals and matching stroke weight. Match the 34-unit cap height and 6-unit line gap in a 128-unit square. Center the complete letter block by its visible bounds. No cursor, pointer, shadows, gradients, or extra symbols.</p></div>
<div class="spec"><h2 style="margin-top:0">Social preview</h2><p><strong>Files:</strong> <code>.github/assets/github-social-preview.svg</code> and <code>.github/assets/github-social-preview.png</code>.</p><p><strong>Dimensions:</strong> 1280 × 640 px, opaque background.</p><p><strong>Prompt:</strong> Extend the PXTK social preview style for PX for Sublime Text. Use the PX/ST icon, a charcoal background, cream heading, and gold subtitle. State Crusader Kings III modding. Pair a short list of supported editing tools with the supplied real Sublime completion screenshot. Keep the mouse pointer out of all images. Do not fabricate editor UI. Keep text legible and leave space around the page edges.</p></div>
<h2>Source and export</h2><p>The P, X, and T outlines come from <a href="https://github.com/JDeffner/paradox-modding-toolkit/blob/main/scripts/brandFace.ts">PXTK's display face</a>. The S is redrawn with upright bowls and level terminals. The source screenshot is <code>screenshots/wiki/completion.png</code>. The social SVG embeds that screenshot and stores its text as vector outlines, so it needs no external fonts or images.</p><p>Build with <code>scripts/build_brand.py</code>, Python, <code>resvg-py</code>, <code>fonttools</code>, and Segoe UI. Pass <code>--font-dir</code> if the fonts are outside <code>C:/Windows/Fonts</code>. Dependencies are used only for asset generation.</p><pre>python -m pip install resvg-py fonttools
python scripts/build_brand.py</pre><p>The PNG social preview is ready to select in the repository's Social preview setting. This asset build does not change that setting.</p>
</main></html>'''
    (ROOT / "art-instructions.html").write_text(guide, encoding="utf-8")
    print(f"Built brand assets in {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=Path("C:/Windows/Fonts"))
    build(parser.parse_args().font_dir)
