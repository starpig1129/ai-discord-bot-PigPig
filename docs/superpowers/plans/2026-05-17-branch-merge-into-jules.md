# Branch Merge Into Jules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate all meaningful remote branches and merge the best implementations into `jules`, resolving all conflicts automatically by preferring functional completeness then code clarity.

**Architecture:** Phase 1 merges 5 unique-feature branches in conflict-risk order (docs → single-file fixes → multi-file features). Phase 2 runs parallel agent analysis across 16 duplicate optimization branches, selects the best one per category (Episodic Memory, Procedural Memory), and merges them.

**Tech Stack:** Python 3.11+, discord.py, LangChain, asyncio, SQLite, git

---

## File Impact Map

| Branch | Files Changed (relative to `jules`) |
|--------|--------------------------------------|
| `docs/generate-all-docs-...` | `docs/**/*.md`, `final_output.txt` (pure additions) |
| `fix-on-tree-error-messages-...` | `bot.py` |
| `ux/improve-slash-command-error-handling-...` | `bot.py` (conflicts with above) |
| `feature/knowledge-save-command-...` | `cogs/userdata.py` |
| `feat-dashboard` | `bot.py`, `addons/`, `cogs/`, `dashboard-frontend/`, `.env Example`, `README.md` |
| Episodic Memory (best of 10) | `llm/memory/episodic.py`, `cogs/memory/services/vectorization_service.py` |
| Procedural Memory (best of 6) | `cogs/memory/db/procedural_storage.py`, `cogs/memory/users/manager.py` |

---

## Task 1: Switch to `jules` and Sync

**Files:** none (git operations only)

- [ ] **Step 1: Switch to jules and pull latest**

```bash
git checkout jules
git pull origin jules
```

Expected: `Already up to date.` or fast-forward. Current HEAD should be commit `494d651`.

- [ ] **Step 2: Verify clean state**

```bash
git status
git log --oneline -3
```

Expected: `nothing to commit, working tree clean`. Top commit: `494d651 feat: refine tool usage guidelines...`

---

## Task 2: Merge `docs/generate-all-docs` (pure additions, no conflict)

**Files:**
- Create: `docs/**/*.md` (60+ new documentation files)
- Create: `final_output.txt`

- [ ] **Step 1: Merge docs branch**

```bash
git merge origin/docs/generate-all-docs-9646874452220810181 --no-ff -m "merge: auto-generated documentation for all Python modules"
```

Expected: Fast-forward or clean merge — no conflicts. All changes are new files under `docs/`.

- [ ] **Step 2: Verify merge**

```bash
git log --oneline -1
ls docs/cogs/memory/
```

Expected: merge commit present; `docs/cogs/memory/` contains `.md` files like `episodic_storage.md`.

- [ ] **Step 3: Syntax-check bot entry point**

```bash
python -c "import ast; ast.parse(open('bot.py').read()); print('OK')"
```

Expected: `OK`

---

## Task 3: Merge `fix-on-tree-error-messages` (bot.py only)

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Inspect the diff before merging**

```bash
git diff origin/jules...origin/fix-on-tree-error-messages-16870004965955776482 -- bot.py
```

Read what `on_tree_error` handler was changed to — note the exact added lines for conflict reference in Task 4.

- [ ] **Step 2: Merge**

```bash
git merge origin/fix-on-tree-error-messages-16870004965955776482 --no-ff -m "merge: add friendly error messages for AppCommand errors in on_tree_error"
```

Expected: Clean merge — `bot.py` updated with new `on_tree_error` logic.

- [ ] **Step 3: Verify**

```bash
python -c "import ast; ast.parse(open('bot.py').read()); print('OK')"
git log --oneline -1
```

Expected: `OK` and merge commit present.

---

## Task 4: Merge `ux/improve-slash-command-error-handling` (bot.py conflict expected)

**Files:**
- Modify: `bot.py` (conflicts with Task 3 changes)

- [ ] **Step 1: Inspect the diff**

```bash
git diff origin/jules...origin/ux/improve-slash-command-error-handling-10386039463375131800 -- bot.py
```

Note the lines added for localized slash command error handling. Compare with what Task 3 added.

- [ ] **Step 2: Attempt merge**

```bash
git merge origin/ux/improve-slash-command-error-handling-10386039463375131800 --no-ff -m "merge: add localized handling for expected slash command errors"
```

If clean: skip to Step 4. If conflict: continue to Step 3.

- [ ] **Step 3: Resolve bot.py conflict (if any)**

Open `bot.py` and find conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). Resolution rule:
- **Keep BOTH blocks** — Task 3 added `on_tree_error` friendly messages; this branch adds localized slash command error handling. These are complementary, not competing.
- Combine the logic so `on_tree_error` contains both the friendly message mapping (from Task 3) AND the localized error response (from this branch).

```bash
# After manually resolving:
python -c "import ast; ast.parse(open('bot.py').read()); print('OK')"
git add bot.py
git commit -m "merge: add localized handling for expected slash command errors (resolved bot.py conflict)"
```

- [ ] **Step 4: Verify**

```bash
python -c "import ast; ast.parse(open('bot.py').read()); print('OK')"
git log --oneline -2
```

