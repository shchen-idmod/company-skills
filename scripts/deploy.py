#!/usr/bin/env python3
"""Deploy company skills to their native distribution channels.

Two channels, both fed from this one repo:

  - claude_code : skills ship via this repo's plugin marketplace. There is no
                  upload step on our side; `git push` publishes. This deploy
                  step is a validation gate (folder exists + registered in
                  marketplace.json).

  - claude_ai   : skills ship as one .zip per skill, uploaded by an org owner
                  in Claude.ai > Organization settings > Skills. This deploy
                  step builds the zip into dist/.

It can also generate a static, human-facing catalog (site/index.html) that
lists every skill grouped by scope (org-wide vs. team plugins). The catalog is
a read-only reference for people — it does NOT serve skills to Claude. Host it
on GitHub Pages; it regenerates from the repo so it never drifts from what is
actually published.

Usage:
    python scripts/deploy.py [--dry-run] [--channel claude_code|claude_ai|all]
                             [--skill NAME ...]
    python scripts/deploy.py --catalog          # build site/index.html
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
DIST = ROOT / "dist"
SITE = ROOT / "site"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


@dataclass
class DeployResult:
    name: str
    channel: str
    ok: bool
    detail: str


# --------------------------------------------------------------------------- #
# Manifest helpers
# --------------------------------------------------------------------------- #
def load_registered_skills() -> set[str]:
    """Return the set of skill names listed in marketplace.json."""
    manifest = json.loads(MARKETPLACE.read_text())
    return {
        Path(p).name
        for plugin in manifest.get("plugins", [])
        for p in plugin.get("skills", [])
    }


def discover_skills() -> list[str]:
    """All skill folders on disk that contain a SKILL.md."""
    return sorted(
        d.name for d in SKILLS.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    )


def read_frontmatter(skill_name: str) -> dict:
    """Parse the YAML-ish frontmatter at the top of a SKILL.md.

    Only needs name/description, so we do a tiny line parser rather than pull
    in a YAML dependency. Returns {} if there is no frontmatter block.
    """
    text = (SKILLS / skill_name / "SKILL.md").read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta


def load_plugins() -> list[dict]:
    """Plugins from the manifest, each with name, scope, description, skills."""
    manifest = json.loads(MARKETPLACE.read_text())
    return manifest.get("plugins", [])


# --------------------------------------------------------------------------- #
# Channel: Claude Code  (validation gate — git is the transport)
# --------------------------------------------------------------------------- #
def deploy_claude_code(entry: dict, dry_run: bool) -> DeployResult:
    name = entry["name"]
    skill_md = SKILLS / name / "SKILL.md"

    if not skill_md.is_file():
        return DeployResult(name, "claude_code", False,
                            f"missing {skill_md.relative_to(ROOT)}")

    try:
        registered = load_registered_skills()
    except (OSError, json.JSONDecodeError) as exc:
        return DeployResult(name, "claude_code", False,
                            f"cannot read marketplace.json: {exc}")

    if name not in registered:
        return DeployResult(name, "claude_code", False,
                            f"not listed in marketplace.json")

    if dry_run:
        return DeployResult(name, "claude_code", True,
                            "valid + registered; `git push` to publish")
    return DeployResult(name, "claude_code", True,
                        "ready; publish with `git push`")


# --------------------------------------------------------------------------- #
# Channel: Claude.ai  (build a .zip for admin upload)
# --------------------------------------------------------------------------- #
def deploy_claude_ai(entry: dict, dry_run: bool) -> DeployResult:
    name = entry["name"]
    skill_dir = SKILLS / name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.is_file():
        return DeployResult(name, "claude_ai", False,
                            f"missing {skill_md.relative_to(ROOT)}")

    zip_path = DIST / f"{name}.zip"
    rel = zip_path.relative_to(ROOT)

    if dry_run:
        return DeployResult(name, "claude_ai", True,
                            f"dry-run: would build {rel}")

    DIST.mkdir(exist_ok=True)
    # Zip the folder so SKILL.md sits inside <name>/ within the archive,
    # matching what Claude.ai expects on upload.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(skill_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(SKILLS))

    return DeployResult(name, "claude_ai", True,
                        f"built {rel} — upload via Organization settings")


# --------------------------------------------------------------------------- #
# Catalog (static, human-facing reference — NOT a runtime skill server)
# --------------------------------------------------------------------------- #
def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def list_bundled_files(skill_name: str) -> list[Path]:
    """Files inside a skill folder other than SKILL.md, relative to the folder.

    Returns sorted relative paths so nested files (scripts/foo.py) display
    correctly. Empty when the skill is instruction-only.
    """
    skill_dir = SKILLS / skill_name
    return sorted(
        f.relative_to(skill_dir)
        for f in skill_dir.rglob("*")
        if f.is_file() and f.name != "SKILL.md"
    )


def build_catalog(dry_run: bool, repo_url: str | None = None) -> DeployResult:
    out = SITE / "index.html"
    rel = out.relative_to(ROOT)

    try:
        plugins = load_plugins()
    except (OSError, json.JSONDecodeError) as exc:
        return DeployResult("catalog", "catalog", False,
                            f"cannot read marketplace.json: {exc}")

    total = sum(len(p.get("skills", [])) for p in plugins)
    if dry_run:
        return DeployResult("catalog", "catalog", True,
                            f"dry-run: would write {rel} "
                            f"({len(plugins)} plugins, {total} skills)")

    # Base for "view file" links. If repo_url is given (e.g.
    # https://github.com/org/company-skills), link into blob/main; otherwise
    # fall back to a relative path so links still resolve when the repo is
    # served statically alongside the site.
    def file_link(skill_name: str, relpath: Path) -> str:
        p = f"skills/{skill_name}/{relpath.as_posix()}"
        if repo_url:
            return f"{repo_url.rstrip('/')}/blob/main/{p}"
        return f"../{p}"

    cards = []
    for plugin in plugins:
        scope = plugin.get("scope", "unspecified")
        badge = "org-wide" if scope == "org-wide" else scope
        rows = []
        for path in plugin.get("skills", []):
            sname = Path(path).name
            meta = read_frontmatter(sname)
            desc = meta.get("description", "(no description)")

            files = list_bundled_files(sname)
            files_html = ""
            if files:
                items = "".join(
                    f'<li><a href="{_html_escape(file_link(sname, f))}">'
                    f'{_html_escape(f.as_posix())}</a></li>'
                    for f in files
                )
                files_html = (
                    f'<div class="files"><span class="files-label">'
                    f'{len(files)} bundled file(s):</span><ul>{items}</ul></div>'
                )

            rows.append(
                f'<div class="skill"><div class="skill-name">{_html_escape(sname)}</div>'
                f'<div class="skill-desc">{_html_escape(desc)}</div>'
                f'{files_html}</div>'
            )
        cards.append(
            f'<section class="plugin"><h2>{_html_escape(plugin.get("name", "?"))}'
            f'<span class="badge">{_html_escape(badge)}</span></h2>'
            f'<p class="plugin-desc">{_html_escape(plugin.get("description", ""))}</p>'
            f'{"".join(rows)}</section>'
        )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Company Skills Catalog</title>
<style>
  :root {{ --accent:#2E75B6; --ink:#1f1f1f; --muted:#595959; --line:#e3e3e3; }}
  * {{ box-sizing:border-box; }}
  body {{ font:16px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;
          color:var(--ink); max-width:880px; margin:0 auto; padding:40px 20px; }}
  header h1 {{ margin:0 0 4px; font-size:30px; }}
  header p {{ margin:0 0 8px; color:var(--muted); }}
  .note {{ background:#f4f7fb; border-left:3px solid var(--accent);
           padding:10px 14px; font-size:14px; color:var(--muted); border-radius:4px; }}
  .plugin {{ margin:32px 0; }}
  .plugin h2 {{ font-size:20px; color:var(--accent); border-bottom:2px solid var(--accent);
                padding-bottom:6px; display:flex; align-items:center; gap:10px; }}
  .badge {{ font-size:12px; font-weight:600; color:#fff; background:var(--accent);
            padding:2px 8px; border-radius:10px; text-transform:uppercase; letter-spacing:.04em; }}
  .plugin-desc {{ color:var(--muted); margin:8px 0 16px; }}
  .skill {{ border:1px solid var(--line); border-radius:6px; padding:12px 14px; margin:8px 0; }}
  .skill-name {{ font-weight:600; font-family:ui-monospace,Consolas,monospace; }}
  .skill-desc {{ color:var(--muted); font-size:14px; margin-top:4px; }}
  .files {{ margin-top:10px; padding-top:8px; border-top:1px dashed var(--line); }}
  .files-label {{ font-size:12px; font-weight:600; color:var(--muted);
                  text-transform:uppercase; letter-spacing:.03em; }}
  .files ul {{ margin:6px 0 0; padding-left:18px; }}
  .files li {{ font-family:ui-monospace,Consolas,monospace; font-size:13px; margin:2px 0; }}
  .files a {{ color:var(--accent); text-decoration:none; }}
  .files a:hover {{ text-decoration:underline; }}
  footer {{ margin-top:40px; color:var(--muted); font-size:13px;
            border-top:1px solid var(--line); padding-top:12px; }}
</style></head>
<body>
<header>
  <h1>Company Skills Catalog</h1>
  <p>{total} skills across {len(plugins)} plugin(s). Generated from the
     source-of-truth repository.</p>
  <p class="note">This page is a human reference only. Claude receives these
     skills through the plugin marketplace (Claude Code) and admin-provisioned
     skills (Claude.ai), not from this site.</p>
</header>
{"".join(cards)}
<footer>Regenerate with <code>python scripts/deploy.py --catalog</code>.</footer>
</body></html>
"""

    SITE.mkdir(exist_ok=True)
    out.write_text(html)
    return DeployResult("catalog", "catalog", True,
                        f"wrote {rel} ({len(plugins)} plugins, {total} skills)")


