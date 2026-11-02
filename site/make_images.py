"""Render the social-share images and app icons into site/static/ with headless Chrome.

Run after changing the hero copy: `uv run python site/make_images.py`.
The PNGs are committed, so the normal build doesn't need Chrome.
"""
from __future__ import annotations

import subprocess
import tempfile
from html import escape
from pathlib import Path

from build import ROOT, load

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONT = (ROOT / "static" / "fonts" / "inter-latin-wght-normal.woff2").as_uri()
STATIC = ROOT / "static"

BASE_CSS = f"""
@font-face {{ font-family: Inter; src: url({FONT}) format("woff2-variations"); font-weight: 100 900; }}
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ width: 100%; height: 100%; overflow: hidden; }}
body {{ font-family: Inter, sans-serif; color: #eceef8; -webkit-font-smoothing: antialiased;
  background: radial-gradient(700px 480px at 92% 8%, rgba(139,92,246,.42), transparent 70%),
              radial-gradient(640px 420px at 0% 100%, rgba(91,91,240,.34), transparent 70%), #0c0e1a; }}
.mark {{ display: grid; place-items: center; border-radius: 22%; color: #fff;
  background: linear-gradient(135deg, #5b5bf0, #8b5cf6); }}
"""
H_PATH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" width="54%" height="54%"><path d="M6 4v16M18 4v16M6 12h12"/></svg>'


def og_html(c: dict) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}
body {{ padding: 72px 80px; display: flex; flex-direction: column; }}
.brand {{ display: flex; align-items: center; gap: 16px; font-size: 34px; font-weight: 700; letter-spacing: -.03em; }}
.brand .mark {{ width: 52px; height: 52px; }}
.eyebrow {{ margin-top: auto; align-self: flex-start; padding: 8px 18px; border-radius: 999px; font-size: 22px; font-weight: 600;
  color: #c9c9ff; background: rgba(123,123,255,.16); border: 1px solid rgba(167,139,250,.35); }}
h1 {{ margin-top: 26px; font-size: 76px; line-height: 1.02; font-weight: 750; letter-spacing: -.045em; max-width: 1000px; }}
.grad {{ background: linear-gradient(100deg, #8f8fff, #c4a8ff); -webkit-background-clip: text; color: transparent; }}
.foot {{ margin-top: 40px; display: flex; justify-content: space-between; font-size: 22px; color: #a9aec8; }}
.foot b {{ color: #eceef8; font-weight: 600; }}
</style></head><body>
<div class="brand"><span class="mark">{H_PATH}</span>hubgentic</div>
<p class="eyebrow">{escape(c["hero"]["eyebrow"])}</p>
<h1>{escape(c["hero"]["title_a"])} <span class="grad">{escape(c["hero"]["title_b"])}</span></h1>
<div class="foot"><b>hubgentic.ai</b><span>{escape(c["platform"]["badge"])} · {escape(c["platform"]["title"])}</span></div>
</body></html>"""


def icon_html() -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}
body {{ background: linear-gradient(135deg, #5b5bf0, #8b5cf6); display: grid; place-items: center; color: #fff; }}
</style></head><body>{H_PATH.replace('width="54%" height="54%"', 'width="56%" height="56%"')}</body></html>"""


def shoot(html: str, size: tuple[int, int], out: Path, tmp: Path) -> None:
    page = tmp / f"{out.stem}.html"
    page.write_text(html, encoding="utf-8")
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
         f"--user-data-dir={tmp / 'profile'}", f"--window-size={size[0]},{size[1]}",
         f"--screenshot={out}", "--virtual-time-budget=2000", page.as_uri()],
        check=True, capture_output=True,
    )
    print(f"wrote {out.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for lang in ("it", "en"):
            shoot(og_html(load(lang)), (1200, 630), STATIC / f"og-{lang}.png", tmp)
        shoot(icon_html(), (512, 512), STATIC / "icon-512.png", tmp)
    subprocess.run(["sips", "-z", "180", "180", str(STATIC / "icon-512.png"), "--out", str(STATIC / "icon-180.png")],
                   check=True, capture_output=True)
    print("wrote site/static/icon-180.png")
