"""Build the static marketing site (www.hubgentic.ai) into site/dist/.

Copy lives in content/{it,en}.yml, structure in templates/. Italian is served
at the root, English under /en/. Run with `make site`.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
SITE_URL = "https://www.hubgentic.ai"
APP_URL = "https://app.hubgentic.ai"
EMAIL = "info@hubgentic.ai"
LINKEDIN = "https://www.linkedin.com/company/hubgentic"
LANGS = ("it", "en")
PAGES = {"home": "home.html", "privacy": "privacy.html", "thanks": "thanks.html"}
NOINDEX = {"thanks"}


def load(lang: str) -> dict:
    return yaml.safe_load((ROOT / "content" / f"{lang}.yml").read_text(encoding="utf-8"))


def asset_version() -> str:
    h = hashlib.sha256()
    for name in ("site.css", "site.js"):
        h.update((ROOT / "static" / name).read_bytes())
    return h.hexdigest()[:10]


def structured_data(c: dict) -> list[dict]:
    """schema.org JSON-LD: who we are, what we offer, and the FAQ."""
    home = SITE_URL + c["paths"]["home"]
    org = {
        "@type": "Organization", "@id": f"{SITE_URL}/#org", "name": "Hubgentic",
        "url": SITE_URL + "/", "logo": f"{SITE_URL}/assets/icon-512.png", "email": EMAIL,
        "sameAs": [LINKEDIN],
        "parentOrganization": {"@type": "Organization", "name": "Complify PTE. LTD."},
    }
    service = {
        "@type": "ProfessionalService", "@id": f"{home}#service", "name": "Hubgentic",
        "url": home, "description": c["meta"]["description"], "provider": {"@id": f"{SITE_URL}/#org"},
        "areaServed": ["IT", "EU"], "availableLanguage": ["it", "en"], "email": EMAIL,
        "hasOfferCatalog": {
            "@type": "OfferCatalog", "name": c["services"]["title"],
            "itemListElement": [
                {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s["title"], "description": s["body"]}}
                for s in c["services"]["items"]
            ],
        },
    }
    faq = {
        "@type": "FAQPage", "@id": f"{home}#faq", "inLanguage": c["lang"],
        "mainEntity": [
            {"@type": "Question", "name": i["q"], "acceptedAnswer": {"@type": "Answer", "text": i["a"]}}
            for i in c["faq"]["items"]
        ],
    }
    return [{"@context": "https://schema.org", "@graph": [org, service, faq]}]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(out: Path = DIST) -> Path:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "static", out / "assets")
    shutil.copy(ROOT / "static" / "favicon.svg", out / "favicon.svg")

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"), undefined=StrictUndefined,
        autoescape=select_autoescape(("html", "xml")), trim_blocks=True, lstrip_blocks=True,
    )
    content = {lang: load(lang) for lang in LANGS}
    common = {
        "site_url": SITE_URL, "app_url": APP_URL, "email": EMAIL, "linkedin": LINKEDIN,
        "year": date.today().year, "v": asset_version(), "content": content,
    }
    for lang, c in content.items():
        other = content["en" if lang == "it" else "it"]
        for page, template in PAGES.items():
            ctx = {
                **common, "c": c, "page": page, "path": c["paths"][page],
                "alt": other, "alt_path": other["paths"][page], "noindex": page in NOINDEX,
                "jsonld": structured_data(c) if page == "home" else [],
            }
            write(out / c["paths"][page].strip("/") / "index.html", env.get_template(template).render(ctx))

    write(out / "404.html", env.get_template("404.html").render(**common, c=content["it"]))
    for name in ("robots.txt", "sitemap.xml", "llms.txt"):
        write(out / name, env.get_template(name).render(**common))
    return out


if __name__ == "__main__":
    print(f"built {build().relative_to(ROOT.parent)}")
