#!/usr/bin/env python3
"""Deploy company skills to their native distribution channels.

Repo layout (official Claude Code marketplace format):

    .claude-plugin/
        marketplace.json     # lists plugins by `source` (path to plugin dir)
        scopes.json          # our own Claude.ai scope metadata per plugin
    plugins/
        <plugin>/
            .claude-plugin/plugin.json
            skills/<skill>/SKILL.md

Two channels, both fed from this one repo:

  - claude_code : skills ship via this repo's plugin marketplace. There is no
                  upload step on our side; `git push` publishes. This deploy
                  step is a validation gate (each plugin source exists, has a
                  plugin.json, and its skills have SKILL.md files).

  - claude_ai   : skills ship as one .zip per skill, uploaded by an org owner
                  in Claude.ai > Organization settings > Skills (org-wide), or
                  as a plugin bundle assigned to a group (team-scoped). This
                  step builds the zip(s) into dist/.

It can also generate a static, human-facing catalog (site/index.html) grouped
by plugin/scope. The catalog is a read-only reference — it does NOT serve
skills to Claude. Host it on GitHub Pages; it regenerates from the repo.

Usage:
    python scripts/deploy.py [--dry-run] [--channel claude_code|claude_ai|all]
    python scripts/deploy.py --catalog [--repo-url https://github.com/org/repo]
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
DIST = ROOT / "dist"
SITE = ROOT / "site"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SCOPES = ROOT / ".claude-plugin" / "scopes.json"


@dataclass
class DeployResult:
    name: str
    channel: str
    ok: bool
    detail: str


# --------------------------------------------------------------------------- #
# Manifest / layout helpers
# --------------------------------------------------------------------------- #
def load_plugins() -> list[dict]:
    """Plugin entries from marketplace.json (name, description, source, ...)."""
    manifest = json.loads(MARKETPLACE.read_text())
    return manifest.get("plugins", [])


def load_scopes() -> dict:
    """Plugin-name -> scope string (e.g. 'org-wide', 'group:IDM')."""
    if not SCOPES.is_file():
        return {}
    data = json.loads(SCOPES.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def plugin_dir(plugin: dict) -> Path:
    """Resolve a plugin entry's source to an absolute directory."""
    src = plugin.get("source", "")
    return (ROOT / src).resolve()


def plugin_skill_dirs(plugin: dict) -> list[Path]:
    """Skill folders (containing SKILL.md) inside a plugin's skills/ dir."""
    skills_root = plugin_dir(plugin) / "skills"
    if not skills_root.is_dir():
        return []
    return sorted(
        d for d in skills_root.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    )


# --------------------------------------------------------------------------- #
# Frontmatter parsing (PyYAML preferred; safe fallback otherwise)
# --------------------------------------------------------------------------- #
def _parse_frontmatter_block(block: str) -> dict:
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(block) or {}
        return {
            str(k): " ".join(str(v).split())
            for k, v in data.items()
        } if isinstance(data, dict) else {}
    except ImportError:
        meta: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                if key and " " not in key:
                    meta[key] = val.strip()
        return meta


