# Database Migrations Guide

A reference for how schema changes are made in this project, what was cleaned up to get here, and the exact commands to use going forward. Written for a beginner maintaining a production backend — read top to bottom once, then use it as a lookup.

---

## 1. What a migration actually is

Your database has a **schema** — the shape of your tables: which columns exist, their types, constraints, indexes. Your code (the SQLAlchemy models in `app/models/`) also describes that same shape.

The problem: when you change a model in code (add a column, add a table), the *already-running production database* has no idea. It still has the old shape. A **migration** is a small, ordered, written-down recipe that says exactly how to change the live database's shape to match the new code — for example:

> "Add column `is_trial` (boolean, default false) to table `subscriptions`."

**Alembic** is the tool that manages an ordered *sequence* of these recipes — think of it like a git commit history, but for your database schema instead of your code. Every file in `migrations/versions/` is one step, and each step points to the step before it via `down_revision`, forming a single chain.

Each migration file has two functions:

| Function | Purpose |
|---|---|
| `upgrade()` | Moves the database forward one step (applies the change) |
| `downgrade()` | Reverses that exact step, if something goes wrong |

Alembic also keeps one small table inside your actual database — `alembic_version` — holding a single row that records exactly which migration the database is currently on. Running `alembic upgrade head` looks at that row, sees where you are, and only runs the migrations after it. Nothing re-runs, nothing runs out of order.

**A migration is only needed when the *shape* of stored data changes.** A normal bug fix (fixing logic, fixing a calculation, fixing a typo in a response) needs no migration at all — fix the code, deploy, done.

---

## 2. The problem this project had, and what was fixed

### The two-system problem

Before this cleanup, there were **two systems both changing the database schema**, and only one of them was safe:

