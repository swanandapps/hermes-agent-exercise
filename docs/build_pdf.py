#!/usr/bin/env python3
"""Render a docs/*.md file to PDF for presenting.

    python docs/build_pdf.py docs/hermes-vs-langchain.md

GitHub's Markdown rendering is fine for reading in a browser and poor for handing to
someone in a meeting — the tables in the comparison doc carry most of its meaning and
they need real typography to be legible. Chrome is used as the renderer because it is
already on any machine that runs the UI, so this needs no extra toolchain.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 11mm 12mm 10mm 12mm; }

:root {
  --ink:        #16181d;
  --ink-soft:   #5b6472;
  --rule:       #d7dbe2;
  --rule-soft:  #eaedf1;
  --accent:     #0d5c9c;
  --hermes-bg:  #f4f8fb;
  --code-bg:    #f2f3f5;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: "Charter", "Iowan Old Style", Georgia, serif;
  font-size: 8.6pt;
  line-height: 1.40;
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}

h1 {
  font-family: "Helvetica Neue", Arial, sans-serif;
  font-size: 17.5pt;
  line-height: 1.1;
  letter-spacing: -0.015em;
  margin: 0 0 2mm;
  color: var(--ink);
}

h2 {
  font-family: "Helvetica Neue", Arial, sans-serif;
  font-size: 10pt;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 4mm 0 1.6mm;
  padding-bottom: 0.8mm;
  border-bottom: 1px solid var(--rule);
  break-after: avoid;
}

p { margin: 0 0 2mm; }
strong { font-weight: 600; }
em { color: var(--ink-soft); }

a { color: var(--accent); text-decoration: none; }

/* The lead-in block: framing and provenance, deliberately quiet. */
blockquote {
  margin: 0 0 3mm;
  padding: 2mm 0 2mm 3.5mm;
  border-left: 2px solid var(--rule);
  color: var(--ink-soft);
  font-size: 8.2pt;
  line-height: 1.45;
}
blockquote p { margin: 0 0 1.2mm; }
blockquote p:last-child { margin: 0; }

/* The closing recommendation reads as a pull-quote, not an aside. */
h2 + blockquote {
  border-left: 2px solid var(--accent);
  background: var(--hermes-bg);
  color: var(--ink);
  font-size: 9.2pt;
  padding: 3mm 4mm;
}

code {
  font-family: "SF Mono", "JetBrains Mono", Menlo, monospace;
  font-size: 0.86em;
  background: var(--code-bg);
  padding: 0.5mm 1mm;
  border-radius: 2px;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 3.5mm;
  font-size: 8.5pt;
  line-height: 1.42;
  break-inside: auto;
}

th {
  font-family: "Helvetica Neue", Arial, sans-serif;
  font-size: 8pt;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  text-align: left;
  color: var(--ink-soft);
  border-bottom: 1.2px solid var(--ink);
  padding: 1.5mm 2.5mm;
}

td {
  padding: 1.0mm 2.2mm;
  border-bottom: 1px solid var(--rule-soft);
  vertical-align: top;
}

/* The two tables want different proportions. The dimensions table gives its prose columns
   the room; the practice table needs a label column wide enough that "Sessions surviving a
   restart" does not wrap to three lines and triple the row height. */
table:nth-of-type(1) th:first-child { width: 14%; }
table:nth-of-type(1) th:nth-child(2), table:nth-of-type(1) th:nth-child(3) { width: 43%; }
table:nth-of-type(2) th:first-child { width: 26%; }
table:nth-of-type(2) th:nth-child(2), table:nth-of-type(2) th:nth-child(3) { width: 37%; }
/* The job table's middle column holds one word — give it just enough not to wrap its heading. */
table:nth-of-type(3) th:first-child { width: 33%; }
table:nth-of-type(3) th:nth-child(2) { width: 13%; white-space: nowrap; }
table:nth-of-type(3) th:nth-child(3) { width: 54%; }

/* Hermes column tinted, so the eye tracks one framework down the page. */
td:nth-child(2) { background: var(--hermes-bg); }

/* A row whose first cell is empty is the italic gloss on the row above it —
   pull it tight to its parent and mute it. */
tr td:first-child:empty ~ td { padding-top: 0; font-size: 8pt; color: var(--ink-soft); }
tr td:first-child:empty { border-bottom: 1px solid var(--rule-soft); }
tr:has(td:first-child:empty) td { border-top: none; }
tr:not(:has(td:first-child:empty)) td { border-bottom: none; }

hr { display: none; }

/* Break before "Which one for which job" so that table stays whole. Splitting a table across
   a page is worse than a slightly shorter first page: the reader loses the column headings
   mid-comparison, which is the one thing a comparison table cannot afford. Page one then
   carries the framing and both required tables; page two carries the recommendation. */
h2:nth-of-type(3) { break-before: page; margin-top: 0; }
tr, h1, h2 { break-inside: avoid; }
"""


def build(md_path: Path) -> Path:
    html_body = markdown.markdown(
        md_path.read_text(),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    html = (
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>{md_path.stem}</title><style>{CSS}</style>{html_body}"
    )
    tmp_html = md_path.with_suffix(".build.html")
    tmp_html.write_text(html)
    pdf = md_path.with_suffix(".pdf")
    try:
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf}", tmp_html.resolve().as_uri()],
            check=True, capture_output=True, timeout=120,
        )
    finally:
        tmp_html.unlink(missing_ok=True)
    return pdf


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python docs/build_pdf.py docs/<file>.md")
    for arg in sys.argv[1:]:
        out = build(Path(arg))
        print(f"  {out}  ({out.stat().st_size // 1024} KB)")
