---
name: python-code-fixer
description: "Use this skill when applying fixes to Python 3 code review findings from REVIEW.md. Covers reading source files, applying intelligent fixes, committing each fix atomically, and producing a REVIEW-FIX.md report. Python 3 only — do NOT use for other languages, initial code review, test running, or deployment tasks."
allowed-tools: Read, Edit, Write, Grep, Glob, Bash, PowerShell
---

# Python Code Fixer (Python 3)

Applies fixes to Python 3 code review findings from `REVIEW.md`. Produces a `REVIEW-FIX.md` artifact next to the source review file.

**Usage:** Load this skill in Claude Code to apply fixes to Python 3 code review findings from `REVIEW.md`.

## Modes

This skill runs in one of two modes:

- **Standalone Mode (default)** — invoked directly by a user. Reads `./REVIEW.md` from the project root (matching the output of the companion `python-code-reviewer` skill), writes `./REVIEW-FIX.md`, edits files in the current working tree, and does **not** create a worktree. Skip Step 1 entirely.
- **Phase Mode** — invoked by an orchestrator that supplies a `<config>` block with `phase_dir`, `padded_phase`, `review_path`, `fix_report_path`. Runs the full worktree-based flow in Step 1.

Detect the mode in Step 2 by checking whether a `<config>` block is present in the prompt.

> **Scope:** Python 3 source files (`.py`) only. Skip any finding that targets a non-Python file and mark it as "skipped: non-Python file, out of scope".

**Job:** Read `REVIEW.md` findings → fix source code intelligently (not blindly) → commit each fix atomically → produce `REVIEW-FIX.md` report.

> **CRITICAL — Mandatory Initial Read:** If the prompt contains a `<required_reading>` block, use the `Read` tool to load every file listed there before any other action. This is primary context.

---

## Project Context

Before fixing code, discover project context:

**Project instructions:** Read `./CLAUDE.md` if it exists. Follow all project-specific guidelines, security requirements, and coding conventions.

**Project skills:** Check `.claude/skills/` or `.agents/skills/` if either exists:
1. List available skills (subdirectories)
2. Read `SKILL.md` for each skill (lightweight index ~130 lines)
3. Load specific `rules/*.md` files as needed
4. Do NOT load full `AGENTS.md` files (100KB+ context cost)
5. Follow skill rules relevant to fix tasks

---

## Fix Strategy

The REVIEW.md fix suggestion is **guidance**, not a patch to apply blindly.

**For each finding:**
1. **Read the actual source file** at the cited line (plus surrounding context — at least +/- 10 lines)
2. **Understand the current code state** — check if code matches what reviewer saw
3. **Adapt the fix suggestion** to actual code if it has changed or differs from review context
4. **Apply the fix** using Edit tool (preferred) for targeted changes, or Write tool for full rewrites
5. **Verify the fix** using the 3-tier verification strategy (see below)

**If the source file has changed significantly** and the fix no longer applies cleanly:
- Mark finding as "skipped: code context differs from review"
- Continue with remaining findings
- Document in REVIEW-FIX.md

**If multiple files are referenced in the Fix section:**
- Collect ALL file paths mentioned in the finding
- Apply fix to each file
- Include all modified files in the atomic commit

---

## Rollback Strategy

Before editing **any** file for a finding, establish safe rollback capability.

**Protocol:**
1. **Record files to touch:** Note each file path in `touched_files` before editing anything.
2. **Apply fix:** Use Edit tool (preferred) for targeted changes.
3. **Verify fix:** Apply 3-tier verification strategy.
4. **On verification failure:**
   - Run `git checkout -- {file}` for EACH file in `touched_files`.
   - This is safe: the fix has NOT been committed yet. `git checkout --` reverts only the uncommitted in-progress change and does not affect commits from prior findings.
   - **DO NOT use Write tool for rollback** — a partial write on tool failure leaves the file corrupted with no recovery path.
5. **After rollback:**
   - Re-read the file and confirm it matches pre-fix state.
   - Mark finding as "skipped: fix caused errors, rolled back".
   - Document failure details in skip reason.
   - Continue with next finding.

**Rollback scope:** Per-finding only. Files modified by prior (already committed) findings are NOT touched during rollback.

---

## Verification Strategy (3-Tier)

After applying each fix, verify correctness in 3 tiers.

### Tier 1 — Minimum (ALWAYS REQUIRED)
- Re-read the modified file section (at least the lines affected by the fix)
- Confirm the fix text is present
- Confirm surrounding code is intact (no corruption)

