#!/usr/bin/env python3
"""Générateur statique de ThisWeek.

Lit les numéros YAML dans content/issues/, produit le site dans dist/ :
  index.html            dernier numéro
  numeros/<date>.html   chaque numéro
  archives.html         liste des numéros
  methode.html          page méthode (depuis content/methode.md)
  rss.xml               flux RSS des numéros

Usage : python3 site/build.py
"""

from __future__ import annotations

import html
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
DIST = ROOT / "dist"
SITE_URL = "https://ssc-ux.github.io/ThisWeek"

TYPE_LABELS = {
    "reco": "Recommandation",
    "pnds": "PNDS",
    "essai": "Essai clinique",
    "meta": "Méta-analyse",
    "alerte": "Alerte sécurité",
    "autre": "Autre",
}

MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def date_fr(d: date) -> str:
    return f"{d.day}{'er' if d.day == 1 else ''} {MOIS_FR[d.month - 1]} {d.year}"


def load_issues() -> list[dict]:
    issues = []
    for path in sorted((CONTENT / "issues").glob("*.yaml")):
        issue = yaml.safe_load(path.read_text(encoding="utf-8"))
        d = issue["date"]
        if not isinstance(d, date):
            d = datetime.strptime(str(d), "%Y-%m-%d").date()
        issue["date"] = d
        issue["date_fr"] = date_fr(d)
        issue["slug"] = d.isoformat()
        for item in issue.get("items", []):
            if item.get("type") not in TYPE_LABELS:
                item["type"] = "autre"
        issues.append(issue)
    issues.sort(key=lambda i: i["date"], reverse=True)
    return issues


VEILLE_SECTIONS = {
    "reco": "Recommandations, guidelines et consensus",
    "essai": "Essais randomisés — grandes revues",
}


def load_veille() -> dict | None:
    """Dernier brouillon PubMed (content/drafts/), pour la page veille."""
    drafts = sorted((CONTENT / "drafts").glob("*-brouillon.yaml"))
    if not drafts:
        return None
    draft = yaml.safe_load(drafts[-1].read_text(encoding="utf-8"))
    sections = [
        {"titre": titre, "docs": draft["candidats"].get(cle, [])}
        for cle, titre in VEILLE_SECTIONS.items()
        if draft["candidats"].get(cle)
    ]
    if not sections:
        return None
    d = datetime.strptime(str(draft["genere_le"]), "%Y-%m-%d").date()
    return {
        "date_fr": date_fr(d),
        "periode_jours": draft.get("periode_jours", 7),
        "total": sum(len(s["docs"]) for s in sections),
        "sections": sections,
    }


def build_rss(issues: list[dict]) -> str:
    entries = []
    for issue in issues:
        titles = "; ".join(item["titre"] for item in issue.get("items", []))
        entries.append(
            "<item>"
            "<title>"
            + html.escape(f"N° {issue['numero']} — semaine du {issue['semaine']}")
            + "</title>"
            f"<link>{SITE_URL}/numeros/{issue['slug']}.html</link>"
            f"<guid isPermaLink=\"false\">thisweek-{issue['slug']}</guid>"
            f"<pubDate>{issue['date'].strftime('%a, %d %b %Y')} 08:00:00 +0100</pubDate>"
            f"<description>{html.escape(titles)}</description>"
            "</item>"
        )
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>ThisWeek · Médecine interne</title>"
        f"<link>{SITE_URL}</link>"
        "<description>Chaque semaine, l'essentiel des nouvelles recommandations, PNDS et "
        "articles majeurs pour les médecins internistes.</description>"
        "<language>fr</language>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        + "".join(entries)
        + "</channel></rss>"
    )


def main() -> None:
    env = Environment(
        loader=FileSystemLoader(ROOT / "site" / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    css = (ROOT / "site" / "static" / "style.css").read_text(encoding="utf-8")
    issues = load_issues()
    if not issues:
        raise SystemExit("Aucun numéro dans content/issues/ — rien à construire.")

    latest_slug = issues[0]["slug"]
    env.globals["latest_slug"] = latest_slug

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "numeros").mkdir(parents=True)

    issue_tpl = env.get_template("issue.html")
    for issue in issues:
        page = issue_tpl.render(
            issue=issue, type_labels=TYPE_LABELS, css=css, root="../", active="dernier"
        )
        (DIST / "numeros" / f"{issue['slug']}.html").write_text(page, encoding="utf-8")

    home = env.get_template("accueil.html").render(
        latest=issues[0], css=css, root="", active="accueil", page_class="page-wide"
    )
    (DIST / "index.html").write_text(home, encoding="utf-8")

    archives = env.get_template("archives.html").render(
        issues=issues, css=css, root="", active="archives"
    )
    (DIST / "archives.html").write_text(archives, encoding="utf-8")

    veille = env.get_template("veille.html").render(
        veille=load_veille(), css=css, root="", active="veille"
    )
    (DIST / "veille.html").write_text(veille, encoding="utf-8")

    methode_md = (CONTENT / "methode.md").read_text(encoding="utf-8")
    methode = env.get_template("page.html").render(
        page_title="Méthode",
        body=markdown.markdown(methode_md),
        css=css,
        root="",
        active="methode",
    )
    (DIST / "methode.html").write_text(methode, encoding="utf-8")

    (DIST / "rss.xml").write_text(build_rss(issues), encoding="utf-8")

    n_pages = len(list(DIST.rglob("*.html"))) + 1
    print(f"✓ {len(issues)} numéro(s), {n_pages} fichiers générés dans {DIST.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
