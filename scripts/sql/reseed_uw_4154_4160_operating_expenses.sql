-- Reseed uw_operating_expenses for underwritings 4154..4160, whose opex
-- was imported from the GSheet rather than seeded from market data. All 7 deals
-- were holding zero expense rows.
--
-- Amounts are the sheet's. Labels and sort_order come from
-- app.iron_bank.services.opex_catalog.OPEX_ROWS, so every deal carries the full
-- 13-row catalog in canonical order and nothing can drift from what the app
-- seeds on save. A catalog row the sheet had no figure for is inserted at 0.00
-- and marked; the sheet's "Other" and "PMI" columns were blank on every deal and
-- map to no catalog row, so both are dropped.
--
-- One transaction per deal: check each verify SELECT before its COMMIT.

-- underwriting_id=4154  13 catalog rows, 13 from the sheet, 0 placeholder

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4154;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (4154, 'Internet',                     100.00,  0),
    (4154, 'Utilities',                    450.00,  1),
    (4154, 'Pest Control',                  60.00,  2),
    (4154, 'Pool/Hot Tub Maintenance',     150.00,  3),
    (4154, 'Outdoor/Landscaping',          125.00,  4),
    (4154, 'Software',                      50.00,  5),
    (4154, 'Household Supplies',           175.00,  6),
    (4154, 'Cleaning',                    1300.00,  7),
    (4154, 'Property Taxes (Monthly)',     485.00,  8),
    (4154, 'Insurance HOI',                325.00,  9),
    (4154, 'CapEx Reserve',                375.00, 10),
    (4154, 'MISC',                           0.00, 11),
    (4154, 'HOA Fees',                       0.00, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4154
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4155  13 catalog rows, 13 from the sheet, 0 placeholder

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4155;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (4155, 'Internet',                     100.00,  0),
    (4155, 'Utilities',                    750.00,  1),
    (4155, 'Pest Control',                  75.00,  2),
    (4155, 'Pool/Hot Tub Maintenance',     350.00,  3),
    (4155, 'Outdoor/Landscaping',          125.00,  4),
    (4155, 'Software',                      50.00,  5),
    (4155, 'Household Supplies',           300.00,  6),
    (4155, 'Cleaning',                    1875.00,  7),
    (4155, 'Property Taxes (Monthly)',     450.00,  8),
    (4155, 'Insurance HOI',                650.00,  9),
    (4155, 'CapEx Reserve',                750.00, 10),
    (4155, 'MISC',                           0.00, 11),
    (4155, 'HOA Fees',                       0.00, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4155
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4156  13 catalog rows, 13 from the sheet, 0 placeholder

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4156;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (4156, 'Internet',                     100.00,  0),
    (4156, 'Utilities',                    725.00,  1),
    (4156, 'Pest Control',                  60.00,  2),
    (4156, 'Pool/Hot Tub Maintenance',     350.00,  3),
    (4156, 'Outdoor/Landscaping',          125.00,  4),
    (4156, 'Software',                      50.00,  5),
    (4156, 'Household Supplies',           200.00,  6),
    (4156, 'Cleaning',                    1438.00,  7),
    (4156, 'Property Taxes (Monthly)',     785.00,  8),
    (4156, 'Insurance HOI',                400.00,  9),
    (4156, 'CapEx Reserve',                475.00, 10),
    (4156, 'MISC',                           0.00, 11),
    (4156, 'HOA Fees',                       0.00, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4156
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4157  13 catalog rows, 13 from the sheet, 0 placeholder

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4157;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (4157, 'Internet',                     100.00,  0),
    (4157, 'Utilities',                    675.00,  1),
    (4157, 'Pest Control',                  60.00,  2),
    (4157, 'Pool/Hot Tub Maintenance',     325.00,  3),
    (4157, 'Outdoor/Landscaping',          225.00,  4),
    (4157, 'Software',                      50.00,  5),
    (4157, 'Household Supplies',           200.00,  6),
    (4157, 'Cleaning',                    1500.00,  7),
    (4157, 'Property Taxes (Monthly)',     950.00,  8),
    (4157, 'Insurance HOI',                685.00,  9),
    (4157, 'CapEx Reserve',                450.00, 10),
    (4157, 'MISC',                           0.00, 11),
    (4157, 'HOA Fees',                       0.00, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4157
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4158  13 catalog rows, 13 from the sheet, 0 placeholder

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4158;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (4158, 'Internet',                     125.00,  0),
    (4158, 'Utilities',                    775.00,  1),
    (4158, 'Pest Control',                 100.00,  2),
    (4158, 'Pool/Hot Tub Maintenance',     400.00,  3),
    (4158, 'Outdoor/Landscaping',          125.00,  4),
    (4158, 'Software',                      50.00,  5),
    (4158, 'Household Supplies',           250.00,  6),
    (4158, 'Cleaning',                    1950.00,  7),
    (4158, 'Property Taxes (Monthly)',     400.00,  8),
    (4158, 'Insurance HOI',                465.00,  9),
    (4158, 'CapEx Reserve',                450.00, 10),
    (4158, 'MISC',                           0.00, 11),
    (4158, 'HOA Fees',                     100.00, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4158
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4159  13 catalog rows, 13 from the sheet, 0 placeholder

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4159;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (4159, 'Internet',                     200.00,  0),
    (4159, 'Utilities',                   1500.00,  1),
    (4159, 'Pest Control',                 150.00,  2),
    (4159, 'Pool/Hot Tub Maintenance',     200.00,  3),
    (4159, 'Outdoor/Landscaping',          200.00,  4),
    (4159, 'Software',                      50.00,  5),
    (4159, 'Household Supplies',           575.00,  6),
    (4159, 'Cleaning',                    2763.00,  7),
    (4159, 'Property Taxes (Monthly)',    1425.00,  8),
    (4159, 'Insurance HOI',               1150.00,  9),
    (4159, 'CapEx Reserve',               1250.00, 10),
    (4159, 'MISC',                           0.00, 11),
    (4159, 'HOA Fees',                       0.00, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4159
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4160  13 catalog rows, 11 from the sheet, 2 placeholder

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4160;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (4160, 'Internet',                     175.00,  0),
    (4160, 'Utilities',                   1100.00,  1),
    (4160, 'Pest Control',                  80.00,  2),
    (4160, 'Pool/Hot Tub Maintenance',     400.00,  3),
    (4160, 'Outdoor/Landscaping',          125.00,  4),
    (4160, 'Software',                       0.00,  5),
    (4160, 'Household Supplies',           300.00,  6),
    (4160, 'Cleaning',                    2338.00,  7),
    (4160, 'Property Taxes (Monthly)',    1200.00,  8),
    (4160, 'Insurance HOI',                700.00,  9),
    (4160, 'CapEx Reserve',                675.00, 10),
    (4160, 'MISC',                           0.00, 11),  -- placeholder, not on the sheet
    (4160, 'HOA Fees',                       0.00, 12);  -- placeholder, not on the sheet

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 4160
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