### Tier 2 — Preferred (when available)
Run the Python 3 syntax check on the modified `.py` file. Try `python3` first, then `python` (Windows typically only ships `python`):

POSIX shells:
```bash
PY=$(command -v python3 || command -v python)
"$PY" -m py_compile {file} && echo "OK"
```

PowerShell:
```powershell
$py = (Get-Command python3 -ErrorAction SilentlyContinue) ?? (Get-Command python -ErrorAction SilentlyContinue)
if ($py) { & $py.Source -m py_compile {file}; if ($LASTEXITCODE -eq 0) { "OK" } }
```

**Scoping rules:**
- Only fail if the syntax error is in the file you just modified. Errors in other files are pre-existing — ignore them.
- If the check fails with errors that existed before your edit: proceed to commit.
- If neither `python3` nor `python` is available: fall back to Tier 3 — do NOT rollback.

### Tier 3 — Fallback
If no Python interpreter is on PATH (e.g., restricted environment):
- Accept Tier 1 result
- Note in REVIEW-FIX.md: "syntax check skipped: python interpreter not available"

**Logic bug limitation:** Tier 1 and Tier 2 verify syntax/structure only, NOT semantic correctness. For findings where REVIEW.md classifies the issue as a logic error (incorrect condition, wrong algorithm, bad state handling), set the commit status in REVIEW-FIX.md as `"fixed: requires human verification"` rather than `"fixed"`.

---

## Finding Parser

### Structure

Each finding starts with:
```
### {ID}: {Title}
```

ID matches: `CR-\d+` or `BL-\d+` (Critical), `WR-\d+` (Warning), or `IN-\d+` (Info)

### Required Fields

- **File:** primary file path — format: `path/to/file.ext:42` or `path/to/file.ext`
- **Issue:** problem description
- **Fix:** section extends from `**Fix:**` to next `### ` heading or end of file

### Fix Content Variants

The **Fix:** section may contain:

1. **Inline code or code fences:**
   ````
   ```language
   code snippet
   ```
   ````
   Extract code from triple-backtick fences.

   > **IMPORTANT:** Code fences may contain markdown-like syntax (headings, horizontal rules). Always track fence open/close state when scanning for section boundaries. Content between ``` delimiters is opaque — never parse it as finding structure.

2. **Multiple file references:**
   "In `module_a.py`, change X; in `module_b.py`, change Y" — parse ALL file references into the finding's `files` array.

3. **Prose-only descriptions:**
   "Add null check before accessing property" — interpret intent and apply fix.

### Parsing Rules

- Trim whitespace from extracted values
- Handle missing line numbers gracefully (line: null)
- If Fix section is empty or just says "see above", use Issue description as guidance
- Stop parsing at next `### ` heading or `---` footer
- When scanning for `### ` boundaries, treat content inside triple-backtick fences as opaque — do NOT match `### ` or `---` inside fenced blocks
- `### ` headings inside a code fence (e.g., example markdown output) are NOT finding boundaries

---

## Execution Flow

### Step 1 — Setup Worktree (Phase Mode only — skip in Standalone)

> **Standalone Mode:** Skip this entire step. Operate on the current working tree, in the current branch. Proceed directly to Step 2.
>
> **Phase Mode only:** When invoked by an orchestrator with a `<config>` block, create a dedicated git worktree BEFORE touching any files.

This skill, when run in Phase Mode, runs as a background process that makes commits. Operating on the main working tree would race the foreground session. Every Phase-Mode instance runs in its own isolated worktree.

> The bash block below is POSIX-only (uses `mktemp`, `awk`, `sed`, `node`). It is intended for the orchestrator's Linux/macOS environment. Do **not** attempt to translate it to PowerShell for direct user runs — Standalone Mode skips this step entirely.

The cleanup tail (commit fixes → remove worktree → drop recovery sentinel) MUST be transactional. If the process is interrupted between the last commit and `git worktree remove`, a discoverable recovery sentinel must be left behind for future cleanup.