def read_frontmatter(skill_dir: Path) -> dict:
    """Parse the YAML frontmatter at the top of skill_dir/SKILL.md."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    return _parse_frontmatter_block(text[3:end])


def list_bundled_files(skill_dir: Path) -> list[Path]:
    """Files inside a skill folder other than SKILL.md, relative to it."""
    return sorted(
        f.relative_to(skill_dir)
        for f in skill_dir.rglob("*")
        if f.is_file() and f.name != "SKILL.md"
    )


# --------------------------------------------------------------------------- #
# Channel: Claude Code  (validation gate — git is the transport)
# --------------------------------------------------------------------------- #
def deploy_claude_code(plugin: dict, dry_run: bool) -> DeployResult:
    name = plugin.get("name", "?")
    pdir = plugin_dir(plugin)

    if not pdir.is_dir():
        return DeployResult(name, "claude_code", False,
                            f"source dir not found: {plugin.get('source')}")
    if not (pdir / ".claude-plugin" / "plugin.json").is_file():
        return DeployResult(name, "claude_code", False,
                            "missing .claude-plugin/plugin.json")

    skills = plugin_skill_dirs(plugin)
    if not skills:
        return DeployResult(name, "claude_code", False,
                            "no skills with SKILL.md under skills/")

    n = len(skills)
    if dry_run:
        return DeployResult(name, "claude_code", True,
                            f"valid: {n} skill(s); `git push` to publish")
    return DeployResult(name, "claude_code", True,
                        f"ready: {n} skill(s); publish with `git push`")


# --------------------------------------------------------------------------- #
# Channel: Claude.ai  (build .zip artifacts for admin upload)
# --------------------------------------------------------------------------- #
def deploy_claude_ai(plugin: dict, dry_run: bool, scopes: dict) -> DeployResult:
    name = plugin.get("name", "?")
    scope = scopes.get(name, "unspecified")
    skills = plugin_skill_dirs(plugin)

    if not skills:
        return DeployResult(name, "claude_ai", False,
                            "no skills with SKILL.md under skills/")

    # Org-wide: one zip per skill (uploaded individually under Settings>Skills).
    # Team-scoped: one plugin bundle zip (assigned to a group in the console).
    if scope == "org-wide":
        targets = [(s.name, [s]) for s in skills]
        note = "upload each via Organization settings > Skills"
    else:
        targets = [(name, skills)]  # bundle all the plugin's skills together
        note = f"assign plugin to {scope} in the admin console"

    if dry_run:
        zips = ", ".join(f"dist/{t}.zip" for t, _ in targets)
        return DeployResult(name, "claude_ai", True,
                            f"dry-run [{scope}]: would build {zips}")

    DIST.mkdir(exist_ok=True)
    built = []
    for zip_name, skill_set in targets:
        zip_path = DIST / f"{zip_name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for sdir in skill_set:
                base = sdir.parent  # so SKILL.md sits under <skill>/ in the zip
                for file in sorted(sdir.rglob("*")):
                    if file.is_file():
                        zf.write(file, file.relative_to(base))
        built.append(zip_path.relative_to(ROOT).as_posix())

    return DeployResult(name, "claude_ai", True,
                        f"[{scope}] built {', '.join(built)} — {note}")


# --------------------------------------------------------------------------- #
# Catalog (static, human-facing reference — NOT a runtime skill server)
# --------------------------------------------------------------------------- #
def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def build_catalog(dry_run: bool, repo_url: str | None = None) -> DeployResult:
    out = SITE / "index.html"
    rel = out.relative_to(ROOT)

    try:
        plugins = load_plugins()
        scopes = load_scopes()
    except (OSError, json.JSONDecodeError) as exc:
        return DeployResult("catalog", "catalog", False,
                            f"cannot read manifest: {exc}")

    total = sum(len(plugin_skill_dirs(p)) for p in plugins)
    if dry_run:
        return DeployResult("catalog", "catalog", True,
                            f"dry-run: would write {rel} "
                            f"({len(plugins)} plugins, {total} skills)")

    def file_link(rel_repo_path: str) -> str:
        if repo_url:
            return f"{repo_url.rstrip('/')}/blob/main/{rel_repo_path}"
        return f"../{rel_repo_path}"

    cards = []
    for plugin in plugins:
        name = plugin.get("name", "?")
        scope = scopes.get(name, "unspecified")
        badge = "org-wide" if scope == "org-wide" else scope
        rows = []
        for sdir in plugin_skill_dirs(plugin):
            sname = sdir.name
            meta = read_frontmatter(sdir)
            desc = meta.get("description", "(no description)")

            files = list_bundled_files(sdir)
            files_html = ""
            if files:
                repo_rel_base = sdir.relative_to(ROOT).as_posix()
                items = "".join(
                    f'<li><a href="{_html_escape(file_link(repo_rel_base + "/" + f.as_posix()))}">'
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
            f'<section class="plugin"><h2>{_html_escape(name)}'
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
def run(channels: list[str], dry_run: bool) -> list[DeployResult]:
    plugins = load_plugins()
    scopes = load_scopes()
    results: list[DeployResult] = []
    for plugin in plugins:
        for ch in channels:
            if ch == "claude_code":
                results.append(deploy_claude_code(plugin, dry_run))
            elif ch == "claude_ai":
                results.append(deploy_claude_ai(plugin, dry_run, scopes))
    return results


def print_table(results: list[DeployResult]) -> None:
    if not results:
        print("Nothing to deploy.")
        return
    w_name = max(len("PLUGIN"), max(len(r.name) for r in results))
    w_chan = max(len("CHANNEL"), max(len(r.channel) for r in results))
    header = f"{'PLUGIN':<{w_name}}  {'CHANNEL':<{w_chan}}  STATUS  DETAIL"
    print(header)
    print("-" * len(header))
    for r in results:
        status = " OK " if r.ok else "FAIL"
        print(f"{r.name:<{w_name}}  {r.channel:<{w_chan}}  [{status}] {r.detail}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deploy company skills.")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would happen without writing anything")
    p.add_argument("--channel", choices=["claude_code", "claude_ai", "all"],
                   default="all")
    p.add_argument("--catalog", action="store_true",
                   help="build the static catalog (site/index.html) and exit")
    p.add_argument("--repo-url",
                   help="repo base URL (e.g. https://github.com/org/company-skills); "
                        "makes bundled-file links point at GitHub")
    args = p.parse_args(argv)

    if args.catalog:
        result = build_catalog(args.dry_run, args.repo_url)
        print_table([result])
        return 0 if result.ok else 1

    channels = (["claude_code", "claude_ai"] if args.channel == "all"
                else [args.channel])
    results = run(channels, args.dry_run)
    print_table(results)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
