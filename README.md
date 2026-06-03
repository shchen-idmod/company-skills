# Company Skills

Single source of truth for company-wide Claude skills. Each skill is authored
once here and published to **two** channels, because Claude.ai and Claude Code
consume skills differently:

| Surface     | How it gets skills                          | Discoverability |
|-------------|---------------------------------------------|-----------------|
| Claude.ai   | Admin uploads zips in Organization Settings | Auto-activates org-wide, zero user setup |
| Claude Code | Devs add this repo as a plugin marketplace  | Auto-activates locally, one-time setup per dev |

There is no single registry that feeds both automatically today, so we keep the
`SKILL.md` files here as the source of truth and run two thin publish steps.

## Repo layout

Skills are grouped into **plugins**. Each plugin is a folder under `plugins/`
with its own `plugin.json` and a `skills/` directory; the marketplace manifest
lists the plugins by path.

```
company-skills/
├── .claude-plugin/
│   ├── marketplace.json        # Claude Code marketplace manifest (lists plugins by source)
│   └── scopes.json             # Claude.ai scope per plugin (org-wide vs. group)
├── .github/workflows/
│   └── catalog.yml             # Builds + deploys the catalog to GitHub Pages
├── plugins/
│   ├── company-skills/         # org-wide plugin
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json
│   │   └── skills/
│   │       ├── incident-report/
│   │       │   └── SKILL.md
│   │       └── quarterly-report/
│   │           ├── SKILL.md
│   │           ├── references/gl-schema.md
│   │           ├── scripts/aggregate.py
│   │           └── tests/
│   └── idm-skills/             # group:IDM plugin
│       ├── .claude-plugin/
│       │   └── plugin.json
│       └── skills/
│           ├── idm-pkg-install/
│           │   └── SKILL.md
│           ├── python-code-fixer/
│           │   └── SKILL.md
│           └── python-code-review/
│               └── SKILL.md
├── scripts/
│   └── deploy.py               # Deploys both channels, builds catalog, status table
├── requirements.txt            # Tooling deps for deploy.py (PyYAML)
├── dist/                       # Generated zips for Claude.ai upload (git-ignored)
└── site/                       # Generated catalog (GitHub Pages)
```

## Authoring a skill

Create a folder under a plugin's `skills/` directory (e.g.
`plugins/company-skills/skills/my-skill/`) with a `SKILL.md`. A skill folder may
also bundle supporting files — `references/`, `scripts/`, `tests/`, etc. The
frontmatter `description` is what makes Claude auto-activate the skill on both
surfaces, so write it carefully — state *when* to use the skill, not just what
it does.

```yaml
---
name: my-skill
description: Use when <specific trigger>. Applies <what it does>.
---
```

No manifest edit is needed for a new skill: `deploy.py` and the catalog discover
every skill folder containing a `SKILL.md` under each plugin's `skills/` dir.
You only touch `marketplace.json` when adding a whole **new plugin** (and
`scopes.json` to set that plugin's Claude.ai scope).

## Publish to Claude Code (developers)

Each developer runs once:

```bash
claude plugin marketplace add https://github.com/your-org/company-skills
claude plugin install company-skills@company-skills
```

Then `/plugin` (Installed tab) confirms it. Updates: reinstall to pull latest
(plugins don't auto-update yet).

## Publish to Claude.ai (admin / owner)

1. Build the zips:
   ```bash
   python scripts/deploy.py --channel claude_ai
   ```
2. In Claude.ai: **Organization settings > Skills**. Ensure **Code execution
   and file creation** and **Skills** are both enabled.
3. Under **Organization skills**, click **+ Add** and upload each
   `dist/<skill>.zip`. Each becomes available to all members immediately.

For team-scoped skills, bundle them into a plugin and assign it to a group
instead of provisioning org-wide.

## Deploy CLI

`scripts/deploy.py` handles both channels and prints a per-plugin, per-channel
status table. It exits non-zero if any channel fails, so it works in CI. It
needs the tooling deps first: `pip install -r requirements.txt`.

```bash
python scripts/deploy.py                       # both channels, all plugins
python scripts/deploy.py --dry-run             # preview, write nothing
python scripts/deploy.py --channel claude_ai   # only build Claude.ai zips
python scripts/deploy.py --channel claude_code # only validate Claude Code plugins
python scripts/deploy.py --catalog             # build the static catalog and exit
```

For Claude Code, "deploy" is a validation gate: it confirms each skill has a
`SKILL.md` and is registered in `marketplace.json`. Actual publishing is
`git push`. For Claude.ai, it builds the upload zip into `dist/`.

## Skill scoping (org-wide vs. team)

Scope is set per plugin in `.claude-plugin/scopes.json`, which maps each
plugin name to a scope string:

```json
{
  "company-skills": "org-wide",
  "idm-skills": "group:IDM"
}
```

- `"org-wide"` — `deploy.py` builds one zip per skill; upload them under
  Organization Settings → Skills, enabled for everyone.
- `"group:<NAME>"` — `deploy.py` bundles the whole plugin into a single zip;
  assign it to that group in the admin console so only the group sees it.

Scope is read only by `scripts/deploy.py` and the catalog (it is not part of the
Claude Code marketplace schema), and it is also what the catalog groups by.

## Skills catalog (human reference)

`python scripts/deploy.py --catalog` generates `site/index.html`: a static page
listing every skill grouped by plugin/scope, with each skill's description.
Skills that bundle files beyond `SKILL.md` also list those files as links you
can click to view them. It is a **read-only reference for people** — Claude
still receives skills through the marketplace and admin provisioning, never from
this page.

Pass `--repo-url https://github.com/your-org/company-skills` to make the
bundled-file links point at GitHub; the CI workflow sets this automatically.

Host it on **GitHub Pages**. The included workflow
(`.github/workflows/catalog.yml`) regenerates and deploys it on every push that
touches a skill or the manifest, so the catalog never drifts from what's
actually published. To enable: in the repo, go to **Settings → Pages → Build
and deployment → Source: GitHub Actions**.

Do not stand up a separate always-on service (e.g. a Railway app) to serve
skills at runtime — that reintroduces the manual-invocation problems the native
paths were chosen to avoid. A static catalog is reference only.

## Governance

Keep org-wide *member* sharing **off** in Organization Settings (it has no
approval step). Members submit skills via PR to this repo; an owner reviews,
merges, then publishes through the two steps above. That keeps this repo the
gated source of truth.