-- ACTIVITY_CLASS
CASE WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('savings') AND tags.is_deleted = false))) THEN 'savings' WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('debt_principal') AND tags.is_deleted = false))) THEN 'debt_principal' WHEN ((transactions.transfer_id IS NOT NULL OR xfer_payee.transfer_account_id IS NOT NULL) AND NOT coalesce(counterpart_acct.on_budget, true) AND coalesce(counterpart_acct.classification, 'asset') != 'liability' AND coalesce(counterpart_acct.counts_as_savings, true)) THEN 'savings' WHEN ((transactions.transfer_id IS NOT NULL OR xfer_payee.transfer_account_id IS NOT NULL) AND NOT coalesce(counterpart_acct.on_budget, true) AND coalesce(counterpart_acct.classification, 'asset') = 'liability') THEN 'debt_principal' WHEN ((transactions.transfer_id IS NOT NULL OR xfer_payee.transfer_account_id IS NOT NULL) AND transactions.category_id IS NULL AND NOT (own_acct.on_budget = true AND NOT coalesce(counterpart_acct.on_budget, true) AND coalesce(counterpart_acct.classification, 'asset') != 'liability' AND NOT coalesce(counterpart_acct.counts_as_savings, true))) THEN 'transfer_internal' WHEN (own_acct.on_budget = false AND own_acct.classification != 'liability') THEN 'investment_return' WHEN (own_acct.on_budget = false AND own_acct.classification = 'liability') THEN 'debt_interest' WHEN (transactions.amount > 0 AND transactions.category_id IS NULL OR (EXISTS (SELECT categories.id 
FROM categories, transactions 
WHERE categories.id = transactions.category_id AND (EXISTS (SELECT category_groups.id 
FROM category_groups 
WHERE category_groups.id = categories.category_group_id AND category_groups.is_system = true))))) THEN 'income' ELSE 'spending' END
-- ACTIVITY_REASON
CASE WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('savings') AND tags.is_deleted = false))) THEN 'tagged_savings' WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('debt_principal') AND tags.is_deleted = false))) THEN 'tagged_debt' WHEN ((transactions.transfer_id IS NOT NULL OR xfer_payee.transfer_account_id IS NOT NULL) AND NOT coalesce(counterpart_acct.on_budget, true) AND coalesce(counterpart_acct.classification, 'asset') != 'liability' AND coalesce(counterpart_acct.counts_as_savings, true)) THEN 'transfer_to_tracked_asset' WHEN ((transactions.transfer_id IS NOT NULL OR xfer_payee.transfer_account_id IS NOT NULL) AND NOT coalesce(counterpart_acct.on_budget, true) AND coalesce(counterpart_acct.classification, 'asset') = 'liability') THEN 'transfer_to_tracked_debt' WHEN ((transactions.transfer_id IS NOT NULL OR xfer_payee.transfer_account_id IS NOT NULL) AND transactions.category_id IS NULL AND NOT (own_acct.on_budget = true AND NOT coalesce(counterpart_acct.on_budget, true) AND coalesce(counterpart_acct.classification, 'asset') != 'liability' AND NOT coalesce(counterpart_acct.counts_as_savings, true))) THEN 'internal_transfer' WHEN (own_acct.on_budget = false AND own_acct.classification != 'liability') THEN 'tracked_asset_activity' WHEN (own_acct.on_budget = false AND own_acct.classification = 'liability') THEN 'tracked_debt_activity' WHEN (transactions.amount > 0 AND transactions.category_id IS NULL OR (EXISTS (SELECT categories.id 
FROM categories, transactions 
WHERE categories.id = transactions.category_id AND (EXISTS (SELECT category_groups.id 
FROM category_groups 
WHERE category_groups.id = categories.category_group_id AND category_groups.is_system = true))))) THEN 'uncategorized_inflow' ELSE 'default_spending' END
-- ACTIVITY_CLASS_SUBQUERY
CASE WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('savings') AND tags.is_deleted = false))) THEN 'savings' WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('debt_principal') AND tags.is_deleted = false))) THEN 'debt_principal' WHEN ((transactions.transfer_id IS NOT NULL OR (EXISTS (SELECT payees.id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id AND payees.transfer_account_id IS NOT NULL))) AND NOT coalesce((SELECT accounts.on_budget 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true) AND coalesce((SELECT accounts.classification 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), 'asset') != 'liability' AND coalesce((SELECT accounts.counts_as_savings 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true)) THEN 'savings' WHEN ((transactions.transfer_id IS NOT NULL OR (EXISTS (SELECT payees.id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id AND payees.transfer_account_id IS NOT NULL))) AND NOT coalesce((SELECT accounts.on_budget 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true) AND coalesce((SELECT accounts.classification 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), 'asset') = 'liability') THEN 'debt_principal' WHEN ((transactions.transfer_id IS NOT NULL OR (EXISTS (SELECT payees.id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id AND payees.transfer_account_id IS NOT NULL))) AND transactions.category_id IS NULL AND NOT ((SELECT accounts.on_budget 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = true AND NOT coalesce((SELECT accounts.on_budget 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true) AND coalesce((SELECT accounts.classification 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), 'asset') != 'liability' AND NOT coalesce((SELECT accounts.counts_as_savings 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true))) THEN 'transfer_internal' WHEN ((SELECT accounts.on_budget 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = false AND (SELECT accounts.classification 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) != 'liability') THEN 'investment_return' WHEN ((SELECT accounts.on_budget 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = false AND (SELECT accounts.classification 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = 'liability') THEN 'debt_interest' WHEN (transactions.amount > 0 AND transactions.category_id IS NULL OR (EXISTS (SELECT categories.id 
FROM categories, transactions 
WHERE categories.id = transactions.category_id AND (EXISTS (SELECT category_groups.id 
FROM category_groups 
WHERE category_groups.id = categories.category_group_id AND category_groups.is_system = true))))) THEN 'income' ELSE 'spending' END
-- ACTIVITY_REASON_SUBQUERY
CASE WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('savings') AND tags.is_deleted = false))) THEN 'tagged_savings' WHEN (transactions.category_id IS NOT NULL AND transactions.category_id IN (SELECT category_tags.category_id 
FROM category_tags 
WHERE category_tags.tag_id IN (SELECT tags.id 
FROM tags 
WHERE tags.system_key IN ('debt_principal') AND tags.is_deleted = false))) THEN 'tagged_debt' WHEN ((transactions.transfer_id IS NOT NULL OR (EXISTS (SELECT payees.id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id AND payees.transfer_account_id IS NOT NULL))) AND NOT coalesce((SELECT accounts.on_budget 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true) AND coalesce((SELECT accounts.classification 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), 'asset') != 'liability' AND coalesce((SELECT accounts.counts_as_savings 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true)) THEN 'transfer_to_tracked_asset' WHEN ((transactions.transfer_id IS NOT NULL OR (EXISTS (SELECT payees.id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id AND payees.transfer_account_id IS NOT NULL))) AND NOT coalesce((SELECT accounts.on_budget 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true) AND coalesce((SELECT accounts.classification 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), 'asset') = 'liability') THEN 'transfer_to_tracked_debt' WHEN ((transactions.transfer_id IS NOT NULL OR (EXISTS (SELECT payees.id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id AND payees.transfer_account_id IS NOT NULL))) AND transactions.category_id IS NULL AND NOT ((SELECT accounts.on_budget 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = true AND NOT coalesce((SELECT accounts.on_budget 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true) AND coalesce((SELECT accounts.classification 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), 'asset') != 'liability' AND NOT coalesce((SELECT accounts.counts_as_savings 
FROM accounts 
WHERE accounts.id = coalesce((SELECT transactions_1.account_id 
FROM transactions AS transactions_1, transactions 
WHERE transactions_1.id = transactions.transfer_id), (SELECT payees.transfer_account_id 
FROM payees, transactions 
WHERE payees.id = transactions.payee_id))), true))) THEN 'internal_transfer' WHEN ((SELECT accounts.on_budget 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = false AND (SELECT accounts.classification 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) != 'liability') THEN 'tracked_asset_activity' WHEN ((SELECT accounts.on_budget 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = false AND (SELECT accounts.classification 
FROM accounts, transactions 
WHERE accounts.id = transactions.account_id) = 'liability') THEN 'tracked_debt_activity' WHEN (transactions.amount > 0 AND transactions.category_id IS NULL OR (EXISTS (SELECT categories.id 
FROM categories, transactions 
WHERE categories.id = transactions.category_id AND (EXISTS (SELECT category_groups.id 
FROM category_groups 
WHERE category_groups.id = categories.category_group_id AND category_groups.is_system = true))))) THEN 'uncategorized_inflow' ELSE 'default_spending' END
