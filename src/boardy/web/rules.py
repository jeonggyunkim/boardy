"""Renders the plain-Markdown rulebooks under docs/ as a themed HTML page.

Kept intentionally small: the rulebooks only use headers, bold, bulleted/
numbered lists, and one table, so a full Markdown library would be
overkill. Content lives in one place (docs/*.md, meant to be human-read
as plain Markdown too) and this just converts it for the in-browser link.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "docs"

# slug (matches GameSpec.slug) -> rulebook filename under docs/
RULEBOOKS = {
    "deep_sea_crew": "deep_sea_crew_rules.md",
    "gomoku": "gomoku_rules.md",
}

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ORDERED_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def _inline(text: str) -> str:
    return _BOLD_RE.sub(r"<strong>\1</strong>", html.escape(text))


def render_markdown(text: str) -> str:
    # Two passes: first group raw (still-unescaped) lines into blocks, with
    # a wrapped continuation line simply appended to the current block's
    # raw text -- then render each block's *complete* raw text through
    # _inline() once. Doing the inline conversion line-by-line instead
    # would break **bold** spans that happen to wrap across a line, since
    # each half would be missing its matching ** marker.
    blocks: list[tuple[str, object]] = []  # (kind, payload)

    def current_is(kind: str) -> bool:
        return bool(blocks) and blocks[-1][0] == kind

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        if not stripped:
            blocks.append(("blank", None))
            continue

        header = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if header:
            blocks.append(("h" + str(len(header.group(1))), header.group(2)))
            continue

        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r"-+", c) for c in cells):
                continue  # header/body separator row
            if current_is("table"):
                blocks[-1][1].append(cells)  # type: ignore[union-attr]
            else:
                blocks.append(("table", [cells]))
            continue

        if stripped.startswith("- "):
            blocks.append(("ul_item", stripped[2:]))
            continue

        ordered = _ORDERED_RE.match(stripped)
        if ordered:
            blocks.append(("ol_item", ordered.group(2)))
            continue

        # continuation line (wrapped list item or paragraph) or the start
        # of a fresh paragraph.
        if current_is("ul_item") or current_is("ol_item") or current_is("para"):
            kind, prev_text = blocks[-1]
            blocks[-1] = (kind, f"{prev_text} {stripped}")
        else:
            blocks.append(("para", stripped))

    out: list[str] = []
    open_list: str | None = None  # "ul" | "ol" | None

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            out.append(f"</{open_list}>")
            open_list = None

    for kind, payload in blocks:
        if kind == "blank":
            close_list()
            continue
        if kind in ("h1", "h2", "h3"):
            close_list()
            out.append(f"<{kind}>{_inline(payload)}</{kind}>")
        elif kind == "para":
            close_list()
            out.append(f"<p>{_inline(payload)}</p>")
        elif kind == "table":
            close_list()
            rows = payload
            out.append("<table>")
            for i, cells in enumerate(rows):
                tag = "th" if i == 0 else "td"
                out.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells) + "</tr>")
            out.append("</table>")
        elif kind in ("ul_item", "ol_item"):
            want = "ul" if kind == "ul_item" else "ol"
            if open_list != want:
                close_list()
                out.append(f"<{want}>")
                open_list = want
            out.append(f"<li>{_inline(payload)}</li>")

    close_list()
    return "\n".join(out)


def render_rulebook_page(slug: str) -> str | None:
    """Full standalone HTML page for `slug`'s rulebook, or None if it has none."""
    filename = RULEBOOKS.get(slug)
    if filename is None:
        return None
    path = DOCS_DIR / filename
    if not path.exists():
        return None
    body = render_markdown(path.read_text(encoding="utf-8"))
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Boardy — 규칙</title>
<link rel="stylesheet" href="/style.css">
<style>
  .rulebook {{ max-width: 700px; }}
  .rulebook h1 {{ font-size: 1.5rem; }}
  .rulebook h2 {{ font-size: 1.15rem; margin-top: 1.6rem; border-bottom: 1px solid #244; padding-bottom: 0.3rem; }}
  .rulebook table {{ border-collapse: collapse; margin: 0.6rem 0; }}
  .rulebook th, .rulebook td {{ border: 1px solid #244; padding: 0.4rem 0.6rem; text-align: left; }}
  .rulebook li {{ margin: 0.2rem 0; }}
  .back-link {{ display: inline-block; margin-bottom: 1rem; }}
</style>
</head>
<body>
<a class="back-link" href="/">← Boardy로 돌아가기</a>
<div class="rulebook">
{body}
</div>
</body>
</html>
"""