Expected: `OK` and two merge commits visible.

---

## Task 5: Merge `feature/knowledge-save-command` (cogs/userdata.py only)

**Files:**
- Modify: `cogs/userdata.py`

- [ ] **Step 1: Inspect the diff**

```bash
git diff origin/jules...origin/feature/knowledge-save-command-17141402164890107963 -- cogs/userdata.py
```

Note the new `/knowledge save` slash command handler added.

- [ ] **Step 2: Merge**

```bash
git merge origin/feature/knowledge-save-command-17141402164890107963 --no-ff -m "merge: add /knowledge save slash command to userdata cog"
```

Expected: Clean merge — `cogs/userdata.py` gains new slash command.

- [ ] **Step 3: Verify**

```bash
python -c "import ast; ast.parse(open('cogs/userdata.py').read()); print('OK')"
git log --oneline -1
```

Expected: `OK` and merge commit present.

---

## Task 6: Merge `feat-dashboard` (widest change surface)

**Files:**
- Modify: `bot.py`, `addons/logging.py`, `addons/settings.py`, `addons/tokens.py`, `base_configs/base.yaml`, `cogs/` (multiple), `cogs/memory/` (multiple)
- Create: `dashboard-frontend/` (entire React frontend)
- Modify: `.env Example`, `.gitignore`, `README.md`

- [ ] **Step 1: List all conflicting files**

```bash
git merge --no-commit --no-ff origin/feat-dashboard 2>&1 | grep -i conflict || echo "no conflicts"
git merge --abort 2>/dev/null || true
```

This dry-run shows what will conflict. Note the list.

- [ ] **Step 2: Perform the merge**

```bash
git merge origin/feat-dashboard --no-ff -m "merge: feat-dashboard — web dashboard, config GUI, and memory management UI"
```

- [ ] **Step 3: Resolve each conflict file**

For each file with `<<<<<<<` markers, apply this rule:

**`bot.py`**: Keep ALL error handler additions from Tasks 3 & 4. Keep ALL dashboard initialization code from `feat-dashboard`. Combine both.

**`addons/settings.py`**, **`addons/tokens.py`**, **`addons/logging.py`**: `feat-dashboard` adds dashboard-specific config fields. Accept all `feat-dashboard` additions; if jules had no changes to these files, there should be no conflict.

**`cogs/memory/db/procedural_storage.py`** or **`cogs/memory/users/manager.py`**: If conflict appears here, prefer `feat-dashboard` side for now — Task 9 will layer the best N+1 fix on top.

**`base_configs/base.yaml`**: Accept `feat-dashboard`'s additions (dashboard config keys).

After resolving each file:
```bash
python -c "import ast; ast.parse(open('<filename>').read()); print('OK')"
git add <filename>
```

- [ ] **Step 4: Complete merge commit**

```bash
git commit -m "merge: feat-dashboard — web dashboard, config GUI, and memory management UI (conflicts resolved)"
```

- [ ] **Step 5: Verify all Python files parse**

```bash
find . -name "*.py" -not -path "./.git/*" -not -path "./dashboard-frontend/*" | xargs -I{} python -c "import ast; ast.parse(open('{}').read())" 2>&1 | grep -v "^$" || echo "All Python files OK"
```

Expected: No output (or "All Python files OK") — zero parse errors.

---

## Task 7: Parallel Analysis — Episodic Memory Branches (10 branches)

**Goal:** Select the single best implementation of TTL cache invalidation + thundering herd protection for `llm/memory/episodic.py`.

**Files to analyze:** `llm/memory/episodic.py` (primary), `cogs/memory/services/vectorization_service.py` (secondary)

- [ ] **Step 1: Spawn two parallel Research agents to analyze 5 branches each**

Agent A analyzes:
```
origin/feat/episodic-cache-invalidation-14303117678071509552
origin/feat/episodic-cache-invalidation-9994507373146319024
origin/feat/episodic-memory-invalidation-6883572420221573079
origin/feature/episodic-cache-stampede-protection-5632036186227064419
origin/feature/thundering-herd-episodic-memory-14639554855333254375
```

Agent B analyzes:
```
origin/perf-episodic-herd-protection-2076966194897591363
origin/perf-episodic-herd-protection-5179611711499615457
origin/perf/add-episodic-thundering-herd-protection-6333206903023604760
origin/perf/cache-stampede-protection-5904977498386338677
origin/perf/episodic-memory-provider-improvements-3816913018741036409
```

Each agent runs:
```bash
git show origin/<branch>:llm/memory/episodic.py
```

And scores each branch on:
- **Functional completeness (60%):** Does it handle cache stampede AND thundering herd? Is the asyncio.Lock/Event usage correct? Are TTL invalidation and manual invalidation both implemented? Does it handle exceptions without leaving locks held?
- **Code quality (40%):** Is the implementation concise? Does it follow the existing class structure in `llm/memory/episodic.py`? Are variable names clear?

- [ ] **Step 2: Consolidate scores and select winner**

Present a ranked table like:
```
Branch                                  | Functional | Quality | Total
feat/episodic-cache-invalidation-143... |    55/60   |  35/40  |  90
...
```