1. **Alembic** — 14 real, versioned migrations (`0001`–`0014`), the correct tool.
2. **28 ad-hoc functions inside `app/main.py`** — each one ran an idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`-style check automatically, on **every single server restart**, with no versioning, no review step, and no way to know which database had which changes applied.

This mattered for one specific, serious reason: **Alembic tracks state, the `main.py` functions didn't.** If you ever pointed this app at a brand-new database — a staging environment, or your first production database on GCP — running `alembic upgrade head` would only bring it to `0014`. Every schema change that only ever lived in the 28 `main.py` functions (new tables, new columns, unique constraints — changes going back to purchase invoice dates, GSTR support, customer uniqueness keys, and more) would be **silently missing**, and the app would crash the first time it touched one of those missing columns.

### What was done about it

All 28 functions were ported 1:1 into new, real Alembic migrations — `migrations/versions/0015_*.py` through `0043_*.py` — each with:

- The exact same idempotent logic as the original function (safe to run on a database that already has some of the columns).
- A real `downgrade()`. Where a clean, safe reversal is possible (a single added column or index), it drops it. Where reversing would either destroy real data or be misleading (a one-time backfill, a dedup step, a retired table), the `downgrade()` is a documented no-op that says so explicitly — it does **not** pretend to undo something it safely can't. A **backup taken before the upgrade** is the real safety net for those cases, not `downgrade()`.

`app/main.py` was then cleaned up: all 28 functions and their `try/except` startup calls were removed. What's left in `main.py` is just table creation on boot (`Base.metadata.create_all`, which only ever *creates* missing tables, never alters existing ones) and `_seed_default_plans()` — which was **kept**, because it inserts/corrects *data* (subscription plan prices), not schema, and idempotent data seeding on boot is a reasonable pattern to keep.

This was verified end-to-end: `alembic upgrade head` was run against the real dev database, applied all 29 new migrations cleanly, landed at `0043 (head)`, and the app started and ran normally afterward.

**Current state:** one single source of truth for schema — `migrations/versions/`. Any fresh database, anywhere, gets to the exact same schema by running one command: `alembic upgrade head`.

---

## 3. The day-to-day workflow for a schema change

This is the process to follow every time a code change needs a new column, table, index, or constraint:

1. **Change the SQLAlchemy model** in `app/models/` (e.g. add a new column to `Coupon`).
2. **Generate a draft migration:**
   ```bash
   alembic revision --autogenerate -m "add coupon min_order_amount"
   ```
   Alembic diffs your models against what it believes the database looks like, and writes a draft file into `migrations/versions/`.
3. **Read the generated file carefully.** Autogenerate is a helpful first draft, not gospel — see the blind spots below. Edit it by hand if it got something wrong.
4. **Test it against a copy of production data** — a staging environment, or at minimum a local/dev database restored from a recent backup. Never let an untested migration touch production first.
5. **Take a fresh backup of production** immediately before deploying.
6. **Deploy the new code.**
7. **Run the migration against production:**
   ```bash
   alembic upgrade head
   ```
8. **Verify** — check the app works, watch logs for errors.
9. **If something's wrong:** `alembic downgrade -1` reverts the last step *if* its `downgrade()` is a real, safe reversal. If not (or if data was already lost), restore from the backup taken in step 5. The backup is always the true safety net.

For a **pure bug fix with no schema change** — the vast majority of fixes — skip all of this. Fix the code, test it, deploy. No migration involved.

---

## 4. Alembic commands, one at a time

| Command | What it does |
|---|---|
| `alembic current` | Shows which migration the *connected database* is currently on. Reads the single row in the `alembic_version` table. |
| `alembic history` | Lists every migration in order, whether applied or not. Good sanity check that the chain hasn't branched. |
| `alembic upgrade head` | Applies every migration between the database's current position and the newest one. |
| `alembic upgrade <revision_id>` | Applies migrations up to (and including) a specific revision, not necessarily the newest. |
| `alembic downgrade -1` | Reverts exactly one step — runs the `downgrade()` of whatever is currently at head. |
| `alembic downgrade <revision_id>` | Reverts back to a specific point, running every `downgrade()` in between, in reverse order. |
| `alembic revision --autogenerate -m "message"` | Diffs your models against the database and writes a **draft** migration file for the difference. |
| `alembic show <revision_id>` | Prints one migration file's contents without hunting for it manually. |

---

## 5. Autogenerate's blind spots (read this before trusting a generated file)

Autogenerate is reliable for:
- New or dropped tables
- New or dropped columns
- New or dropped indexes
- Column type changes

Autogenerate is **unreliable or blind** for:

| Situation | What goes wrong |
|---|---|
| **Renaming a column** | Autogenerate sees "one column disappeared, a different one appeared" and writes `drop_column` + `add_column` — this **deletes all data** in that column instead of preserving it under the new name. You must hand-edit this into `op.alter_column(..., new_column_name=...)`. |
| **Renaming a table** | Same problem — treated as a drop + a fresh create. |
| **Data-only changes** | Backfills, one-time corrections, deduping rows — autogenerate never generates these, because there's no model diff to detect. You write these by hand (see `0040_deactivate_stale_bills.py` or the plan-price backfill in `_seed_default_plans` as examples already in this repo). |
| **Some constraint/check-constraint changes** | Behavior varies by database backend; always worth a manual read. |

**Rule of thumb: never run `alembic upgrade head` against a generated migration you haven't personally read.** Treat every autogenerated file as a first draft.

---

## 6. A safe practice exercise

Whenever you want the workflow to become muscle memory, try this on something trivial and low-stakes (e.g. a nullable `notes` text column on some table that isn't load-bearing):

1. Add the column to the SQLAlchemy model.
2. `alembic revision --autogenerate -m "add notes column"`
3. Open the generated file and confirm it only does that one thing.
4. `alembic upgrade head`
5. `alembic current` — confirm it moved forward.
6. `alembic downgrade -1` — confirm the column disappears cleanly.
7. `alembic upgrade head` again — back to normal.

Doing this round-trip once, even on a throwaway column, is usually what makes the whole workflow click.

---

## 7. Quick reference — what NOT to do

- Don't hand-write `ALTER TABLE` statements directly against production. Always go through a migration file, even for a "quick" change — that's exactly how this project ended up with 28 undocumented ad-hoc functions in the first place.
- Don't run `alembic upgrade head` against production without a fresh backup taken first.
- Don't trust an autogenerated migration you haven't read, especially around renames.
- Don't assume `downgrade()` is a substitute for a backup — some changes genuinely can't be safely auto-reversed, and this project's own migrations are honest about which ones (see their `downgrade()` comments).
