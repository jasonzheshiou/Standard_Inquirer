"""
build_wiki.py — Wiki Generator for Compliance Gap Analyser

Generates both:
1. Standalone HTML wiki (wiki_build/wiki_standalone.html)
2. MkDocs-based searchable documentation (wiki_site/)

Usage:
    python build_wiki.py                    # Generate standalone HTML
    python build_wiki.py --mkdocs           # Generate MkDocs site
    python build_wiki.py --both             # Generate both (default)
    python build_wiki.py --open             # Open in browser after generation

Author: Compliance Gap Analyser
Last Updated: 2026-05-13
"""

import os
import sys
import webbrowser
import subprocess
import json
from pathlib import Path
from datetime import datetime
from argparse import ArgumentParser

# Fix Unicode output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
WIKI_DIR = PROJECT_ROOT / "wiki_build"
WIKI_SITE_DIR = PROJECT_ROOT / "wiki_site"
WIKI_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Compliance registry data (scanned from project data files)
# ---------------------------------------------------------------------------

IMPLEMENTED_STANDARDS = [
    {
        "name": "APRA CPS 230",
        "category": "Operational Risk",
        "status": "implemented",
        "rules": 8,
        "questions": 8,
        "url": "https://www.apra.gov.au/prudential-standards/cps-230",
    }
]

PLANNED_STANDARDS = [
    {"name": "APRA CPS 220", "category": "Risk Management", "status": "planned"},
    {"name": "APRA CPS 510", "category": "Governance", "status": "planned"},
    {"name": "APRA LPS 110", "category": "Capital Adequacy", "status": "planned"},
    {"name": "APRA LPS 220", "category": "Risk Management (Life)", "status": "planned"},
    {"name": "AI PS 200", "category": "Life Insurance Valuation", "status": "planned"},
    {"name": "AI PS 300", "category": "Actuarial Reporting", "status": "planned"},
    {"name": "AI PS 400", "category": "Model Governance", "status": "planned"},
]

IMPLEMENTED_RULES = [
    {"id": "CPS230-6", "clause": "Paragraph 6", "category": "Board Oversight", "severity": "High"},
    {"id": "CPS230-27b", "clause": "Paragraph 27(b)", "category": "Board Oversight", "severity": "High"},
    {"id": "CPS230-22", "clause": "Paragraph 22", "category": "Model Validation", "severity": "High"},
    {"id": "CPS230-30", "clause": "Paragraph 30", "category": "Risk Escalation", "severity": "High"},
    {"id": "CPS230-21", "clause": "Paragraph 21", "category": "Model Inventory", "severity": "Medium"},
    {"id": "CPS230-27", "clause": "Paragraph 27", "category": "Data Governance", "severity": "Medium"},
    {"id": "CPS230-28", "clause": "Paragraph 28", "category": "Documentation", "severity": "Medium"},
    {"id": "CPS230-29", "clause": "Paragraph 29", "category": "Risk Management", "severity": "Medium"},
]


def _status_icon(status: str) -> str:
    return {"implemented": "✅", "planned": "🔲", "in_progress": "🚧"}.get(status, "🔲")