# --------------------------------------------------------------------------- #
# Orchestration + CLI
# --------------------------------------------------------------------------- #
CHANNELS = {
    "claude_code": deploy_claude_code,
    "claude_ai": deploy_claude_ai,
}


def run(channels: list[str], skills: list[str], dry_run: bool) -> list[DeployResult]:
    results: list[DeployResult] = []
    for name in skills:
        entry = {"name": name}
        for ch in channels:
            results.append(CHANNELS[ch](entry, dry_run))
    return results


def print_table(results: list[DeployResult]) -> None:
    if not results:
        print("No skills to deploy.")
        return
    w_name = max(len("SKILL"), max(len(r.name) for r in results))
    w_chan = max(len("CHANNEL"), max(len(r.channel) for r in results))
    header = f"{'SKILL':<{w_name}}  {'CHANNEL':<{w_chan}}  STATUS  DETAIL"
    print(header)
    print("-" * len(header))
    for r in results:
        status = " OK " if r.ok else "FAIL"
        print(f"{r.name:<{w_name}}  {r.channel:<{w_chan}}  [{status}] {r.detail}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deploy company skills.")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would happen without writing anything")
    p.add_argument("--channel", choices=[*CHANNELS, "all"], default="all")
    p.add_argument("--skill", action="append", dest="skills",
                   help="deploy only this skill (repeatable); default: all")
    p.add_argument("--catalog", action="store_true",
                   help="build the static human-facing catalog (site/index.html) and exit")
    p.add_argument("--repo-url",
                   help="repo base URL (e.g. https://github.com/org/company-skills); "
                        "makes bundled-file links point at GitHub")
    args = p.parse_args(argv)

    if args.catalog:
        result = build_catalog(args.dry_run, args.repo_url)
        print_table([result])
        return 0 if result.ok else 1

    channels = list(CHANNELS) if args.channel == "all" else [args.channel]
    skills = args.skills or discover_skills()

    results = run(channels, skills, args.dry_run)
    print_table(results)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())