```bash
branch=$(git branch --show-current)
test -n "$branch" || { echo "Detached HEAD is not supported for review-fix (#2686)"; exit 1; }

# Recovery-sentinel handling (#2839):
sentinel="${phase_dir}/.review-fix-recovery-pending.json"
if [ -f "$sentinel" ]; then
  echo "Detected pre-existing recovery sentinel from a prior interrupted run: $sentinel"
  prior_recovery=$(node -e '
    const fs = require("fs");
    try {
      const parsed = JSON.parse(fs.readFileSync(process.argv[1], "utf-8"));
      process.stdout.write((parsed.worktree_path || "") + "\n" + (parsed.reviewfix_branch || ""));
    } catch (err) {
      process.stderr.write(`Warning: malformed recovery sentinel ${process.argv[1]}: ${err.message}\n`);
      process.stdout.write("\n");
    }
  ' "$sentinel")
  prior_wt="$(printf '%s' "$prior_recovery" | sed -n '1p')"
  prior_branch="$(printf '%s' "$prior_recovery" | sed -n '2p')"
  if [ -n "$prior_wt" ] && git worktree list --porcelain | grep -q "^worktree $prior_wt$"; then
    echo "Removing orphan worktree from prior run: $prior_wt"
    git worktree remove "$prior_wt" --force || true
  fi
  if [ -n "$prior_branch" ]; then
    echo "Removing orphan reviewfix branch from prior run: $prior_branch"
    git branch -D "$prior_branch" 2>/dev/null || true
  fi
  rm -f "$sentinel"
fi

wt=$(mktemp -d "/tmp/sv-${padded_phase}-reviewfix-XXXXXX")

reviewfix_branch="python-reviewfix/${padded_phase}-$$"
git worktree add -b "$reviewfix_branch" "$wt" "$branch"

# Write recovery sentinel ONLY AFTER `git worktree add` succeeds
node -e '
  const fs = require("fs");
  const [sentinelPath, worktree_path, branch, reviewfix_branch, padded_phase] = process.argv.slice(1);
  fs.writeFileSync(sentinelPath, JSON.stringify({
    worktree_path,
    branch,
    reviewfix_branch,
    padded_phase,
    started_at: new Date().toISOString()
  }, null, 2));
' "$sentinel" "$wt" "$branch" "$reviewfix_branch" "$padded_phase"

cd "$wt"
```

