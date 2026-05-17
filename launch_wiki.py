"""
launch_wiki.py — One-click Wiki Launcher for Compliance Gap Analyser

Generates the wiki documentation and opens it in the browser.
Installs mkdocs-material if not already installed.

Usage:
    python launch_wiki.py              # Generate and open wiki
    python launch_wiki.py --no-open    # Generate only, don't open
    python launch_wiki.py --html-only  # Generate standalone HTML only
    python launch_wiki.py --mkdocs     # Generate MkDocs site only

Author: Compliance Gap Analyser
Last Updated: 2026-05-18
"""

import subprocess
import sys
import webbrowser
from pathlib import Path

# Fix Unicode output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

PROJECT_ROOT = Path(__file__).parent


def _ensure_mkdocs_material() -> bool:
    """Ensure mkdocs-material is installed."""
    try:
        import mkdocs_material  # noqa: F401
        return True
    except ImportError:
        print("⚠️  mkdocs-material not found. Installing...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "mkdocs-material", "-q"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✅ mkdocs-material installed.")
            return True
        else:
            print(f"❌ Failed to install mkdocs-material: {result.stderr}")
            return False


def generate_wiki(html_only: bool = False) -> bool:
    """Generate wiki documentation via build_wiki.py."""
    print("\n" + "=" * 60)
    print("Generating Wiki Documentation")
    print("=" * 60)

    cmd = [sys.executable, str(PROJECT_ROOT / "build_wiki.py")]
    if html_only:
        cmd.append("--html")
    else:
        cmd.append("--both")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


def open_wiki() -> None:
    """Open the generated wiki in the browser."""
    # Try MkDocs site first
    wiki_site = PROJECT_ROOT / "wiki_site" / "index.html"
    if wiki_site.exists():
        webbrowser.open(wiki_site.as_uri())
        print(f"\n🌐 Opened MkDocs wiki: {wiki_site}")
        return

    # Fallback to standalone HTML
    wiki_html = PROJECT_ROOT / "wiki_build" / "wiki_standalone.html"
    if wiki_html.exists():
        webbrowser.open(wiki_html.as_uri())
        print(f"\n🌐 Opened standalone wiki: {wiki_html}")
        return

    print("\n⚠️  Wiki not found. Run: python launch_wiki.py")


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Launch the Compliance Gap Analyser wiki")
    parser.add_argument(
        "--no-open", action="store_true", help="Generate wiki but don't open in browser"
    )
    parser.add_argument("--html-only", action="store_true", help="Generate standalone HTML only")
    parser.add_argument(
        "--mkdocs", action="store_true", help="Generate MkDocs site (requires mkdocs-material)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Compliance Gap Analyser — Wiki Launcher")
    print("=" * 60)

    # Generate wiki
    if args.mkdocs:
        if not _ensure_mkdocs_material():
            print("\nCannot generate MkDocs site without mkdocs-material.")
            print("Install with: pip install mkdocs mkdocs-material")
            return 1
        result = generate_wiki(html_only=False)
    else:
        result = generate_wiki(html_only=args.html_only)

    if not result:
        print("\n❌ Wiki generation failed.")
        return 1

    # Open in browser
    if not args.no_open:
        open_wiki()

    print("\n" + "=" * 60)
    print("Wiki generation complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  - View wiki: python launch_wiki.py")
    print("  - Update wiki: python build_wiki.py --both")
    print("  - Serve MkDocs locally: mkdocs serve")
    print("  - Deploy MkDocs to GitHub Pages: mkdocs gh-deploy")

    return 0


if __name__ == "__main__":
    sys.exit(main())
