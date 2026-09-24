-- Reseed uw_operating_expenses for 69 market_108 underwritings
-- still holding only the two placeholder rows (Property Taxes, MISC @ 0.00).
--
-- Generated from app.iron_bank.services.opex_catalog via
-- scripts/generate_uw_operating_expenses_sql.py, so the row set, labels,
-- amounts and sort_order match exactly what the app seeds on save.
--
-- One transaction per deal: check each verify SELECT before its COMMIT.
-- Deals 2344..2518; 897 rows inserted, 138 placeholders deleted.
-- underwriting_id=2344  market_id=108  bedrooms=3
-- property_size=2160 -> opex_by_size.sqft=2750  purchase_price=824900.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2344;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2344, 'Internet',                        150,  0),
    (2344, 'Utilities',                       625,  1),
    (2344, 'Pest Control',                     75,  2),
    (2344, 'Pool/Hot Tub Maintenance',        125,  3),
    (2344, 'Outdoor/Landscaping',             150,  4),
    (2344, 'Software',                          0,  5),
    (2344, 'Household Supplies',              175,  6),
    (2344, 'Cleaning',                       1050,  7),
    (2344, 'Property Taxes (Monthly)',     384.95,  8),
    (2344, 'Insurance HOI',                   250,  9),
    (2344, 'CapEx Reserve',                   350, 10),
    (2344, 'MISC',                              0, 11),
    (2344, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2344
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2347  market_id=108  bedrooms=3
-- property_size=2368 -> opex_by_size.sqft=2750  purchase_price=749000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2347;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2347, 'Internet',                        150,  0),
    (2347, 'Utilities',                       625,  1),
    (2347, 'Pest Control',                     75,  2),
    (2347, 'Pool/Hot Tub Maintenance',        125,  3),
    (2347, 'Outdoor/Landscaping',             150,  4),
    (2347, 'Software',                          0,  5),
    (2347, 'Household Supplies',              175,  6),
    (2347, 'Cleaning',                       1050,  7),
    (2347, 'Property Taxes (Monthly)',     349.53,  8),
    (2347, 'Insurance HOI',                   250,  9),
    (2347, 'CapEx Reserve',                   350, 10),
    (2347, 'MISC',                              0, 11),
    (2347, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2347
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2349  market_id=108  bedrooms=3
-- property_size=3386 -> opex_by_size.sqft=3500  purchase_price=740000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2349;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2349, 'Internet',                        150,  0),
    (2349, 'Utilities',                       700,  1),
    (2349, 'Pest Control',                     75,  2),
    (2349, 'Pool/Hot Tub Maintenance',        125,  3),
    (2349, 'Outdoor/Landscaping',             150,  4),
    (2349, 'Software',                          0,  5),
    (2349, 'Household Supplies',              175,  6),
    (2349, 'Cleaning',                       1050,  7),
    (2349, 'Property Taxes (Monthly)',     345.33,  8),
    (2349, 'Insurance HOI',                   250,  9),
    (2349, 'CapEx Reserve',                   350, 10),
    (2349, 'MISC',                              0, 11),
    (2349, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2349
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2352  market_id=108  bedrooms=3
-- property_size=1934 -> opex_by_size.sqft=2000  purchase_price=760000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2352;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2352, 'Internet',                        100,  0),
    (2352, 'Utilities',                       525,  1),
    (2352, 'Pest Control',                     60,  2),
    (2352, 'Pool/Hot Tub Maintenance',        125,  3),
    (2352, 'Outdoor/Landscaping',             150,  4),
    (2352, 'Software',                          0,  5),
    (2352, 'Household Supplies',              175,  6),
    (2352, 'Cleaning',                       1050,  7),
    (2352, 'Property Taxes (Monthly)',     354.67,  8),
    (2352, 'Insurance HOI',                   250,  9),
    (2352, 'CapEx Reserve',                   350, 10),
    (2352, 'MISC',                              0, 11),
    (2352, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2352
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2356  market_id=108  bedrooms=4
-- property_size=2451 -> opex_by_size.sqft=2750  purchase_price=995000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2356;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2356, 'Internet',                        150,  0),
    (2356, 'Utilities',                       625,  1),
    (2356, 'Pest Control',                     75,  2),
    (2356, 'Pool/Hot Tub Maintenance',        125,  3),
    (2356, 'Outdoor/Landscaping',             150,  4),
    (2356, 'Software',                          0,  5),
    (2356, 'Household Supplies',              205,  6),
    (2356, 'Cleaning',                     1237.5,  7),
    (2356, 'Property Taxes (Monthly)',     464.33,  8),
    (2356, 'Insurance HOI',                   300,  9),
    (2356, 'CapEx Reserve',                   400, 10),
    (2356, 'MISC',                              0, 11),
    (2356, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2356
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2363  market_id=108  bedrooms=4
-- property_size=3048 -> opex_by_size.sqft=3500  purchase_price=880000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2363;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2363, 'Internet',                        150,  0),
    (2363, 'Utilities',                       700,  1),
    (2363, 'Pest Control',                     75,  2),
    (2363, 'Pool/Hot Tub Maintenance',        125,  3),
    (2363, 'Outdoor/Landscaping',             150,  4),
    (2363, 'Software',                          0,  5),
    (2363, 'Household Supplies',              205,  6),
    (2363, 'Cleaning',                     1237.5,  7),
    (2363, 'Property Taxes (Monthly)',     410.67,  8),
    (2363, 'Insurance HOI',                   300,  9),
    (2363, 'CapEx Reserve',                   400, 10),
    (2363, 'MISC',                              0, 11),
    (2363, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2363
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2370  market_id=108  bedrooms=3
-- property_size=2274 -> opex_by_size.sqft=2750  purchase_price=825000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2370;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2370, 'Internet',                        150,  0),
    (2370, 'Utilities',                       625,  1),
    (2370, 'Pest Control',                     75,  2),
    (2370, 'Pool/Hot Tub Maintenance',        125,  3),
    (2370, 'Outdoor/Landscaping',             150,  4),
    (2370, 'Software',                          0,  5),
    (2370, 'Household Supplies',              175,  6),
    (2370, 'Cleaning',                       1050,  7),
    (2370, 'Property Taxes (Monthly)',     385.00,  8),
    (2370, 'Insurance HOI',                   250,  9),
    (2370, 'CapEx Reserve',                   350, 10),
    (2370, 'MISC',                              0, 11),
    (2370, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2370
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2374  market_id=108  bedrooms=3
-- property_size=2487 -> opex_by_size.sqft=2750  purchase_price=825000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2374;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2374, 'Internet',                        150,  0),
    (2374, 'Utilities',                       625,  1),
    (2374, 'Pest Control',                     75,  2),
    (2374, 'Pool/Hot Tub Maintenance',        125,  3),
    (2374, 'Outdoor/Landscaping',             150,  4),
    (2374, 'Software',                          0,  5),
    (2374, 'Household Supplies',              175,  6),
    (2374, 'Cleaning',                       1050,  7),
    (2374, 'Property Taxes (Monthly)',     385.00,  8),
    (2374, 'Insurance HOI',                   250,  9),
    (2374, 'CapEx Reserve',                   350, 10),
    (2374, 'MISC',                              0, 11),
    (2374, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2374
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2379  market_id=108  bedrooms=3
-- property_size=1672 -> opex_by_size.sqft=2000  purchase_price=610000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2379;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2379, 'Internet',                        100,  0),
    (2379, 'Utilities',                       525,  1),
    (2379, 'Pest Control',                     60,  2),
    (2379, 'Pool/Hot Tub Maintenance',        125,  3),
    (2379, 'Outdoor/Landscaping',             150,  4),
    (2379, 'Software',                          0,  5),
    (2379, 'Household Supplies',              175,  6),
    (2379, 'Cleaning',                       1050,  7),
    (2379, 'Property Taxes (Monthly)',     284.67,  8),
    (2379, 'Insurance HOI',                   250,  9),
    (2379, 'CapEx Reserve',                   350, 10),
    (2379, 'MISC',                              0, 11),
    (2379, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2379
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2383  market_id=108  bedrooms=4
-- property_size=1731 -> opex_by_size.sqft=2000  purchase_price=720000.00
-- 13 of 13 catalog rows resolved

-- BEGIN;

-- DELETE FROM iron_bank.uw_operating_expenses
-- WHERE underwriting_id = 2383;

-- INSERT INTO iron_bank.uw_operating_expenses
--     (underwriting_id, expense_name, monthly_amount, sort_order)
-- VALUES
--     (2383, 'Internet',                        100,  0),
--     (2383, 'Utilities',                       525,  1),
--     (2383, 'Pest Control',                     60,  2),
--     (2383, 'Pool/Hot Tub Maintenance',        125,  3),
--     (2383, 'Outdoor/Landscaping',             150,  4),
--     (2383, 'Software',                          0,  5),
--     (2383, 'Household Supplies',              205,  6),
--     (2383, 'Cleaning',                     1237.5,  7),
--     (2383, 'Property Taxes (Monthly)',     336.00,  8),
--     (2383, 'Insurance HOI',                   300,  9),
--     (2383, 'CapEx Reserve',                   400, 10),
--     (2383, 'MISC',                              0, 11),
--     (2383, 'HOA Fees',                          0, 12);

-- SELECT id, expense_name, monthly_amount, sort_order
-- FROM iron_bank.uw_operating_expenses
-- WHERE underwriting_id = 2383
-- ORDER BY sort_order;

-- -- Check the SELECT above before committing.
-- COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2387  market_id=108  bedrooms=3
-- property_size=1296 -> opex_by_size.sqft=1500  purchase_price=699900.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2387;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2387, 'Internet',                        100,  0),
    (2387, 'Utilities',                       425,  1),
    (2387, 'Pest Control',                     60,  2),
    (2387, 'Pool/Hot Tub Maintenance',        125,  3),
    (2387, 'Outdoor/Landscaping',             150,  4),
    (2387, 'Software',                          0,  5),
    (2387, 'Household Supplies',              175,  6),
    (2387, 'Cleaning',                       1050,  7),
    (2387, 'Property Taxes (Monthly)',     326.62,  8),
    (2387, 'Insurance HOI',                   250,  9),
    (2387, 'CapEx Reserve',                   350, 10),
    (2387, 'MISC',                              0, 11),
    (2387, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2387
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2389  market_id=108  bedrooms=3
-- property_size=1872 -> opex_by_size.sqft=2000  purchase_price=744900.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2389;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2389, 'Internet',                        100,  0),
    (2389, 'Utilities',                       525,  1),
    (2389, 'Pest Control',                     60,  2),
    (2389, 'Pool/Hot Tub Maintenance',        125,  3),
    (2389, 'Outdoor/Landscaping',             150,  4),
    (2389, 'Software',                          0,  5),
    (2389, 'Household Supplies',              175,  6),
    (2389, 'Cleaning',                       1050,  7),
    (2389, 'Property Taxes (Monthly)',     347.62,  8),
    (2389, 'Insurance HOI',                   250,  9),
    (2389, 'CapEx Reserve',                   350, 10),
    (2389, 'MISC',                              0, 11),
    (2389, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2389
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2391  market_id=108  bedrooms=3
-- property_size=1456 -> opex_by_size.sqft=1500  purchase_price=589000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2391;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2391, 'Internet',                        100,  0),
    (2391, 'Utilities',                       425,  1),
    (2391, 'Pest Control',                     60,  2),
    (2391, 'Pool/Hot Tub Maintenance',        125,  3),
    (2391, 'Outdoor/Landscaping',             150,  4),
    (2391, 'Software',                          0,  5),
    (2391, 'Household Supplies',              175,  6),
    (2391, 'Cleaning',                       1050,  7),
    (2391, 'Property Taxes (Monthly)',     274.87,  8),
    (2391, 'Insurance HOI',                   250,  9),
    (2391, 'CapEx Reserve',                   350, 10),
    (2391, 'MISC',                              0, 11),
    (2391, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2391
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2395  market_id=108  bedrooms=3
-- property_size=2206 -> opex_by_size.sqft=2750  purchase_price=799000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2395;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2395, 'Internet',                        150,  0),
    (2395, 'Utilities',                       625,  1),
    (2395, 'Pest Control',                     75,  2),
    (2395, 'Pool/Hot Tub Maintenance',        125,  3),
    (2395, 'Outdoor/Landscaping',             150,  4),
    (2395, 'Software',                          0,  5),
    (2395, 'Household Supplies',              175,  6),
    (2395, 'Cleaning',                       1050,  7),
    (2395, 'Property Taxes (Monthly)',     372.87,  8),
    (2395, 'Insurance HOI',                   250,  9),
    (2395, 'CapEx Reserve',                   350, 10),
    (2395, 'MISC',                              0, 11),
    (2395, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2395
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2398  market_id=108  bedrooms=4
-- property_size=3376 -> opex_by_size.sqft=3500  purchase_price=520000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2398;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2398, 'Internet',                        150,  0),
    (2398, 'Utilities',                       700,  1),
    (2398, 'Pest Control',                     75,  2),
    (2398, 'Pool/Hot Tub Maintenance',        125,  3),
    (2398, 'Outdoor/Landscaping',             150,  4),
    (2398, 'Software',                          0,  5),
    (2398, 'Household Supplies',              205,  6),
    (2398, 'Cleaning',                     1237.5,  7),
    (2398, 'Property Taxes (Monthly)',     242.67,  8),
    (2398, 'Insurance HOI',                   300,  9),
    (2398, 'CapEx Reserve',                   400, 10),
    (2398, 'MISC',                              0, 11),
    (2398, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2398
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2402  market_id=108  bedrooms=3
-- property_size=2226 -> opex_by_size.sqft=2750  purchase_price=718500.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2402;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2402, 'Internet',                        150,  0),
    (2402, 'Utilities',                       625,  1),
    (2402, 'Pest Control',                     75,  2),
    (2402, 'Pool/Hot Tub Maintenance',        125,  3),
    (2402, 'Outdoor/Landscaping',             150,  4),
    (2402, 'Software',                          0,  5),
    (2402, 'Household Supplies',              175,  6),
    (2402, 'Cleaning',                       1050,  7),
    (2402, 'Property Taxes (Monthly)',     335.30,  8),
    (2402, 'Insurance HOI',                   250,  9),
    (2402, 'CapEx Reserve',                   350, 10),
    (2402, 'MISC',                              0, 11),
    (2402, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2402
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2405  market_id=108  bedrooms=3
-- property_size=2722 -> opex_by_size.sqft=2750  purchase_price=599000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2405;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2405, 'Internet',                        150,  0),
    (2405, 'Utilities',                       625,  1),
    (2405, 'Pest Control',                     75,  2),
    (2405, 'Pool/Hot Tub Maintenance',        125,  3),
    (2405, 'Outdoor/Landscaping',             150,  4),
    (2405, 'Software',                          0,  5),
    (2405, 'Household Supplies',              175,  6),
    (2405, 'Cleaning',                       1050,  7),
    (2405, 'Property Taxes (Monthly)',     279.53,  8),
    (2405, 'Insurance HOI',                   250,  9),
    (2405, 'CapEx Reserve',                   350, 10),
    (2405, 'MISC',                              0, 11),
    (2405, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2405
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2409  market_id=108  bedrooms=3
-- property_size=1787 -> opex_by_size.sqft=2000  purchase_price=774900.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2409;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2409, 'Internet',                        100,  0),
    (2409, 'Utilities',                       525,  1),
    (2409, 'Pest Control',                     60,  2),
    (2409, 'Pool/Hot Tub Maintenance',        125,  3),
    (2409, 'Outdoor/Landscaping',             150,  4),
    (2409, 'Software',                          0,  5),
    (2409, 'Household Supplies',              175,  6),
    (2409, 'Cleaning',                       1050,  7),
    (2409, 'Property Taxes (Monthly)',     361.62,  8),
    (2409, 'Insurance HOI',                   250,  9),
    (2409, 'CapEx Reserve',                   350, 10),
    (2409, 'MISC',                              0, 11),
    (2409, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2409
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2413  market_id=108  bedrooms=3
-- property_size=1680 -> opex_by_size.sqft=2000  purchase_price=700000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2413;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2413, 'Internet',                        100,  0),
    (2413, 'Utilities',                       525,  1),
    (2413, 'Pest Control',                     60,  2),
    (2413, 'Pool/Hot Tub Maintenance',        125,  3),
    (2413, 'Outdoor/Landscaping',             150,  4),
    (2413, 'Software',                          0,  5),
    (2413, 'Household Supplies',              175,  6),
    (2413, 'Cleaning',                       1050,  7),
    (2413, 'Property Taxes (Monthly)',     326.67,  8),
    (2413, 'Insurance HOI',                   250,  9),
    (2413, 'CapEx Reserve',                   350, 10),
    (2413, 'MISC',                              0, 11),
    (2413, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2413
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2416  market_id=108  bedrooms=3
-- property_size=2223 -> opex_by_size.sqft=2750  purchase_price=749900.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2416;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2416, 'Internet',                        150,  0),
    (2416, 'Utilities',                       625,  1),
    (2416, 'Pest Control',                     75,  2),
    (2416, 'Pool/Hot Tub Maintenance',        125,  3),
    (2416, 'Outdoor/Landscaping',             150,  4),
    (2416, 'Software',                          0,  5),
    (2416, 'Household Supplies',              175,  6),
    (2416, 'Cleaning',                       1050,  7),
    (2416, 'Property Taxes (Monthly)',     349.95,  8),
    (2416, 'Insurance HOI',                   250,  9),
    (2416, 'CapEx Reserve',                   350, 10),
    (2416, 'MISC',                              0, 11),
    (2416, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2416
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2419  market_id=108  bedrooms=3
-- property_size=1231 -> opex_by_size.sqft=1500  purchase_price=639500.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2419;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2419, 'Internet',                        100,  0),
    (2419, 'Utilities',                       425,  1),
    (2419, 'Pest Control',                     60,  2),
    (2419, 'Pool/Hot Tub Maintenance',        125,  3),
    (2419, 'Outdoor/Landscaping',             150,  4),
    (2419, 'Software',                          0,  5),
    (2419, 'Household Supplies',              175,  6),
    (2419, 'Cleaning',                       1050,  7),
    (2419, 'Property Taxes (Monthly)',     298.43,  8),
    (2419, 'Insurance HOI',                   250,  9),
    (2419, 'CapEx Reserve',                   350, 10),
    (2419, 'MISC',                              0, 11),
    (2419, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2419
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2423  market_id=108  bedrooms=4
-- property_size=3873 -> opex_by_size.sqft=4500  purchase_price=995000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2423;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2423, 'Internet',                        150,  0),
    (2423, 'Utilities',                       825,  1),
    (2423, 'Pest Control',                     75,  2),
    (2423, 'Pool/Hot Tub Maintenance',        125,  3),
    (2423, 'Outdoor/Landscaping',             150,  4),
    (2423, 'Software',                          0,  5),
    (2423, 'Household Supplies',              205,  6),
    (2423, 'Cleaning',                     1237.5,  7),
    (2423, 'Property Taxes (Monthly)',     464.33,  8),
    (2423, 'Insurance HOI',                   300,  9),
    (2423, 'CapEx Reserve',                   400, 10),
    (2423, 'MISC',                              0, 11),
    (2423, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2423
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2427  market_id=108  bedrooms=3
-- property_size=2917 -> opex_by_size.sqft=3500  purchase_price=995000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2427;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2427, 'Internet',                        150,  0),
    (2427, 'Utilities',                       700,  1),
    (2427, 'Pest Control',                     75,  2),
    (2427, 'Pool/Hot Tub Maintenance',        125,  3),
    (2427, 'Outdoor/Landscaping',             150,  4),
    (2427, 'Software',                          0,  5),
    (2427, 'Household Supplies',              175,  6),
    (2427, 'Cleaning',                       1050,  7),
    (2427, 'Property Taxes (Monthly)',     464.33,  8),
    (2427, 'Insurance HOI',                   250,  9),
    (2427, 'CapEx Reserve',                   350, 10),
    (2427, 'MISC',                              0, 11),
    (2427, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2427
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2431  market_id=108  bedrooms=3
-- property_size=3912 -> opex_by_size.sqft=4500  purchase_price=850000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2431;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2431, 'Internet',                        150,  0),
    (2431, 'Utilities',                       825,  1),
    (2431, 'Pest Control',                     75,  2),
    (2431, 'Pool/Hot Tub Maintenance',        125,  3),
    (2431, 'Outdoor/Landscaping',             150,  4),
    (2431, 'Software',                          0,  5),
    (2431, 'Household Supplies',              175,  6),
    (2431, 'Cleaning',                       1050,  7),
    (2431, 'Property Taxes (Monthly)',     396.67,  8),
    (2431, 'Insurance HOI',                   250,  9),
    (2431, 'CapEx Reserve',                   350, 10),
    (2431, 'MISC',                              0, 11),
    (2431, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2431
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2435  market_id=108  bedrooms=3
-- property_size=3564 -> opex_by_size.sqft=4500  purchase_price=800000.00
-- 13 of 13 catalog rows resolved

-- BEGIN;

-- DELETE FROM iron_bank.uw_operating_expenses
-- WHERE underwriting_id = 2435;

-- INSERT INTO iron_bank.uw_operating_expenses
--     (underwriting_id, expense_name, monthly_amount, sort_order)
-- VALUES
--     (2435, 'Internet',                        150,  0),
--     (2435, 'Utilities',                       825,  1),
--     (2435, 'Pest Control',                     75,  2),
--     (2435, 'Pool/Hot Tub Maintenance',        125,  3),
--     (2435, 'Outdoor/Landscaping',             150,  4),
--     (2435, 'Software',                          0,  5),
--     (2435, 'Household Supplies',              175,  6),
--     (2435, 'Cleaning',                       1050,  7),
--     (2435, 'Property Taxes (Monthly)',     373.33,  8),
--     (2435, 'Insurance HOI',                   250,  9),
--     (2435, 'CapEx Reserve',                   350, 10),
--     (2435, 'MISC',                              0, 11),
--     (2435, 'HOA Fees',                          0, 12);

-- SELECT id, expense_name, monthly_amount, sort_order
-- FROM iron_bank.uw_operating_expenses
-- WHERE underwriting_id = 2435
-- ORDER BY sort_order;

-- -- Check the SELECT above before committing.
-- COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2441  market_id=108  bedrooms=3
-- property_size=2624 -> opex_by_size.sqft=2750  purchase_price=650000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2441;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2441, 'Internet',                        150,  0),
    (2441, 'Utilities',                       625,  1),
    (2441, 'Pest Control',                     75,  2),
    (2441, 'Pool/Hot Tub Maintenance',        125,  3),
    (2441, 'Outdoor/Landscaping',             150,  4),
    (2441, 'Software',                          0,  5),
    (2441, 'Household Supplies',              175,  6),
    (2441, 'Cleaning',                       1050,  7),
    (2441, 'Property Taxes (Monthly)',     303.33,  8),
    (2441, 'Insurance HOI',                   250,  9),
    (2441, 'CapEx Reserve',                   350, 10),
    (2441, 'MISC',                              0, 11),
    (2441, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2441
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2444  market_id=108  bedrooms=5
-- property_size=3704 -> opex_by_size.sqft=4500  purchase_price=979000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2444;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2444, 'Internet',                        150,  0),
    (2444, 'Utilities',                       825,  1),
    (2444, 'Pest Control',                     75,  2),
    (2444, 'Pool/Hot Tub Maintenance',        125,  3),
    (2444, 'Outdoor/Landscaping',             175,  4),
    (2444, 'Software',                          0,  5),
    (2444, 'Household Supplies',              250,  6),
    (2444, 'Cleaning',                    1443.75,  7),
    (2444, 'Property Taxes (Monthly)',     456.87,  8),
    (2444, 'Insurance HOI',                   350,  9),
    (2444, 'CapEx Reserve',                   500, 10),
    (2444, 'MISC',                              0, 11),
    (2444, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2444
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2447  market_id=108  bedrooms=3
-- property_size=2025 -> opex_by_size.sqft=2750  purchase_price=699000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2447;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2447, 'Internet',                        150,  0),
    (2447, 'Utilities',                       625,  1),
    (2447, 'Pest Control',                     75,  2),
    (2447, 'Pool/Hot Tub Maintenance',        125,  3),
    (2447, 'Outdoor/Landscaping',             150,  4),
    (2447, 'Software',                          0,  5),
    (2447, 'Household Supplies',              175,  6),
    (2447, 'Cleaning',                       1050,  7),
    (2447, 'Property Taxes (Monthly)',     326.20,  8),
    (2447, 'Insurance HOI',                   250,  9),
    (2447, 'CapEx Reserve',                   350, 10),
    (2447, 'MISC',                              0, 11),
    (2447, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2447
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2448  market_id=108  bedrooms=4
-- property_size=2034 -> opex_by_size.sqft=2750  purchase_price=515000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2448;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2448, 'Internet',                        150,  0),
    (2448, 'Utilities',                       625,  1),
    (2448, 'Pest Control',                     75,  2),
    (2448, 'Pool/Hot Tub Maintenance',        125,  3),
    (2448, 'Outdoor/Landscaping',             150,  4),
    (2448, 'Software',                          0,  5),
    (2448, 'Household Supplies',              205,  6),
    (2448, 'Cleaning',                     1237.5,  7),
    (2448, 'Property Taxes (Monthly)',     240.33,  8),
    (2448, 'Insurance HOI',                   300,  9),
    (2448, 'CapEx Reserve',                   400, 10),
    (2448, 'MISC',                              0, 11),
    (2448, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2448
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2451  market_id=108  bedrooms=3
-- property_size=1984 -> opex_by_size.sqft=2000  purchase_price=775000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2451;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2451, 'Internet',                        100,  0),
    (2451, 'Utilities',                       525,  1),
    (2451, 'Pest Control',                     60,  2),
    (2451, 'Pool/Hot Tub Maintenance',        125,  3),
    (2451, 'Outdoor/Landscaping',             150,  4),
    (2451, 'Software',                          0,  5),
    (2451, 'Household Supplies',              175,  6),
    (2451, 'Cleaning',                       1050,  7),
    (2451, 'Property Taxes (Monthly)',     361.67,  8),
    (2451, 'Insurance HOI',                   250,  9),
    (2451, 'CapEx Reserve',                   350, 10),
    (2451, 'MISC',                              0, 11),
    (2451, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2451
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2454  market_id=108  bedrooms=4
-- property_size=2081 -> opex_by_size.sqft=2750  purchase_price=690000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2454;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2454, 'Internet',                        150,  0),
    (2454, 'Utilities',                       625,  1),
    (2454, 'Pest Control',                     75,  2),
    (2454, 'Pool/Hot Tub Maintenance',        125,  3),
    (2454, 'Outdoor/Landscaping',             150,  4),
    (2454, 'Software',                          0,  5),
    (2454, 'Household Supplies',              205,  6),
    (2454, 'Cleaning',                     1237.5,  7),
    (2454, 'Property Taxes (Monthly)',     322.00,  8),
    (2454, 'Insurance HOI',                   300,  9),
    (2454, 'CapEx Reserve',                   400, 10),
    (2454, 'MISC',                              0, 11),
    (2454, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2454
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2456  market_id=108  bedrooms=4
-- property_size=2733 -> opex_by_size.sqft=2750  purchase_price=650000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2456;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2456, 'Internet',                        150,  0),
    (2456, 'Utilities',                       625,  1),
    (2456, 'Pest Control',                     75,  2),
    (2456, 'Pool/Hot Tub Maintenance',        125,  3),
    (2456, 'Outdoor/Landscaping',             150,  4),
    (2456, 'Software',                          0,  5),
    (2456, 'Household Supplies',              205,  6),
    (2456, 'Cleaning',                     1237.5,  7),
    (2456, 'Property Taxes (Monthly)',     303.33,  8),
    (2456, 'Insurance HOI',                   300,  9),
    (2456, 'CapEx Reserve',                   400, 10),
    (2456, 'MISC',                              0, 11),
    (2456, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2456
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2458  market_id=108  bedrooms=3
-- property_size=1532 -> opex_by_size.sqft=2000  purchase_price=475000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2458;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2458, 'Internet',                        100,  0),
    (2458, 'Utilities',                       525,  1),
    (2458, 'Pest Control',                     60,  2),
    (2458, 'Pool/Hot Tub Maintenance',        125,  3),
    (2458, 'Outdoor/Landscaping',             150,  4),
    (2458, 'Software',                          0,  5),
    (2458, 'Household Supplies',              175,  6),
    (2458, 'Cleaning',                       1050,  7),
    (2458, 'Property Taxes (Monthly)',     221.67,  8),
    (2458, 'Insurance HOI',                   250,  9),
    (2458, 'CapEx Reserve',                   350, 10),
    (2458, 'MISC',                              0, 11),
    (2458, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2458
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2460  market_id=108  bedrooms=3
-- property_size=1560 -> opex_by_size.sqft=2000  purchase_price=563000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2460;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2460, 'Internet',                        100,  0),
    (2460, 'Utilities',                       525,  1),
    (2460, 'Pest Control',                     60,  2),
    (2460, 'Pool/Hot Tub Maintenance',        125,  3),
    (2460, 'Outdoor/Landscaping',             150,  4),
    (2460, 'Software',                          0,  5),
    (2460, 'Household Supplies',              175,  6),
    (2460, 'Cleaning',                       1050,  7),
    (2460, 'Property Taxes (Monthly)',     262.73,  8),
    (2460, 'Insurance HOI',                   250,  9),
    (2460, 'CapEx Reserve',                   350, 10),
    (2460, 'MISC',                              0, 11),
    (2460, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2460
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2462  market_id=108  bedrooms=4
-- property_size=3230 -> opex_by_size.sqft=3500  purchase_price=947000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2462;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2462, 'Internet',                        150,  0),
    (2462, 'Utilities',                       700,  1),
    (2462, 'Pest Control',                     75,  2),
    (2462, 'Pool/Hot Tub Maintenance',        125,  3),
    (2462, 'Outdoor/Landscaping',             150,  4),
    (2462, 'Software',                          0,  5),
    (2462, 'Household Supplies',              205,  6),
    (2462, 'Cleaning',                     1237.5,  7),
    (2462, 'Property Taxes (Monthly)',     441.93,  8),
    (2462, 'Insurance HOI',                   300,  9),
    (2462, 'CapEx Reserve',                   400, 10),
    (2462, 'MISC',                              0, 11),
    (2462, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2462
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2463  market_id=108  bedrooms=6
-- property_size=6529 -> opex_by_size.sqft=4500  purchase_price=899000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2463;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2463, 'Internet',                        150,  0),
    (2463, 'Utilities',                       825,  1),
    (2463, 'Pest Control',                     75,  2),
    (2463, 'Pool/Hot Tub Maintenance',        125,  3),
    (2463, 'Outdoor/Landscaping',             175,  4),
    (2463, 'Software',                          0,  5),
    (2463, 'Household Supplies',              300,  6),
    (2463, 'Cleaning',                    1662.50,  7),
    (2463, 'Property Taxes (Monthly)',     419.53,  8),
    (2463, 'Insurance HOI',                   400,  9),
    (2463, 'CapEx Reserve',                   600, 10),
    (2463, 'MISC',                              0, 11),
    (2463, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2463
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2465  market_id=108  bedrooms=3
-- property_size=2665 -> opex_by_size.sqft=2750  purchase_price=695000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2465;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2465, 'Internet',                        150,  0),
    (2465, 'Utilities',                       625,  1),
    (2465, 'Pest Control',                     75,  2),
    (2465, 'Pool/Hot Tub Maintenance',        125,  3),
    (2465, 'Outdoor/Landscaping',             150,  4),
    (2465, 'Software',                          0,  5),
    (2465, 'Household Supplies',              175,  6),
    (2465, 'Cleaning',                       1050,  7),
    (2465, 'Property Taxes (Monthly)',     324.33,  8),
    (2465, 'Insurance HOI',                   250,  9),
    (2465, 'CapEx Reserve',                   350, 10),
    (2465, 'MISC',                              0, 11),
    (2465, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2465
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2467  market_id=108  bedrooms=5
-- property_size=2816 -> opex_by_size.sqft=3500  purchase_price=575000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2467;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2467, 'Internet',                        150,  0),
    (2467, 'Utilities',                       700,  1),
    (2467, 'Pest Control',                     75,  2),
    (2467, 'Pool/Hot Tub Maintenance',        125,  3),
    (2467, 'Outdoor/Landscaping',             175,  4),
    (2467, 'Software',                          0,  5),
    (2467, 'Household Supplies',              250,  6),
    (2467, 'Cleaning',                    1443.75,  7),
    (2467, 'Property Taxes (Monthly)',     268.33,  8),
    (2467, 'Insurance HOI',                   350,  9),
    (2467, 'CapEx Reserve',                   500, 10),
    (2467, 'MISC',                              0, 11),
    (2467, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2467
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2469  market_id=108  bedrooms=4
-- property_size=2464 -> opex_by_size.sqft=2750  purchase_price=725000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2469;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2469, 'Internet',                        150,  0),
    (2469, 'Utilities',                       625,  1),
    (2469, 'Pest Control',                     75,  2),
    (2469, 'Pool/Hot Tub Maintenance',        125,  3),
    (2469, 'Outdoor/Landscaping',             150,  4),
    (2469, 'Software',                          0,  5),
    (2469, 'Household Supplies',              205,  6),
    (2469, 'Cleaning',                     1237.5,  7),
    (2469, 'Property Taxes (Monthly)',     338.33,  8),
    (2469, 'Insurance HOI',                   300,  9),
    (2469, 'CapEx Reserve',                   400, 10),
    (2469, 'MISC',                              0, 11),
    (2469, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2469
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2471  market_id=108  bedrooms=3
-- property_size=2145 -> opex_by_size.sqft=2750  purchase_price=818500.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2471;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2471, 'Internet',                        150,  0),
    (2471, 'Utilities',                       625,  1),
    (2471, 'Pest Control',                     75,  2),
    (2471, 'Pool/Hot Tub Maintenance',        125,  3),
    (2471, 'Outdoor/Landscaping',             150,  4),
    (2471, 'Software',                          0,  5),
    (2471, 'Household Supplies',              175,  6),
    (2471, 'Cleaning',                       1050,  7),
    (2471, 'Property Taxes (Monthly)',     381.97,  8),
    (2471, 'Insurance HOI',                   250,  9),
    (2471, 'CapEx Reserve',                   350, 10),
    (2471, 'MISC',                              0, 11),
    (2471, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2471
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2473  market_id=108  bedrooms=3
-- property_size=3210 -> opex_by_size.sqft=3500  purchase_price=599900.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2473;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2473, 'Internet',                        150,  0),
    (2473, 'Utilities',                       700,  1),
    (2473, 'Pest Control',                     75,  2),
    (2473, 'Pool/Hot Tub Maintenance',        125,  3),
    (2473, 'Outdoor/Landscaping',             150,  4),
    (2473, 'Software',                          0,  5),
    (2473, 'Household Supplies',              175,  6),
    (2473, 'Cleaning',                       1050,  7),
    (2473, 'Property Taxes (Monthly)',     279.95,  8),
    (2473, 'Insurance HOI',                   250,  9),
    (2473, 'CapEx Reserve',                   350, 10),
    (2473, 'MISC',                              0, 11),
    (2473, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2473
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2475  market_id=108  bedrooms=3
-- property_size=2436 -> opex_by_size.sqft=2750  purchase_price=950000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2475;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2475, 'Internet',                        150,  0),
    (2475, 'Utilities',                       625,  1),
    (2475, 'Pest Control',                     75,  2),
    (2475, 'Pool/Hot Tub Maintenance',        125,  3),
    (2475, 'Outdoor/Landscaping',             150,  4),
    (2475, 'Software',                          0,  5),
    (2475, 'Household Supplies',              175,  6),
    (2475, 'Cleaning',                       1050,  7),
    (2475, 'Property Taxes (Monthly)',     443.33,  8),
    (2475, 'Insurance HOI',                   250,  9),
    (2475, 'CapEx Reserve',                   350, 10),
    (2475, 'MISC',                              0, 11),
    (2475, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2475
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2477  market_id=108  bedrooms=3
-- property_size=2150 -> opex_by_size.sqft=2750  purchase_price=645000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2477;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2477, 'Internet',                        150,  0),
    (2477, 'Utilities',                       625,  1),
    (2477, 'Pest Control',                     75,  2),
    (2477, 'Pool/Hot Tub Maintenance',        125,  3),
    (2477, 'Outdoor/Landscaping',             150,  4),
    (2477, 'Software',                          0,  5),
    (2477, 'Household Supplies',              175,  6),
    (2477, 'Cleaning',                       1050,  7),
    (2477, 'Property Taxes (Monthly)',     301.00,  8),
    (2477, 'Insurance HOI',                   250,  9),
    (2477, 'CapEx Reserve',                   350, 10),
    (2477, 'MISC',                              0, 11),
    (2477, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2477
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2478  market_id=108  bedrooms=4
-- property_size=3356 -> opex_by_size.sqft=3500  purchase_price=829000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2478;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2478, 'Internet',                        150,  0),
    (2478, 'Utilities',                       700,  1),
    (2478, 'Pest Control',                     75,  2),
    (2478, 'Pool/Hot Tub Maintenance',        125,  3),
    (2478, 'Outdoor/Landscaping',             150,  4),
    (2478, 'Software',                          0,  5),
    (2478, 'Household Supplies',              205,  6),
    (2478, 'Cleaning',                     1237.5,  7),
    (2478, 'Property Taxes (Monthly)',     386.87,  8),
    (2478, 'Insurance HOI',                   300,  9),
    (2478, 'CapEx Reserve',                   400, 10),
    (2478, 'MISC',                              0, 11),
    (2478, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2478
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2480  market_id=108  bedrooms=3
-- property_size=1536 -> opex_by_size.sqft=2000  purchase_price=439000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2480;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2480, 'Internet',                        100,  0),
    (2480, 'Utilities',                       525,  1),
    (2480, 'Pest Control',                     60,  2),
    (2480, 'Pool/Hot Tub Maintenance',        125,  3),
    (2480, 'Outdoor/Landscaping',             150,  4),
    (2480, 'Software',                          0,  5),
    (2480, 'Household Supplies',              175,  6),
    (2480, 'Cleaning',                       1050,  7),
    (2480, 'Property Taxes (Monthly)',     204.87,  8),
    (2480, 'Insurance HOI',                   250,  9),
    (2480, 'CapEx Reserve',                   350, 10),
    (2480, 'MISC',                              0, 11),
    (2480, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2480
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2482  market_id=108  bedrooms=4
-- property_size=1992 -> opex_by_size.sqft=2000  purchase_price=659900.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2482;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2482, 'Internet',                        100,  0),
    (2482, 'Utilities',                       525,  1),
    (2482, 'Pest Control',                     60,  2),
    (2482, 'Pool/Hot Tub Maintenance',        125,  3),
    (2482, 'Outdoor/Landscaping',             150,  4),
    (2482, 'Software',                          0,  5),
    (2482, 'Household Supplies',              205,  6),
    (2482, 'Cleaning',                     1237.5,  7),
    (2482, 'Property Taxes (Monthly)',     307.95,  8),
    (2482, 'Insurance HOI',                   300,  9),
    (2482, 'CapEx Reserve',                   400, 10),
    (2482, 'MISC',                              0, 11),
    (2482, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2482
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2484  market_id=108  bedrooms=3
-- property_size=2041 -> opex_by_size.sqft=2750  purchase_price=625000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2484;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2484, 'Internet',                        150,  0),
    (2484, 'Utilities',                       625,  1),
    (2484, 'Pest Control',                     75,  2),
    (2484, 'Pool/Hot Tub Maintenance',        125,  3),
    (2484, 'Outdoor/Landscaping',             150,  4),
    (2484, 'Software',                          0,  5),
    (2484, 'Household Supplies',              175,  6),
    (2484, 'Cleaning',                       1050,  7),
    (2484, 'Property Taxes (Monthly)',     291.67,  8),
    (2484, 'Insurance HOI',                   250,  9),
    (2484, 'CapEx Reserve',                   350, 10),
    (2484, 'MISC',                              0, 11),
    (2484, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2484
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2486  market_id=108  bedrooms=3
-- property_size=2028 -> opex_by_size.sqft=2750  purchase_price=640000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2486;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2486, 'Internet',                        150,  0),
    (2486, 'Utilities',                       625,  1),
    (2486, 'Pest Control',                     75,  2),
    (2486, 'Pool/Hot Tub Maintenance',        125,  3),
    (2486, 'Outdoor/Landscaping',             150,  4),
    (2486, 'Software',                          0,  5),
    (2486, 'Household Supplies',              175,  6),
    (2486, 'Cleaning',                       1050,  7),
    (2486, 'Property Taxes (Monthly)',     298.67,  8),
    (2486, 'Insurance HOI',                   250,  9),
    (2486, 'CapEx Reserve',                   350, 10),
    (2486, 'MISC',                              0, 11),
    (2486, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2486
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2488  market_id=108  bedrooms=3
-- property_size=2102 -> opex_by_size.sqft=2750  purchase_price=599000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2488;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2488, 'Internet',                        150,  0),
    (2488, 'Utilities',                       625,  1),
    (2488, 'Pest Control',                     75,  2),
    (2488, 'Pool/Hot Tub Maintenance',        125,  3),
    (2488, 'Outdoor/Landscaping',             150,  4),
    (2488, 'Software',                          0,  5),
    (2488, 'Household Supplies',              175,  6),
    (2488, 'Cleaning',                       1050,  7),
    (2488, 'Property Taxes (Monthly)',     279.53,  8),
    (2488, 'Insurance HOI',                   250,  9),
    (2488, 'CapEx Reserve',                   350, 10),
    (2488, 'MISC',                              0, 11),
    (2488, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2488
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2490  market_id=108  bedrooms=4
-- property_size=2720 -> opex_by_size.sqft=2750  purchase_price=495000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2490;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2490, 'Internet',                        150,  0),
    (2490, 'Utilities',                       625,  1),
    (2490, 'Pest Control',                     75,  2),
    (2490, 'Pool/Hot Tub Maintenance',        125,  3),
    (2490, 'Outdoor/Landscaping',             150,  4),
    (2490, 'Software',                          0,  5),
    (2490, 'Household Supplies',              205,  6),
    (2490, 'Cleaning',                     1237.5,  7),
    (2490, 'Property Taxes (Monthly)',     231.00,  8),
    (2490, 'Insurance HOI',                   300,  9),
    (2490, 'CapEx Reserve',                   400, 10),
    (2490, 'MISC',                              0, 11),
    (2490, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2490
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2491  market_id=108  bedrooms=3
-- property_size=1488 -> opex_by_size.sqft=1500  purchase_price=525000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2491;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2491, 'Internet',                        100,  0),
    (2491, 'Utilities',                       425,  1),
    (2491, 'Pest Control',                     60,  2),
    (2491, 'Pool/Hot Tub Maintenance',        125,  3),
    (2491, 'Outdoor/Landscaping',             150,  4),
    (2491, 'Software',                          0,  5),
    (2491, 'Household Supplies',              175,  6),
    (2491, 'Cleaning',                       1050,  7),
    (2491, 'Property Taxes (Monthly)',     245.00,  8),
    (2491, 'Insurance HOI',                   250,  9),
    (2491, 'CapEx Reserve',                   350, 10),
    (2491, 'MISC',                              0, 11),
    (2491, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2491
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2493  market_id=108  bedrooms=4
-- property_size=2470 -> opex_by_size.sqft=2750  purchase_price=800000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2493;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2493, 'Internet',                        150,  0),
    (2493, 'Utilities',                       625,  1),
    (2493, 'Pest Control',                     75,  2),
    (2493, 'Pool/Hot Tub Maintenance',        125,  3),
    (2493, 'Outdoor/Landscaping',             150,  4),
    (2493, 'Software',                          0,  5),
    (2493, 'Household Supplies',              205,  6),
    (2493, 'Cleaning',                     1237.5,  7),
    (2493, 'Property Taxes (Monthly)',     373.33,  8),
    (2493, 'Insurance HOI',                   300,  9),
    (2493, 'CapEx Reserve',                   400, 10),
    (2493, 'MISC',                              0, 11),
    (2493, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2493
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2495  market_id=108  bedrooms=3
-- property_size=1976 -> opex_by_size.sqft=2000  purchase_price=475000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2495;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2495, 'Internet',                        100,  0),
    (2495, 'Utilities',                       525,  1),
    (2495, 'Pest Control',                     60,  2),
    (2495, 'Pool/Hot Tub Maintenance',        125,  3),
    (2495, 'Outdoor/Landscaping',             150,  4),
    (2495, 'Software',                          0,  5),
    (2495, 'Household Supplies',              175,  6),
    (2495, 'Cleaning',                       1050,  7),
    (2495, 'Property Taxes (Monthly)',     221.67,  8),
    (2495, 'Insurance HOI',                   250,  9),
    (2495, 'CapEx Reserve',                   350, 10),
    (2495, 'MISC',                              0, 11),
    (2495, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2495
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2497  market_id=108  bedrooms=4
-- property_size=2475 -> opex_by_size.sqft=2750  purchase_price=700000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2497;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2497, 'Internet',                        150,  0),
    (2497, 'Utilities',                       625,  1),
    (2497, 'Pest Control',                     75,  2),
    (2497, 'Pool/Hot Tub Maintenance',        125,  3),
    (2497, 'Outdoor/Landscaping',             150,  4),
    (2497, 'Software',                          0,  5),
    (2497, 'Household Supplies',              205,  6),
    (2497, 'Cleaning',                     1237.5,  7),
    (2497, 'Property Taxes (Monthly)',     326.67,  8),
    (2497, 'Insurance HOI',                   300,  9),
    (2497, 'CapEx Reserve',                   400, 10),
    (2497, 'MISC',                              0, 11),
    (2497, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2497
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2499  market_id=108  bedrooms=5
-- property_size=2232 -> opex_by_size.sqft=2750  purchase_price=672000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2499;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2499, 'Internet',                        150,  0),
    (2499, 'Utilities',                       625,  1),
    (2499, 'Pest Control',                     75,  2),
    (2499, 'Pool/Hot Tub Maintenance',        125,  3),
    (2499, 'Outdoor/Landscaping',             175,  4),
    (2499, 'Software',                          0,  5),
    (2499, 'Household Supplies',              250,  6),
    (2499, 'Cleaning',                    1443.75,  7),
    (2499, 'Property Taxes (Monthly)',     313.60,  8),
    (2499, 'Insurance HOI',                   350,  9),
    (2499, 'CapEx Reserve',                   500, 10),
    (2499, 'MISC',                              0, 11),
    (2499, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2499
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2501  market_id=108  bedrooms=3
-- property_size=2824 -> opex_by_size.sqft=3500  purchase_price=990000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2501;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2501, 'Internet',                        150,  0),
    (2501, 'Utilities',                       700,  1),
    (2501, 'Pest Control',                     75,  2),
    (2501, 'Pool/Hot Tub Maintenance',        125,  3),
    (2501, 'Outdoor/Landscaping',             150,  4),
    (2501, 'Software',                          0,  5),
    (2501, 'Household Supplies',              175,  6),
    (2501, 'Cleaning',                       1050,  7),
    (2501, 'Property Taxes (Monthly)',     462.00,  8),
    (2501, 'Insurance HOI',                   250,  9),
    (2501, 'CapEx Reserve',                   350, 10),
    (2501, 'MISC',                              0, 11),
    (2501, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2501
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2503  market_id=108  bedrooms=3
-- property_size=2336 -> opex_by_size.sqft=2750  purchase_price=770000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2503;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2503, 'Internet',                        150,  0),
    (2503, 'Utilities',                       625,  1),
    (2503, 'Pest Control',                     75,  2),
    (2503, 'Pool/Hot Tub Maintenance',        125,  3),
    (2503, 'Outdoor/Landscaping',             150,  4),
    (2503, 'Software',                          0,  5),
    (2503, 'Household Supplies',              175,  6),
    (2503, 'Cleaning',                       1050,  7),
    (2503, 'Property Taxes (Monthly)',     359.33,  8),
    (2503, 'Insurance HOI',                   250,  9),
    (2503, 'CapEx Reserve',                   350, 10),
    (2503, 'MISC',                              0, 11),
    (2503, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2503
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2505  market_id=108  bedrooms=3
-- property_size=3150 -> opex_by_size.sqft=3500  purchase_price=895000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2505;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2505, 'Internet',                        150,  0),
    (2505, 'Utilities',                       700,  1),
    (2505, 'Pest Control',                     75,  2),
    (2505, 'Pool/Hot Tub Maintenance',        125,  3),
    (2505, 'Outdoor/Landscaping',             150,  4),
    (2505, 'Software',                          0,  5),
    (2505, 'Household Supplies',              175,  6),
    (2505, 'Cleaning',                       1050,  7),
    (2505, 'Property Taxes (Monthly)',     417.67,  8),
    (2505, 'Insurance HOI',                   250,  9),
    (2505, 'CapEx Reserve',                   350, 10),
    (2505, 'MISC',                              0, 11),
    (2505, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2505
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2506  market_id=108  bedrooms=3
-- property_size=1690 -> opex_by_size.sqft=2000  purchase_price=745000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2506;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2506, 'Internet',                        100,  0),
    (2506, 'Utilities',                       525,  1),
    (2506, 'Pest Control',                     60,  2),
    (2506, 'Pool/Hot Tub Maintenance',        125,  3),
    (2506, 'Outdoor/Landscaping',             150,  4),
    (2506, 'Software',                          0,  5),
    (2506, 'Household Supplies',              175,  6),
    (2506, 'Cleaning',                       1050,  7),
    (2506, 'Property Taxes (Monthly)',     347.67,  8),
    (2506, 'Insurance HOI',                   250,  9),
    (2506, 'CapEx Reserve',                   350, 10),
    (2506, 'MISC',                              0, 11),
    (2506, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2506
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2508  market_id=108  bedrooms=3
-- property_size=2869 -> opex_by_size.sqft=3500  purchase_price=1000000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2508;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2508, 'Internet',                        150,  0),
    (2508, 'Utilities',                       700,  1),
    (2508, 'Pest Control',                     75,  2),
    (2508, 'Pool/Hot Tub Maintenance',        125,  3),
    (2508, 'Outdoor/Landscaping',             150,  4),
    (2508, 'Software',                          0,  5),
    (2508, 'Household Supplies',              175,  6),
    (2508, 'Cleaning',                       1050,  7),
    (2508, 'Property Taxes (Monthly)',     466.67,  8),
    (2508, 'Insurance HOI',                   250,  9),
    (2508, 'CapEx Reserve',                   350, 10),
    (2508, 'MISC',                              0, 11),
    (2508, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2508
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2509  market_id=108  bedrooms=3
-- property_size=1344 -> opex_by_size.sqft=1500  purchase_price=515000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2509;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2509, 'Internet',                        100,  0),
    (2509, 'Utilities',                       425,  1),
    (2509, 'Pest Control',                     60,  2),
    (2509, 'Pool/Hot Tub Maintenance',        125,  3),
    (2509, 'Outdoor/Landscaping',             150,  4),
    (2509, 'Software',                          0,  5),
    (2509, 'Household Supplies',              175,  6),
    (2509, 'Cleaning',                       1050,  7),
    (2509, 'Property Taxes (Monthly)',     240.33,  8),
    (2509, 'Insurance HOI',                   250,  9),
    (2509, 'CapEx Reserve',                   350, 10),
    (2509, 'MISC',                              0, 11),
    (2509, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2509
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2510  market_id=108  bedrooms=3
-- property_size=2004 -> opex_by_size.sqft=2750  purchase_price=800000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2510;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2510, 'Internet',                        150,  0),
    (2510, 'Utilities',                       625,  1),
    (2510, 'Pest Control',                     75,  2),
    (2510, 'Pool/Hot Tub Maintenance',        125,  3),
    (2510, 'Outdoor/Landscaping',             150,  4),
    (2510, 'Software',                          0,  5),
    (2510, 'Household Supplies',              175,  6),
    (2510, 'Cleaning',                       1050,  7),
    (2510, 'Property Taxes (Monthly)',     373.33,  8),
    (2510, 'Insurance HOI',                   250,  9),
    (2510, 'CapEx Reserve',                   350, 10),
    (2510, 'MISC',                              0, 11),
    (2510, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2510
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2511  market_id=108  bedrooms=3
-- property_size=1612 -> opex_by_size.sqft=2000  purchase_price=665000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2511;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2511, 'Internet',                        100,  0),
    (2511, 'Utilities',                       525,  1),
    (2511, 'Pest Control',                     60,  2),
    (2511, 'Pool/Hot Tub Maintenance',        125,  3),
    (2511, 'Outdoor/Landscaping',             150,  4),
    (2511, 'Software',                          0,  5),
    (2511, 'Household Supplies',              175,  6),
    (2511, 'Cleaning',                       1050,  7),
    (2511, 'Property Taxes (Monthly)',     310.33,  8),
    (2511, 'Insurance HOI',                   250,  9),
    (2511, 'CapEx Reserve',                   350, 10),
    (2511, 'MISC',                              0, 11),
    (2511, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2511
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2513  market_id=108  bedrooms=3
-- property_size=1818 -> opex_by_size.sqft=2000  purchase_price=538000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2513;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2513, 'Internet',                        100,  0),
    (2513, 'Utilities',                       525,  1),
    (2513, 'Pest Control',                     60,  2),
    (2513, 'Pool/Hot Tub Maintenance',        125,  3),
    (2513, 'Outdoor/Landscaping',             150,  4),
    (2513, 'Software',                          0,  5),
    (2513, 'Household Supplies',              175,  6),
    (2513, 'Cleaning',                       1050,  7),
    (2513, 'Property Taxes (Monthly)',     251.07,  8),
    (2513, 'Insurance HOI',                   250,  9),
    (2513, 'CapEx Reserve',                   350, 10),
    (2513, 'MISC',                              0, 11),
    (2513, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2513
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2514  market_id=108  bedrooms=3
-- property_size=2762 -> opex_by_size.sqft=3500  purchase_price=525000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2514;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2514, 'Internet',                        150,  0),
    (2514, 'Utilities',                       700,  1),
    (2514, 'Pest Control',                     75,  2),
    (2514, 'Pool/Hot Tub Maintenance',        125,  3),
    (2514, 'Outdoor/Landscaping',             150,  4),
    (2514, 'Software',                          0,  5),
    (2514, 'Household Supplies',              175,  6),
    (2514, 'Cleaning',                       1050,  7),
    (2514, 'Property Taxes (Monthly)',     245.00,  8),
    (2514, 'Insurance HOI',                   250,  9),
    (2514, 'CapEx Reserve',                   350, 10),
    (2514, 'MISC',                              0, 11),
    (2514, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2514
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2515  market_id=108  bedrooms=3
-- property_size=1800 -> opex_by_size.sqft=2000  purchase_price=699000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2515;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2515, 'Internet',                        100,  0),
    (2515, 'Utilities',                       525,  1),
    (2515, 'Pest Control',                     60,  2),
    (2515, 'Pool/Hot Tub Maintenance',        125,  3),
    (2515, 'Outdoor/Landscaping',             150,  4),
    (2515, 'Software',                          0,  5),
    (2515, 'Household Supplies',              175,  6),
    (2515, 'Cleaning',                       1050,  7),
    (2515, 'Property Taxes (Monthly)',     326.20,  8),
    (2515, 'Insurance HOI',                   250,  9),
    (2515, 'CapEx Reserve',                   350, 10),
    (2515, 'MISC',                              0, 11),
    (2515, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2515
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2516  market_id=108  bedrooms=3
-- property_size=2192 -> opex_by_size.sqft=2750  purchase_price=669000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2516;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2516, 'Internet',                        150,  0),
    (2516, 'Utilities',                       625,  1),
    (2516, 'Pest Control',                     75,  2),
    (2516, 'Pool/Hot Tub Maintenance',        125,  3),
    (2516, 'Outdoor/Landscaping',             150,  4),
    (2516, 'Software',                          0,  5),
    (2516, 'Household Supplies',              175,  6),
    (2516, 'Cleaning',                       1050,  7),
    (2516, 'Property Taxes (Monthly)',     312.20,  8),
    (2516, 'Insurance HOI',                   250,  9),
    (2516, 'CapEx Reserve',                   350, 10),
    (2516, 'MISC',                              0, 11),
    (2516, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2516
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2517  market_id=108  bedrooms=3
-- property_size=1494 -> opex_by_size.sqft=1500  purchase_price=550000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2517;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2517, 'Internet',                        100,  0),
    (2517, 'Utilities',                       425,  1),
    (2517, 'Pest Control',                     60,  2),
    (2517, 'Pool/Hot Tub Maintenance',        125,  3),
    (2517, 'Outdoor/Landscaping',             150,  4),
    (2517, 'Software',                          0,  5),
    (2517, 'Household Supplies',              175,  6),
    (2517, 'Cleaning',                       1050,  7),
    (2517, 'Property Taxes (Monthly)',     256.67,  8),
    (2517, 'Insurance HOI',                   250,  9),
    (2517, 'CapEx Reserve',                   350, 10),
    (2517, 'MISC',                              0, 11),
    (2517, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2517
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

----------------------------------------------------------------------

-- underwriting_id=2518  market_id=108  bedrooms=3
-- property_size=1824 -> opex_by_size.sqft=2000  purchase_price=698000.00
-- 13 of 13 catalog rows resolved

BEGIN;

DELETE FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2518;

INSERT INTO iron_bank.uw_operating_expenses
    (underwriting_id, expense_name, monthly_amount, sort_order)
VALUES
    (2518, 'Internet',                        100,  0),
    (2518, 'Utilities',                       525,  1),
    (2518, 'Pest Control',                     60,  2),
    (2518, 'Pool/Hot Tub Maintenance',        125,  3),
    (2518, 'Outdoor/Landscaping',             150,  4),
    (2518, 'Software',                          0,  5),
    (2518, 'Household Supplies',              175,  6),
    (2518, 'Cleaning',                       1050,  7),
    (2518, 'Property Taxes (Monthly)',     325.73,  8),
    (2518, 'Insurance HOI',                   250,  9),
    (2518, 'CapEx Reserve',                   350, 10),
    (2518, 'MISC',                              0, 11),
    (2518, 'HOA Fees',                          0, 12);

SELECT id, expense_name, monthly_amount, sort_order
FROM iron_bank.uw_operating_expenses
WHERE underwriting_id = 2518
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;
