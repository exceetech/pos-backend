-- Reclassify historical SETTLE rows into WRITE_OFF / REFUND.
--
-- Mirror of the Android Room migration 48 → 49, so both sides describe the
-- same events the same way.
--
-- WHY
--   SETTLE meant two opposite things: a debt forgiven (no cash moved) and a
--   customer's advance handed back (cash left the shop). One type for two
--   events forced every reader to work out which by replaying the ledger, and
--   it put refunds on the sales side of the books.
--
--   Settles written before the amount was recorded stored 0, so the sum
--   involved was lost from the row. This restores it from the balance that was
--   standing at that moment.
--
-- WHAT IT DOES
--   For each SETTLE, sums the account's transactions since the previous settle:
--     balance > 0  → the debt was forgiven      → WRITE_OFF
--     balance < 0  → the advance was returned   → REFUND
--   and rewrites `amount` to the magnitude of that balance.
--
-- ORDER OF OPERATIONS
--   1. Deploy the backend that accepts WRITE_OFF / REFUND (credit_routes.py).
--   2. Run the SELECT below and eyeball the result.
--   3. Run the UPDATE inside a transaction.
--   4. Then repair credit_accounts.due_amount if payments were ever inverted
--      by the old PAY bug — see the recompute query at the bottom.
--
-- SAFE TO RE-RUN: it only touches rows still typed SETTLE.

-- ─────────────────────────────────────────────────────────────────────────
-- 1. PREVIEW — run this first, change nothing
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    r.id,
    r.account_id,
    r.amount AS stored_amount,
    (SELECT COALESCE(SUM(CASE
            WHEN t.type IN ('ADD','PURCHASE_CREDIT','PURCHASE_RETURN') THEN t.amount
            WHEN t.type = 'PAY' THEN -t.amount
            ELSE 0 END), 0)
     FROM credit_transactions t
     WHERE t.account_id = r.account_id
       AND t.shop_id = r.shop_id
       AND (t.created_at < r.created_at
            OR (t.created_at = r.created_at AND t.id < r.id))
       AND NOT EXISTS (
            SELECT 1 FROM credit_transactions s
            WHERE s.account_id = r.account_id
              AND s.shop_id = r.shop_id
              AND s.type IN ('SETTLE','WRITE_OFF','REFUND')
              AND (s.created_at > t.created_at
                   OR (s.created_at = t.created_at AND s.id > t.id))
              AND (s.created_at < r.created_at
                   OR (s.created_at = r.created_at AND s.id < r.id)))
    ) AS balance_before
FROM credit_transactions r
WHERE r.type = 'SETTLE'
ORDER BY r.account_id, r.created_at, r.id;


-- ─────────────────────────────────────────────────────────────────────────
-- 2. APPLY — wrap in a transaction so it can be rolled back
-- ─────────────────────────────────────────────────────────────────────────
-- BEGIN;

UPDATE credit_transactions AS r
SET type = CASE WHEN bal.balance_before < 0 THEN 'REFUND' ELSE 'WRITE_OFF' END,
    amount = ABS(bal.balance_before)
FROM (
    SELECT
        r2.id,
        (SELECT COALESCE(SUM(CASE
                WHEN t.type IN ('ADD','PURCHASE_CREDIT','PURCHASE_RETURN') THEN t.amount
                WHEN t.type = 'PAY' THEN -t.amount
                ELSE 0 END), 0)
         FROM credit_transactions t
         WHERE t.account_id = r2.account_id
           AND t.shop_id = r2.shop_id
           AND (t.created_at < r2.created_at
                OR (t.created_at = r2.created_at AND t.id < r2.id))
           AND NOT EXISTS (
                SELECT 1 FROM credit_transactions s
                WHERE s.account_id = r2.account_id
                  AND s.shop_id = r2.shop_id
                  AND s.type IN ('SETTLE','WRITE_OFF','REFUND')
                  AND (s.created_at > t.created_at
                       OR (s.created_at = t.created_at AND s.id > t.id))
                  AND (s.created_at < r2.created_at
                       OR (s.created_at = r2.created_at AND s.id < r2.id)))
        ) AS balance_before
    FROM credit_transactions r2
    WHERE r2.type = 'SETTLE'
) AS bal
WHERE r.id = bal.id;

-- COMMIT;


-- ─────────────────────────────────────────────────────────────────────────
-- 3. RECOMPUTE ACCOUNT BALANCES
-- ─────────────────────────────────────────────────────────────────────────
-- Run after step 2. Repairs due_amount for accounts damaged by the old PAY
-- bug, which added payments instead of subtracting them.
--
-- SETTLE, WRITE_OFF and REFUND all CLOSE the account at zero, so only the
-- transactions after the most recent one of those count. They are boundaries,
-- not amounts: their stored figure is never added or subtracted here.
--
-- That matters. An adjustment resets the balance rather than adjusting it, so
-- its stored amount can differ from the sum actually cleared — that happens
-- whenever a settle re-synchronises a device and server that had drifted
-- apart, which is precisely the situation this script exists to repair.
-- Replaying them as deltas gave a balance the app disagreed with: a settle
-- storing 700 against a server balance of 9,999 produced -8,799 instead of 0.
--
-- All three types are matched, so this is correct whether or not step 2 has
-- already run.
--
-- The boundary is ordered by created_at with id as the tie-break, matching
-- step 2 and the app. Ordering by id alone can disagree when rows arrive from
-- more than one device.
--
-- Preview first by turning the UPDATE into a SELECT.

UPDATE credit_accounts a
SET due_amount = COALESCE((
    SELECT SUM(CASE
        WHEN t.type IN ('ADD','PURCHASE_CREDIT','PURCHASE_RETURN') THEN  t.amount
        WHEN t.type = 'PAY' THEN -t.amount
        ELSE 0 END)
    FROM credit_transactions t
    WHERE t.account_id = a.id
      AND t.shop_id = a.shop_id
      AND NOT EXISTS (
            SELECT 1 FROM credit_transactions s
            WHERE s.account_id = a.id
              AND s.shop_id = a.shop_id
              AND s.type IN ('SETTLE','WRITE_OFF','REFUND')
              AND (s.created_at > t.created_at
                   OR (s.created_at = t.created_at AND s.id > t.id)))
), 0)
WHERE a.is_active = true;