Select the highest-scoring branch. If tied, prefer the one with both stampede protection AND thundering herd (more complete).

**Record the winner here:** `origin/___________`

- [ ] **Step 3: Confirm selection with user before proceeding to Task 8**

---

## Task 8: Merge Selected Episodic Memory Branch

**Files:**
- Modify: `llm/memory/episodic.py`
- Modify: `cogs/memory/services/vectorization_service.py` (if changed)

- [ ] **Step 1: Show final diff of selected branch**

```bash
git diff origin/jules...origin/<selected-branch> -- llm/memory/episodic.py
```

- [ ] **Step 2: Merge**

```bash
git merge origin/<selected-branch> --no-ff -m "merge: add TTL cache invalidation and thundering herd protection to EpisodicMemoryProvider"
```

If conflict in `llm/memory/episodic.py`: keep the selected branch's version of the cache/lock logic; preserve any feat-dashboard additions if they don't overlap.

- [ ] **Step 3: Verify**

```bash
python -c "import ast; ast.parse(open('llm/memory/episodic.py').read()); print('OK')"
git log --oneline -1
```

Expected: `OK` and merge commit present.

---

## Task 9: Parallel Analysis — Procedural Memory Branches (6 branches)

**Goal:** Select the single best implementation of batched SQL queries to eliminate N+1 in `ProceduralStorage`.

**Files to analyze:** `cogs/memory/db/procedural_storage.py` (primary), `cogs/memory/users/manager.py` (secondary)

- [ ] **Step 1: Spawn parallel Research agents (split 3+3)**

Agent A analyzes:
```
origin/feat/procedural-storage-batched-query-18022322968939015522
origin/perf-batch-user-queries-11854023974540646687
origin/perf-fix-n-plus-1-procedural-storage-10263388373534883398
```

Agent B analyzes:
```
origin/perf/fix-n-plus-one-procedural-17307369727105486593
origin/perf/optimize-get-multiple-users-8841982453602564851
origin/perf/resolve-n-plus-1-procedural-memory-4482683441739565306
```

Each agent runs:
```bash
git show origin/<branch>:cogs/memory/db/procedural_storage.py
git show origin/<branch>:cogs/memory/users/manager.py
```

Score each on:
- **Functional completeness (60%):** Does the batch query handle empty lists? Does it preserve per-user ordering? Is the SQL injection-safe (parameterized queries)? Does it fall back gracefully if batch fails?
- **Code quality (40%):** Is the batched method a clean addition or does it restructure unrelated code? Is naming consistent with the existing `ProceduralStorage` class?

- [ ] **Step 2: Consolidate and select winner**

Present ranked table. Select the highest scorer. If tied, prefer the one with explicit empty-list handling (safer edge case).

**Record the winner here:** `origin/___________`

- [ ] **Step 3: Confirm selection with user before proceeding to Task 10**

---

## Task 10: Merge Selected Procedural Memory Branch

**Files:**
- Modify: `cogs/memory/db/procedural_storage.py`
- Modify: `cogs/memory/users/manager.py`

- [ ] **Step 1: Show final diff**

```bash
git diff origin/jules...origin/<selected-branch> -- cogs/memory/db/procedural_storage.py cogs/memory/users/manager.py
```

- [ ] **Step 2: Merge**

```bash
git merge origin/<selected-branch> --no-ff -m "merge: resolve N+1 DB query bottleneck in procedural memory with batched SQL"
```

If conflict: `feat-dashboard` may have touched these files. Keep the batched SQL logic from the selected branch; keep any dashboard-specific additions from `feat-dashboard` (e.g., new API endpoints that call `get_multiple_users`). Do not discard either side's unique logic.

- [ ] **Step 3: Verify**

```bash
python -c "import ast; ast.parse(open('cogs/memory/db/procedural_storage.py').read()); print('OK')"
python -c "import ast; ast.parse(open('cogs/memory/users/manager.py').read()); print('OK')"
git log --oneline -1
```

Expected: both `OK` and merge commit present.

---

## Task 11: Final Verification

- [ ] **Step 1: Full Python syntax check**

```bash
find . -name "*.py" -not -path "./.git/*" -not -path "./dashboard-frontend/*" | while read f; do
  python -c "import ast; ast.parse(open('$f').read())" 2>&1 && true || echo "FAIL: $f"
done | grep FAIL || echo "All Python files parse OK"
```

Expected: `All Python files parse OK`

- [ ] **Step 2: Check git log — verify all merges are present**

```bash
git log --oneline --merges | head -10
```

Expected: 7 merge commits visible (docs, fix-on-tree, ux-slash, knowledge-save, feat-dashboard, episodic-best, procedural-best).

- [ ] **Step 3: Push jules to remote**

```bash
git push origin jules
```

Expected: `jules` remote updated with all 7 merged branches.

- [ ] **Step 4: Summary report**

```bash
git log --oneline origin/main..jules | wc -l
echo "commits ahead of main"
git diff origin/main...jules --name-only | sort | uniq | wc -l
echo "files changed vs main"
```

Record results. `jules` is now ready to open a PR into `main`.