def _rule_severity_icon(severity: str) -> str:
    return {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(severity, "")


def generate_standalone_html() -> Path:
    """Generate standalone HTML wiki."""
    print("=" * 60)
    print("Generating Standalone HTML Wiki")
    print("=" * 60)

    # Build compliance registry table
    registry_rows = ""
    for s in IMPLEMENTED_STANDARDS:
        icon = _status_icon(s["status"])
        registry_rows += f'<tr><td><strong>{s["name"]}</strong></td><td>{s["category"]}</td><td>{icon} Implemented</td><td>{s["rules"]}</td><td>{s["questions"]}</td><td><a href="{s["url"]}">Link</a></td></tr>\n'
    for s in PLANNED_STANDARDS:
        icon = _status_icon(s["status"])
        registry_rows += f'<tr><td><strong>{s["name"]}</strong></td><td>{s["category"]}</td><td>{icon} Planned</td><td>—</td><td>—</td><td>—</td></tr>\n'

    # Build implemented rules table
    rules_rows = ""
    for r in IMPLEMENTED_RULES:
        icon = _rule_severity_icon(r["severity"])
        rules_rows += f'<tr><td><code>{r["id"]}</code></td><td>{r["clause"]}</td><td>{r["category"]}</td><td>{icon} {r["severity"]}</td></tr>\n'

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Compliance Gap Analyser — Wiki</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6; color: #333; background: #f5f5f5;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
            color: white; padding: 40px 20px; text-align: center;
        }}
        .header h1 {{ font-size: 2.2rem; margin-bottom: 10px; }}
        .header p {{ font-size: 1.1rem; opacity: 0.9; }}
        .toc {{
            background: white; padding: 30px; margin: 20px 0; border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .toc h2 {{ color: #1e3a5f; margin-bottom: 15px; border-bottom: 2px solid #2563eb; padding-bottom: 5px; }}
        .toc ul {{ list-style: none; }}
        .toc li {{ margin: 8px 0; }}
        .toc a {{ color: #2563eb; text-decoration: none; }}
        .toc a:hover {{ text-decoration: underline; }}
        .section {{
            background: white; padding: 30px; margin: 20px 0; border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .section h2 {{ color: #1e3a5f; margin-bottom: 20px; border-left: 4px solid #2563eb; padding-left: 15px; }}
        .section h3 {{ color: #2563eb; margin: 20px 0 10px 0; }}
        .section p {{ margin: 10px 0; }}
        .section ul {{ margin: 10px 0 10px 20px; }}
        .section li {{ margin: 5px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ border: 1px solid #e1e4e8; padding: 10px; text-align: left; }}
        th {{ background: #f0f4f8; font-weight: 600; }}
        tr:nth-child(even) {{ background: #f8f9fa; }}
        .code {{ background: #f6f8fa; padding: 15px; border-radius: 5px; overflow-x: auto; margin: 10px 0; }}
        .code code {{ font-family: 'Courier New', monospace; font-size: 0.9em; }}
        .note {{
            background: #fff3cd; border-left: 4px solid #ffc107;
            padding: 15px; margin: 15px 0; border-radius: 5px;
        }}
        .warning {{
            background: #f8d7da; border-left: 4px solid #dc3545;
            padding: 15px; margin: 15px 0; border-radius: 5px;
        }}
        .footer {{
            text-align: center; padding: 20px; color: #5a6d82;
            border-top: 1px solid #e1e4e8; margin-top: 40px;
        }}
        .badge {{
            display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 0.85em; font-weight: 600;
        }}
        .badge-high {{ background: #fee2e2; color: #dc2626; }}
        .badge-medium {{ background: #fef3c7; color: #d97706; }}
        .badge-low {{ background: #d1fae5; color: #059669; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ Compliance Gap Analyser</h1>
        <p>Australian Life Insurance Model Governance Gap Analysis</p>
        <p>Generated: {timestamp}</p>
    </div>

    <div class="container">
        <div class="toc">
            <h2>Quick Links</h2>
            <ul>
                <li><a href="#compliance-registry">Compliance Registry</a></li>
                <li><a href="#implemented-rules">Implemented Rules</a></li>
                <li><a href="#getting-started">Getting Started</a></li>
                <li><a href="#architecture">Architecture</a></li>
                <li><a href="#api">API Reference</a></li>
            </ul>
        </div>

        <div class="section" id="compliance-registry">
            <h2>Compliance Registry</h2>
            <p><strong>Status Legend:</strong> ✅ Implemented &middot; 🔲 Planned</p>
            <table>
                <tr>
                    <th>Standard</th><th>Category</th><th>Status</th>
                    <th>Rules</th><th>Questions</th><th>Source</th>
                </tr>
                {registry_rows}
            </table>
        </div>

        <div class="section" id="implemented-rules">
            <h2>Implemented: APRA CPS 230 — Gap Rules</h2>
            <p>The following <strong>8 gap rules</strong> are currently implemented for CPS 230:</p>
            <table>
                <tr>
                    <th>Rule ID</th><th>Clause</th><th>Category</th><th>Severity</th>
                </tr>
                {rules_rows}
            </table>
        </div>

        <div class="section" id="getting-started">
            <h2>Getting Started</h2>
            <h3>Installation</h3>
            <div class="code"><code>pip install -e ".[dev]"</code></div>
            <h3>Running the App</h3>
            <div class="code"><code>streamlit run app.py</code></div>
            <h3>Running the Ingestion Pipeline</h3>
            <div class="code"><code>python -m scripts.run_ingestion</code></div>
            <h3>Generating This Wiki</h3>
            <div class="code"><code>python build_wiki.py --both</code><br><code>mkdocs build</code></div>
        </div>

        <div class="section" id="architecture">
            <h2>Architecture</h2>
            <p>The system consists of four main components:</p>
            <ol>
                <li><strong>Streamlit UI</strong> — Multi-page interface (Home, Questionnaire, Report, Admin)</li>
                <li><strong>Gap Analysis Engine</strong> — Deterministic rule evaluation from JSON rules</li>
                <li><strong>Vector Knowledge Base</strong> — ChromaDB with embedded standards chunks</li>
                <li><strong>Standards Ingestion Pipeline</strong> — Download, parse, chunk, embed PDFs</li>
            </ol>
        </div>

        <div class="section" id="api">
            <h2>API Reference</h2>
            <h3>Engine Package</h3>
            <table>
                <tr><th>Module</th><th>Key Functions</th></tr>
                <tr><td><code>engine.gap_analyzer</code></td><td><code>analyze()</code>, <code>evaluate_rule()</code>, <code>load_gap_rules()</code></td></tr>
                <tr><td><code>engine.questionnaire</code></td><td><code>load_questionnaire()</code>, <code>get_all_questions()</code>, <code>get_sections()</code></td></tr>
                <tr><td><code>engine.schemas</code></td><td><code>GapRule</code>, <code>Question</code>, <code>GapFinding</code>, <code>Questionnaire</code></td></tr>
            </table>
            <h3>Ingestion Pipeline</h3>
            <table>
                <tr><th>Module</th><th>Key Functions</th></tr>
                <tr><td><code>standards_ingestion.downloader</code></td><td><code>download_source()</code></td></tr>
                <tr><td><code>standards_ingestion.parser</code></td><td><code>extract_text_from_pdf()</code>, <code>chunk_text()</code></td></tr>
                <tr><td><code>standards_ingestion.embedder</code></td><td><code>init_chroma_client()</code>, <code>upsert_documents()</code></td></tr>
            </table>
        </div>

        <div class="warning">
            <strong>⚠️ Disclaimer:</strong> This tool provides <strong>sample guidance only</strong>. All rules, mitigations, and gap conditions must be reviewed by a <strong>qualified actuary</strong> before being relied upon for regulatory compliance.
        </div>

        <div class="footer">
            <p>Compliance Gap Analyser — Wiki</p>
            <p>Generated: {timestamp}</p>
        </div>
    </div>
</body>
</html>"""

    html_file = WIKI_DIR / "wiki_standalone.html"
    html_file.write_text(html, encoding="utf-8")
    print(f"✅ Generated standalone HTML: {html_file}")
    return html_file


def generate_mkdocs() -> bool:
    """Generate MkDocs-based searchable documentation."""
    print("=" * 60)
    print("Generating MkDocs Documentation")
    print("=" * 60)

    try:
        result = subprocess.run(
            ["mkdocs", "build"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        print("✅ Built MkDocs site in wiki_site/")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  MkDocs build failed (install with: pip install mkdocs mkdocs-material)")
        print(f"Error: {e}")
        return False
    except FileNotFoundError:
        print("⚠️  MkDocs not installed. Install with: pip install mkdocs mkdocs-material")
        return False


def open_in_browser(use_mkdocs: bool = True) -> None:
    """Open documentation in browser."""
    if use_mkdocs and WIKI_SITE_DIR.exists():
        file_path = WIKI_SITE_DIR / "index.html"
        if file_path.exists():
            webbrowser.open(file_path.as_uri())
            print(f"🌐 Opened MkDocs site: {file_path}")
            return
    file_path = WIKI_DIR / "wiki_standalone.html"
    if file_path.exists():
        webbrowser.open(file_path.as_uri())
        print(f"🌐 Opened standalone HTML: {file_path}")
    else:
        print("⚠️  HTML file not found. Run: python build_wiki.py")


def main() -> int:
    """Main entry point."""
    parser = ArgumentParser(description="Generate wiki documentation")
    parser.add_argument("--mkdocs", action="store_true", help="Generate MkDocs site only")
    parser.add_argument("--html", action="store_true", help="Generate standalone HTML only")
    parser.add_argument("--both", action="store_true", help="Generate both (default)")
    parser.add_argument("--open", action="store_true", help="Open in browser after generation")

    args = parser.parse_args()

    if args.mkdocs:
        generate_mkdocs()
        if args.open:
            open_in_browser(use_mkdocs=True)
    elif args.html:
        generate_standalone_html()
        if args.open:
            open_in_browser(use_mkdocs=False)
    else:
        print("\nGenerating both standalone HTML and MkDocs documentation...\n")
        generate_standalone_html()
        print()
        generate_mkdocs()
        if args.open:
            open_in_browser(use_mkdocs=True)

    print("\n" + "=" * 60)
    print("Wiki generation complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  - View standalone HTML: wiki_build/wiki_standalone.html")
    print("  - View MkDocs site: wiki_site/index.html")
    print("  - Serve MkDocs locally: mkdocs serve")
    print("  - Update documentation: python build_wiki.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
