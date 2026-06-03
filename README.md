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

```
company-skills/
├── .claude-plugin/
│   └── marketplace.json        # Claude Code marketplace manifest (+ scope per plugin)
├── .github/workflows/
│   └── catalog.yml             # Builds + deploys the catalog to GitHub Pages
├── skills/
│   ├── python-code-review/
│   │   └── SKILL.md
│   └── incident-report/
│       └── SKILL.md
├── scripts/
│   └── deploy.py               # Deploys both channels, builds catalog, status table
├── dist/                       # Generated zips for Claude.ai upload (git-ignored)
└── site/                       # Generated catalog (GitHub Pages)
```

## Authoring a skill

Create a folder under `skills/` with a `SKILL.md`. The frontmatter
`description` is what makes Claude auto-activate the skill on both surfaces, so
write it carefully — state *when* to use the skill, not just what it does.

```yaml
---
name: my-skill
description: Use when <specific trigger>. Applies <what it does>.
---
```

After adding a skill folder, also list its path in the `skills` array in
`.claude-plugin/marketplace.json`.

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

`scripts/deploy.py` handles both channels and prints a per-skill, per-channel
status table. It exits non-zero if any channel fails, so it works in CI.

```bash
python scripts/deploy.py                       # both channels, all skills
python scripts/deploy.py --dry-run             # preview, write nothing
python scripts/deploy.py --channel claude_ai   # only build Claude.ai zips
python scripts/deploy.py --skill incident-report   # one skill only
```

For Claude Code, "deploy" is a validation gate: it confirms each skill has a
`SKILL.md` and is registered in `marketplace.json`. Actual publishing is
`git push`. For Claude.ai, it builds the upload zip into `dist/`.

## Skill scoping (org-wide vs. team)

Each plugin in `marketplace.json` carries a `scope` field:

- `"scope": "org-wide"` — upload these skills under Organization Settings →
  Skills; enabled for everyone.
- `"scope": "group:<NAME>"` — bundle as a plugin and assign it to that group in
  the admin console; only the group sees them.

Scope is also what the catalog groups by.

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