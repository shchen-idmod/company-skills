---
name: idm-pkg-install
description: |
  Use this skill when installing, setting up, or troubleshooting any IDM package or repository.
  Triggers include: installing a released IDM package from PyPI, setting up an IDM project
  environment from a GitHub repo or local path, running pip install or conda install against an
  IDM codebase, resolving dependency conflicts in scientific Python environments, or any request
  like 'install emodpy', 'install this repo', 'set up the environment for', or 'get this running'.
  Use this skill before writing any install commands — it determines the correct source, strategy,
  and mode based on what the user wants.
argument-hint: "[pypi|github-url|local-path] [dev|prod|requirements]"
allowed-tools: Bash, Read, Edit, Glob, Grep
---

# IDM Package Installation Skill

This skill installs IDM packages from three possible sources: **PyPI** (released versions), **GitHub repo** (clone and install), or **local path** (install from disk). Always confirm the source and mode with the user before running anything.

---

## Decision 1 — Install source

If not already specified, ask the user:

> "Where should I install from?
> 1. **PyPI** — install a released version by package name (e.g. `emodpy==2.1.0`)
> 2. **GitHub repo** — clone and install from a GitHub URL
> 3. **Local path** — install from a directory on this machine (default: current directory)"

| Source | When to use | Goes to |
|--------|-------------|---------|
| **PyPI** | You want a specific released version; CI/CD; no local clone needed | [PyPI section](#pypi) |
| **GitHub repo** | You want the latest commit or a specific branch/tag; no local clone yet | [Repo/local workflow](#main-workflow) |
| **Local path** | You already have a clone on disk | [Repo/local workflow](#main-workflow) |

---

## Decision 2 — Install mode (repo and local sources only)

Not applicable for PyPI — a PyPI install always installs a fixed release into site-packages.

For GitHub and local sources, three modes are available:

| Mode | Command | When to use |
|------|---------|-------------|
| **Dev** (editable) | `pip install -e .` | Actively modifying the package — changes reflect immediately |
| **Prod** (standard) | `pip install .` | Using the package as a consumer — installs a fixed copy from local source |
| **Requirements** | `pip install -r requirements.txt` | Repo has no installable package (no `pyproject.toml`/`setup.py`) — only dependencies |

**Dev** and **Prod** both install from **local source on disk** — neither downloads from PyPI. The `.` means "this directory." To install from PyPI use `pip install <package-name>` with no `.` (see PyPI section below).

**When to ask vs. auto-detect:**

- If the user passed the mode as an argument (`dev`, `prod`, or `requirements`), use it directly — do not ask.
- Otherwise, **defer the question until after repo inspection** ([Step 1](#step-1)). Once you know what files exist:
  - If only `requirements.txt` is present (no `pyproject.toml`, no `setup.py`/`setup.cfg`) → **auto-select `requirements` mode**, no prompt needed.
  - If an installable package is present → ask: *"Should I do a **dev install** (editable, `pip install -e .`) or a **prod install** (standard, `pip install .`)?"*
  - If both an installable package AND a `requirements.txt` are present and you're unsure → offer all three options.

Apply the chosen mode consistently across all install commands in the session.

---

## Install from PyPI {#pypi}

Use when the user wants a specific released version without cloning the repo.

```bash
# Install latest released version
pip install emodpy --break-system-packages

# Install a specific version
pip install emodpy==2.1.0 --break-system-packages

# Install multiple IDM packages at once
pip install emodpy idmtools emod-api --break-system-packages

# Install with extras
pip install "emodpy[test]" --break-system-packages

# Upgrade an existing install to the latest release
pip install --upgrade emodpy --break-system-packages

# Check available versions before installing
pip index versions emodpy 2>/dev/null \
  || pip install emodpy== --break-system-packages 2>&1 | grep -oP '(?<=versions: ).*'
```

**IDM packages available on PyPI:**

| Package | PyPI name | Notes |
|---------|-----------|-------|
| emod-api | `emod-api` | Core EMOD Python API |
| emodpy | `emodpy` | EMOD Python wrapper |
| emodpy-malaria | `emodpy-malaria` | Malaria-specific extensions |
| emodpy-hiv | `emodpy-hiv` | HIV-specific extensions |
| idmtools | `idmtools` | IDM Tools core |
| idmtools-platform-comps | `idmtools-platform-comps` | COMPS platform support |
| laser-core | `laser-core` | LASER simulation core |

**Packages NOT on PyPI (require GitHub or Artifactory):**

| Package pattern | Source |
|---|---|
| `dtk-*` (legacy) | IDM internal Artifactory — requires IDM network access |
| Unreleased branches / forks | GitHub URL install (see below) |

If the user asks for a package that isn't on PyPI, redirect to the GitHub repo or local path workflow.

**After installing from PyPI, verify:**

```bash
pip show emodpy          # confirm version and location
python -c "import emodpy; print(emodpy.__version__)"
```

---

## Install from GitHub repo or local path {#main-workflow}

### Step 0 — Resolve the repo path

```bash
# Local path — use as-is
REPO=/path/to/repo

# GitHub URL — clone first
git clone https://github.com/InstituteforDiseaseModeling/emodpy /tmp/idm-repo
REPO=/tmp/idm-repo

# Specific branch or tag
git clone --branch v2.1.0 https://github.com/org/repo /tmp/idm-repo

# No path given — use current directory
REPO=$(pwd)
```

---

### Step 1 — Inspect the repo before doing anything {#step-1}

Read these files in order. Stop at the first one that exists and contains install instructions; use the others to fill in gaps.

```bash
# 1. Check for a README
cat $REPO/README.md 2>/dev/null | head -100

# 2. Check for install/dependency files
ls $REPO/setup.py \
   $REPO/setup.cfg \
   $REPO/pyproject.toml \
   $REPO/requirements*.txt \
   $REPO/environment*.yml \
   $REPO/Makefile \
   $REPO/INSTALL* 2>/dev/null
```

---

### Step 2 — Choose the install strategy

Priority order when multiple files exist: `pyproject.toml` > `setup.py/setup.cfg` > `environment.yml` > `requirements.txt` > manual.

| File present | Strategy |
|---|---|
| `pyproject.toml` | Modern Python package (PEP 517/518) |
| `setup.py` or `setup.cfg` | Legacy Python package |
| `environment.yml` | Conda environment |
| `requirements.txt` | Pip dependencies only |
| `Makefile` with `install` target | Makefile-driven |
| None of the above | Script collection — infer deps manually |

---

### Strategy: pyproject.toml

Modern IDM packages use `pyproject.toml` (emod-api, emodpy, laser, etc.).

```bash
cd $REPO
grep -A3 '\[build-system\]' pyproject.toml        # check build backend
grep '\[project.optional-dependencies\]' pyproject.toml -A 30  # check extras
```

**Dev install:**
```bash
pip install -e ".[dev]" --break-system-packages    # with dev extras
pip install -e . --break-system-packages           # without extras
```

**Prod install:**
```bash
pip install ".[dev]" --break-system-packages       # with dev extras
pip install . --break-system-packages              # without extras
```

**If the build backend is `poetry`:**
```bash
pip install poetry --break-system-packages
poetry install           # dev (editable by default)
poetry install --no-dev  # prod (omits dev dependencies)
```

**If the build backend is `hatch`:**
```bash
pip install hatch --break-system-packages
hatch env create && hatch shell   # dev
pip install . --break-system-packages              # prod
```

---

### Strategy: setup.py / setup.cfg

Older IDM repos (EMOD, FPsim, older emodpy variants).

```bash
cd $REPO
grep 'extras_require' setup.py setup.cfg 2>/dev/null
grep 'cmdclass\|install_requires\|dependency_links' setup.py | head -20
```

**Dev install:**
```bash
pip install -e . --break-system-packages
pip install -e ".[test]" --break-system-packages   # with extras
```

**Prod install:**
```bash
pip install . --break-system-packages
pip install ".[test]" --break-system-packages      # with extras
```

> ⚠️ Never run `python setup.py install` — deprecated; bypasses pip's resolver and can silently corrupt environments.

---

### Strategy: environment.yml (Conda)

Use when the repo ships a Conda environment file, especially for compiled C/Fortran dependencies.

```bash
cd $REPO
cat environment.yml

conda env create -f environment.yml                # create fresh
# or: conda env update -f environment.yml --prune  # update existing

conda activate $(grep '^name:' environment.yml | awk '{print $2}')
```

If the repo also has `pyproject.toml` or `setup.py`, install the package inside the activated env:

**Dev install:** `pip install -e . --break-system-packages`
**Prod install:** `pip install . --break-system-packages`

If multiple environment files exist (`environment-dev.yml`, `environment-gpu.yml`, etc.), ask the user which to use.

---

### Strategy: requirements.txt

For script-level repos with no installable package. This is the **`requirements` mode** from [Decision 2](#decision-2--install-mode-repo-and-local-sources-only) — auto-selected when no `pyproject.toml` / `setup.py` is present, or chosen explicitly by the user.

```bash
cd $REPO
cat requirements*.txt    # inspect for version pins, git+https, IDM-internal packages

pip install -r requirements.txt --break-system-packages
# Multiple files:
pip install -r requirements.txt -r requirements-dev.txt --break-system-packages
```

Dev/prod does not apply here — there is no installable package, only dependencies. If the repo *does* have an installable package but the user explicitly asked for `requirements` mode, install only the listed dependencies and skip `pip install .` / `pip install -e .`.

---

### Strategy: Makefile

```bash
cd $REPO
make help 2>/dev/null || grep -E '^[a-zA-Z_-]+:' Makefile | head -20
make install   # or: make dev / make setup
```

---

### Strategy: No install file (script collection)

```bash
cd $REPO
grep -rh '^\s*import \|^\s*from ' --include="*.py" . | sed 's/^\s*//' | sort -u | head -50

pip install pipreqs --break-system-packages
pipreqs . --savepath /tmp/inferred_requirements.txt 2>/dev/null
pip install -r /tmp/inferred_requirements.txt --break-system-packages
```

---

### Step 3 — Environment isolation (MANDATORY — never skip)

**Do not run any install command until an isolated environment is created and activated.** Installing into the system Python or an uncontrolled environment risks corrupting other projects and is not permitted by this skill.

If the user has not specified an environment, ask before proceeding:
> "Should I create a **venv** or a **conda** environment? Or do you have an existing environment to activate?"

```bash
# Check required Python version first
grep -E 'python_requires|python >=|python==' \
  $REPO/pyproject.toml $REPO/setup.py $REPO/setup.cfg $REPO/environment.yml 2>/dev/null

# Option A — venv (lightweight, no conda needed)
python -m venv $REPO/.venv
source $REPO/.venv/bin/activate       # Linux/macOS
# $REPO\.venv\Scripts\activate        # Windows

# Option B — conda (when environment.yml present or C extensions needed)
conda create -n idm-env python=3.9
conda activate idm-env

# Option C — use the repo's own environment.yml directly (see conda strategy above)
conda env create -f $REPO/environment.yml
conda activate $(grep '^name:' $REPO/environment.yml | awk '{print $2}')
```

Confirm the environment is active before moving on:
```bash
which python    # should point inside .venv or the conda env, not system Python
```

---

### Step 4 — Check for IDM-internal packages

```bash
grep -E 'git\+|artifactory|idm-bamboo|idm\.local' \
  requirements*.txt setup.py pyproject.toml 2>/dev/null
```

If found, flag to the user before proceeding — these require IDM network access or credentials.

---

### Step 5 — Verify the installation

```bash
python -c "import <package_name>; print(<package_name>.__version__)"

pytest tests/ -x -q 2>/dev/null \
  || python -m pytest tests/ -x -q 2>/dev/null \
  || make test 2>/dev/null \
  || echo "No test runner found — manual check only"
```

---

## Common failure modes and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError` after install | Wrong environment active | Activate the correct venv/conda env and re-run |
| `Could not find a version that satisfies the requirement` | Package not on PyPI | Check for `git+https` or Artifactory source; use GitHub/local install instead |
| `Microsoft Visual C++ required` (Windows) | C extension needs a compiler | Install Build Tools for Visual Studio 2022 |
| `pip` installs but `import` fails | Package installed to wrong Python | Use `python -m pip install` instead of bare `pip` |
| Dependency conflict | Conflicting version pins | Fresh env; install `--no-deps` then resolve manually |
| `git clone` auth error | Private IDM repo | Add SSH key or use a PAT for HTTPS |
| `setup.py egg_info` fails | Missing `setuptools` | `pip install setuptools --upgrade --break-system-packages` |
| `pyproject.toml` build fails | Missing build backend | `pip install build wheel --break-system-packages` |
| `conda env create` hangs | Solver timeout | `conda env create -f environment.yml --solver=libmamba` |

---

## Workflow summary

**PyPI source:**
1. Confirm package name and optional version with the user.
2. **Create and activate an isolated environment (mandatory).** Ask: venv or conda?
3. `pip install <package>[==version]`
4. Verify with `pip show` and a quick import.

**GitHub / local source:**
1. Resolve path — clone if GitHub URL, default to `pwd` if nothing given.
2. **Create and activate an isolated environment (mandatory).** Ask: venv or conda? Never skip.
3. Inspect the repo — README + install files.
4. Pick strategy — `pyproject.toml` > `setup.py` > `environment.yml` > `requirements.txt` > manual.
5. Confirm install mode based on what was found:
   - Mode was passed as an argument → use it.
   - Only `requirements.txt` found → auto-select `requirements`, no prompt.
   - Installable package found → ask `dev` (`-e .`) vs `prod` (`.`).
6. Check for IDM-internal packages — flag if Artifactory/SSH needed.
7. Run the install using the chosen strategy and mode.
8. Verify — import the package and run any available tests.
9. Report — source, strategy, mode, environment, and any caveats.