# Branch Merge Design: All Remote Branches → jules → main

**Date:** 2026-05-17  
**Author:** starpig1129  
**Target branch:** `jules`  
**Final target:** `main`

## Overview

This document describes the plan to evaluate and merge all meaningful remote branches into `jules` first, then integrate `jules` into `main`. Branches are categorized into unique features and duplicate AI-generated optimization branches.

## Branch Inventory

### Excluded Branches
| Branch | Reason |
|--------|--------|
| `gh-pages` | GitHub Pages static assets, unrelated to bot code |
| `melvin0kuo-main` | Identical to `main`, nothing to merge |
| `musicBot` | Identical to `main`, nothing to merge |
| `main` | Final merge target, not a source |

### Phase 1: Unique Feature Branches (5 branches)
These branches each address a distinct feature or fix with no functional duplicates.

| Merge Order | Branch | Scope | Risk |
|-------------|--------|-------|------|
| 1 | `docs/generate-all-docs-9646874452220810181` | New doc files only | Lowest — pure additions |
| 2 | `fix-on-tree-error-messages-16870004965955776482` | `cogs/` error handler | Low — single fix |
| 3 | `ux/improve-slash-command-error-handling-10386039463375131800` | `cogs/` slash commands | Low-medium — may overlap with fix above |
| 4 | `feature/knowledge-save-command-17141402164890107963` | `cogs/userdata.py` | Low — new command addition |
| 5 | `feat-dashboard` | `dashboard/` + `cogs/` | Medium — widest change surface, merged last |

### Phase 2: Duplicate Optimization Branches (16 branches → 2 selected)

#### Category A: Episodic Memory Performance (10 branches, select 1)
All address the same problem: TTL cache invalidation and/or thundering herd protection for `EpisodicMemoryProvider`.

| Branch |
|--------|
| `feat/episodic-cache-invalidation-14303117678071509552` |
| `feat/episodic-cache-invalidation-9994507373146319024` |
| `feat/episodic-memory-invalidation-6883572420221573079` |
| `feature/episodic-cache-stampede-protection-5632036186227064419` |
| `feature/thundering-herd-episodic-memory-14639554855333254375` |
| `perf-episodic-herd-protection-2076966194897591363` |
| `perf-episodic-herd-protection-5179611711499615457` |
| `perf/add-episodic-thundering-herd-protection-6333206903023604760` |
| `perf/cache-stampede-protection-5904977498386338677` |
| `perf/episodic-memory-provider-improvements-3816913018741036409` |

#### Category B: Procedural Memory N+1 Fix (6 branches, select 1)
All address the same problem: batched SQL queries to eliminate N+1 in `ProceduralStorage`.

| Branch |
|--------|
| `feat/procedural-storage-batched-query-18022322968939015522` |
| `perf-batch-user-queries-11854023974540646687` |
| `perf-fix-n-plus-1-procedural-storage-10263388373534883398` |
| `perf/fix-n-plus-one-procedural-17307369727105486593` |
| `perf/optimize-get-multiple-users-8841982453602564851` |
| `perf/resolve-n-plus-1-procedural-memory-4482683441739565306` |

## Evaluation Criteria (Phase 2)

Parallel agent analysis is run on all branches within each category. Each branch is scored:

| Dimension | Weight | Assessment Method |
|-----------|--------|------------------|
| Functional completeness | 60% | Edge case coverage, async safety, lock correctness, cache invalidation logic |
| Code quality | 40% | Conciseness, naming consistency, alignment with existing codebase style |

The highest-scoring branch in each category is selected for merge. If scores are tied, functional completeness takes priority.

## Merge Execution

### Step 1: Switch to `jules` branch
```bash
git checkout jules
git pull origin jules
```

### Step 2: Phase 1 — merge unique branches in order (1→5)
```bash
git merge origin/<branch> --no-ff -m "merge: <branch>"
# Resolve conflicts automatically: prefer functionally complete side, then cleaner code
```

### Step 3: Phase 2 — parallel analysis of Episodic (10) and Procedural (6) branches
- Spawn two parallel Research agents
- Each produces a ranked comparison table
- User confirms selection

### Step 4: Phase 2 — merge selected best branches
```bash
git merge origin/<selected-episodic> --no-ff
git merge origin/<selected-procedural> --no-ff
```

## Conflict Resolution Policy

When merge conflicts arise, the automated resolution priority is:
1. **Keep the functionally more complete side** (more edge cases handled, proper locking)
2. **If functionally equivalent, keep the cleaner/simpler side**
3. **If ambiguous, flag and pause for user decision**

## Success Criteria

- All 7 target branches merged into `jules` with no unresolved conflicts
- `jules` passes bot startup (`python main.py`) without errors
- Git log on `jules` shows clean, traceable merge commits
- Ready for PR from `jules` → `main`