**Concrete steps:**
1. Parse `padded_phase` and `phase_dir` from the `<config>` block.
2. Resolve current branch: `branch=$(git branch --show-current)`. If empty (detached HEAD), print error and exit.
3. **Recovery check (#2839, #2990):** If `${phase_dir}/.review-fix-recovery-pending.json` exists, parse it, attempt to remove the orphan worktree (best-effort, `--force`), delete the stale `reviewfix_branch` (best-effort, `git branch -D`), then delete the stale sentinel.
4. Create unique worktree path: `wt=$(mktemp -d "/tmp/sv-${padded_phase}-reviewfix-XXXXXX")`.
5. Run `git worktree add -b "$reviewfix_branch" "$wt" "$branch"` — attaches to a NEW branch so it coexists with the user's checkout (#2990).
6. **Write recovery sentinel** at `${phase_dir}/.review-fix-recovery-pending.json` containing `{worktree_path, branch, reviewfix_branch, padded_phase, started_at}`. Only write AFTER `git worktree add` succeeds.
7. All subsequent reads, edits, and commits happen inside `$wt`.

**If `git worktree add` fails:** surface the error and exit. Do not force-remove the path. Do not write the sentinel.

**Cleanup tail (transactional — ALWAYS, even on failure):**

```bash
# Step 1: fast-forward $branch to capture agent commits
main_repo="$(git worktree list --porcelain | awk '/^worktree / { sub(/^worktree /, ""); print; exit }')"
ff_status=0
if git -C "$main_repo" merge --ff-only "$reviewfix_branch" 2>&1; then
  ff_status=0
else
  ff_status=$?
  echo "WARN: could not fast-forward $branch to $reviewfix_branch (exit $ff_status)."
  echo "      The temp branch $reviewfix_branch is preserved for manual merge."
fi

# Step 2: drop the worktree
git worktree remove "$wt" --force

# Step 3: delete temp branch ONLY if fast-forward succeeded
if [ "$ff_status" -eq 0 ]; then
  git -C "$main_repo" branch -D "$reviewfix_branch" || true
fi

# Step 4: drop the recovery sentinel ONLY after worktree remove succeeds
rm -f "$sentinel"
```

---

### Step 2 — Load Context

1. **Read mandatory files:** Load all files from `<required_reading>` block if present.
2. **Detect mode and resolve config:**

   *If a `<config>` block is present in the prompt* → **Phase Mode**. Extract:
   - `phase_dir`: e.g., `.planning/phases/02-code-review-command`
   - `padded_phase`: e.g., `"02"`
   - `review_path`: e.g., `.planning/phases/02-code-review-command/02-REVIEW.md`
   - `fix_scope`: `"critical_warning"` (default) or `"all"` (includes Info findings)
   - `fix_report_path`: e.g., `.planning/phases/02-code-review-command/02-REVIEW-FIX.md`

   *Otherwise* → **Standalone Mode**. Use these defaults (no `<config>` required):
   - `review_path = ./REVIEW.md` (matches output of the `python-code-reviewer` skill)
   - `fix_report_path = ./REVIEW-FIX.md`
   - `fix_scope = "critical_warning"`
   - `phase_dir` and `padded_phase` are **not used** in Standalone Mode.

3. **Read REVIEW.md:** Use the `Read` tool on `{review_path}` (do not shell out to `cat` — it is not cross-platform).
4. **Parse frontmatter status field:** If status is `"clean"` or `"skipped"`, exit with message: "No issues to fix — REVIEW.md status is {status}." Do NOT create REVIEW-FIX.md. Exit code 0.
5. **Load project context:** Read `./CLAUDE.md` and check for `.claude/skills/` or `.agents/skills/`.

---

### Step 3 — Parse Findings

1. **Extract findings from REVIEW.md body** using the finding parser rules above.

   For each finding, extract:
   - `id`: e.g., CR-01, WR-03, IN-12
   - `severity`: Critical (CR-* or BL-*), Warning (WR-*), Info (IN-*)
   - `title`: from `### ` heading
   - `file`: primary file path from **File:** line
   - `files`: ALL file paths referenced in finding (including Fix section)
   - `line`: line number if present, else null
   - `issue`: from **Issue:** line
   - `fix`: full fix content from **Fix:** section

2. **Filter by fix_scope:**
   - `"critical_warning"`: include CR-*, BL-*, WR-* only
   - `"all"`: include CR-*, BL-*, WR-*, IN-*

3. **Sort by severity:** Critical first, then Warning, then Info. Within same severity, maintain document order.

4. **Record `findings_in_scope`** for REVIEW-FIX.md frontmatter.

---

### Step 4 — Apply Fixes

For each finding in sorted order:

**a. Read source files**
- Read ALL source files referenced by the finding
- For primary file: read at least +/- 10 lines around cited line
- For additional files: read full file

**b. Record files to touch**
- Note each file path in `touched_files` before editing anything

**c. Determine if fix applies**
- Compare current code state to what the reviewer described
- Adapt if code has minor changes but fix still logically applies

**d. Apply fix or skip**

*If fix applies cleanly:*
- Use Edit tool (preferred) for targeted changes, or Write tool for full file rewrites
- Apply to ALL files referenced in finding

*If code context differs significantly:*
- Mark as "skipped: code context differs from review"
- Record skip reason, continue to next finding

**e. Verify fix** (3-tier strategy above)

**f. Commit fix atomically**

Examples:
- `fix(02): CR-01 fix SQL injection in auth.py`
- `fix(03): WR-05 add None check before list access in utils.py`

Multiple files: list ALL modified files after the message (space-separated).

Extract commit hash:
```bash
COMMIT_HASH=$(git rev-parse --short HEAD)
```

*If commit FAILS after successful edit:*
- Mark as "skipped: commit failed"
- Execute rollback to restore files
- Do NOT leave uncommitted changes
- Document commit error in skip reason

**g. Record result**

```python
{
    "finding_id": "CR-01",
    "status": "fixed" | "skipped",
    "files_modified": ["path/to/file1.py", "path/to/file2.py"],  # if fixed
    "commit_hash": "abc1234",  # if fixed
    "skip_reason": "code context differs from review"  # if skipped
}
```

**h. Safe arithmetic for counters**

```bash
FIXED_COUNT=$((FIXED_COUNT + 1))   # correct
# ((FIXED_COUNT++))                # WRONG — fails under set -e
```

---

### Step 5 — Write Fix Report

**Create `REVIEW-FIX.md`** at `fix_report_path`.

**YAML frontmatter:**
```yaml
---
phase: {phase}
fixed_at: {ISO timestamp}
review_path: {path to source REVIEW.md}
iteration: {current iteration number, default 1}
findings_in_scope: {count}
fixed: {count}
skipped: {count}
status: all_fixed | partial | none_fixed
---
```

Status values:
- `all_fixed`: All in-scope findings successfully fixed
- `partial`: Some fixed, some skipped
- `none_fixed`: All findings skipped

**Body structure:**
```markdown
# Phase {X}: Code Review Fix Report

**Fixed at:** {timestamp}
**Source review:** {review_path}
**Iteration:** {N}

**Summary:**
- Findings in scope: {count}
- Fixed: {count}
- Skipped: {count}

## Fixed Issues

{If none, write: "None — all findings were skipped."}

### {finding_id}: {title}

**Files modified:** `file1`, `file2`
**Commit:** {hash}
**Applied fix:** {brief description of what was changed}

## Skipped Issues

{Omit section if none}

### {finding_id}: {title}

**File:** `path/to/file.ext:{line}`
**Reason:** {skip_reason}
**Original issue:** {issue description from REVIEW.md}

---

_Fixed: {timestamp}_
_Fixer: Claude (python-code-fixer)_
_Iteration: {N}_
```

> **DO NOT commit REVIEW-FIX.md** — the orchestrator handles that commit. This skill only commits individual per-finding fix changes.

---

## Critical Rules

- **Phase Mode only — always run inside the isolated worktree** set up via `git worktree add -b "$reviewfix_branch" "$wt" "$branch"`. Using `mktemp` ensures concurrent runs don't collide. Commits advance `$reviewfix_branch`; the cleanup tail fast-forwards `$branch` to capture them. **Standalone Mode** operates on the current working tree and does **not** create a worktree.
- **Phase Mode only — always run the transactional cleanup tail in order**: (1) `merge --ff-only`, (2) `worktree remove`, (3) `branch -D` (only if ff succeeded), (4) `rm -f "$sentinel"`. Never reorder. Does not apply in Standalone Mode.
- **Always use the Write tool to create files** — never use `Bash(cat << 'EOF')`, heredocs, or `node -e 'fs.writeFileSync(...)'` to materialize files. (The Phase-Mode sentinel write is the one orchestrator-internal exception; user-visible artifacts always go through the Write tool.)
- **Read the actual source file** before applying any fix — never blindly apply REVIEW.md suggestions.
- **Record touched files** before every fix attempt — this is your rollback list.
- **Commit each fix atomically** — one commit per finding, listing ALL modified files.
- **Use Edit tool (preferred)** over Write tool for targeted changes.
- **Verify each fix** using the 3-tier strategy.
- **Skip findings that cannot be applied cleanly** — do not force broken fixes. Mark as skipped with a clear reason.
- **Rollback using `git checkout -- {file}`** — atomic and safe. Do NOT use Write tool for rollback.
- **Do not modify files unrelated to the finding** — scope each fix narrowly.
- **Do not run the full test suite** between fixes — handled by the verifier phase later.
- **Respect CLAUDE.md project conventions** during fixes.
- **Do not leave uncommitted changes** — if commit fails after successful edit, rollback and mark as skipped.
- **Do not create new files** unless the fix explicitly requires it (e.g., a missing import file). Document in REVIEW-FIX.md if a new file was created.

---

## Partial Failure Semantics

Fixes are committed per-finding. Implications:

- **Mid-run crash:** Some fix commits may already exist in git history. This is by design — each commit is self-contained and correct. If the agent crashes before writing REVIEW-FIX.md, commits are still valid.
- **Agent failure before REVIEW-FIX.md:** Workflow detects the missing report and alerts: "Agent failed. Some fix commits may already exist — check `git log`."
- **REVIEW-FIX.md accuracy:** Report reflects what was actually fixed vs skipped at time of writing.
- **Idempotency:** Re-running the fixer on the same REVIEW.md may produce different results if code has changed. Not a bug — the fixer adapts to current code state, not historical review context.
- **Partial automation:** Some findings may be auto-fixable, others require human judgment. The skip-and-log pattern allows partial automation.

---

## Success Criteria

- [ ] All in-scope findings attempted (fixed or skipped with reason)
- [ ] Each fix committed atomically with `fix({padded_phase}): {id} {description}` format
- [ ] All modified files listed after each commit message
- [ ] REVIEW-FIX.md created with accurate counts, status, and iteration number
- [ ] No source files left in broken state (failed fixes rolled back via `git checkout`)
- [ ] No partial or uncommitted changes remain after execution
- [ ] Verification performed for each fix (minimum: re-read; preferred: syntax check)
- [ ] Safe rollback used `git checkout -- {file}` (not Write tool)
- [ ] Skipped findings documented with specific skip reasons
- [ ] Project conventions from CLAUDE.md respected