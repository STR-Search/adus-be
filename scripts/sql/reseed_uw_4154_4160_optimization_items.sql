-- Reseed uw_optimization_items for underwritings 4154..4160, whose rehab
-- budget was imported from the GSheet rather than seeded from market data.
--
-- Amounts and labels are the sheet's, kept verbatim, except the three items
-- every deal carries, which are canonicalized to the names in
-- PrepareUwDataService so they match app-seeded deals rather than repeating the
-- legacy unspaced spellings. Only total_price is written; base_price, metric,
-- tier, spec and notes have no source on the sheet and stay NULL. sort_order is
-- stamped from sheet position, as the repository does on save.
--
-- One transaction per deal: check each verify SELECT before its COMMIT.

-- underwriting_id=4154  9 items, 2 label(s) canonicalized, total 74500.00

BEGIN;

DELETE FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4154;

-- base_price, metric, tier, spec and notes are left NULL: the sheet
-- supplies no figure for them.
INSERT INTO iron_bank.uw_optimization_items
    (underwriting_id, category, total_price, sort_order)
VALUES
    (4154, 'Furniture / Decor / Essentials',     10000.00,  0),
    (4154, 'Accent Walls',                        3500.00,  1),
    (4154, 'Game Room Mural',                     4500.00,  2),
    (4154, 'Grading',                            10000.00,  3),
    (4154, 'Mini Golf',                          12500.00,  4),
    (4154, 'Playground',                          6500.00,  5),
    (4154, 'Landscaping / Lighting',              7500.00,  6),
    (4154, 'Design / Project Management',        20000.00,  7),  -- canonicalized
    (4154, 'Install / Staging / Warehousing',        0.00,  8);  -- canonicalized

SELECT id, category, total_price, sort_order
FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4154
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4155  13 items, 2 label(s) canonicalized, total 342000.00

BEGIN;

DELETE FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4155;

-- base_price, metric, tier, spec and notes are left NULL: the sheet
-- supplies no figure for them.
INSERT INTO iron_bank.uw_optimization_items
    (underwriting_id, category, total_price, sort_order)
VALUES
    (4155, 'Furniture / Decor / Essentials',    105000.00,  0),
    (4155, 'Game Room',                          10000.00,  1),
    (4155, 'Garage to 5th, 6th, 7th bedroom',    65000.00,  2),
    (4155, 'Garage add bathroom',                25000.00,  3),
    (4155, 'Permits/Architect Plans',             8000.00,  4),
    (4155, 'Mini Pickleball Court',              30000.00,  5),
    (4155, 'Landscaping Removal',                10000.00,  6),
    (4155, 'Pool Heater',                        12000.00,  7),
    (4155, 'Fire Pit / Chairs',                   6500.00,  8),
    (4155, 'Lighting / Turf',                    10000.00,  9),
    (4155, 'Accent Walls/Murals',                10000.00, 10),
    (4155, 'Design / Project Management',        28000.00, 11),  -- canonicalized
    (4155, 'Install / Staging / Warehousing',    22500.00, 12);  -- canonicalized

SELECT id, category, total_price, sort_order
FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4155
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4156  9 items, 2 label(s) canonicalized, total 210000.00

BEGIN;

DELETE FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4156;

-- base_price, metric, tier, spec and notes are left NULL: the sheet
-- supplies no figure for them.
INSERT INTO iron_bank.uw_optimization_items
    (underwriting_id, category, total_price, sort_order)
VALUES
    (4156, 'Furniture / Decor / Essentials',         0.00,  0),
    (4156, 'Game Room Mural',                     5000.00,  1),
    (4156, 'New Bedding',                        10000.00,  2),
    (4156, 'Grading',                            20000.00,  3),
    (4156, 'Inground Pool/Deck',                125000.00,  4),
    (4156, 'Mini Golf',                          15000.00,  5),
    (4156, 'Landscaping / Lighting',             10000.00,  6),
    (4156, 'Design / Project Management',        25000.00,  7),  -- canonicalized
    (4156, 'Install / Staging / Warehousing',        0.00,  8);  -- canonicalized

SELECT id, category, total_price, sort_order
FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4156
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4157  16 items, 2 label(s) canonicalized, total 308000.00

BEGIN;

DELETE FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4157;

-- base_price, metric, tier, spec and notes are left NULL: the sheet
-- supplies no figure for them.
INSERT INTO iron_bank.uw_optimization_items
    (underwriting_id, category, total_price, sort_order)
VALUES
    (4157, 'Furniture / Decor / Essentials',     75000.00,  0),
    (4157, 'Interior Paint',                     13000.00,  1),
    (4157, 'Game Room',                          10000.00,  2),
    (4157, 'Fans/Fixtures/Lighting',              5500.00,  3),
    (4157, 'Garage to 4th bedroom',              50000.00,  4),
    (4157, 'Permits/Architect Plans',             8000.00,  5),
    (4157, 'Pickleball Court',                   40000.00,  6),
    (4157, 'Mini Golf',                          10000.00,  7),
    (4157, 'Playground',                          6500.00,  8),
    (4157, 'Fire Pit / Chairs',                   6500.00,  9),
    (4157, 'Landscaping/Lighting',               12500.00, 10),
    (4157, 'Remove Pool Cage',                    5500.00, 11),
    (4157, 'Murals/Accent Walls',                 7500.00, 12),
    (4157, 'Pool Heater',                        12000.00, 13),
    (4157, 'Design / Project Management',        25000.00, 14),  -- canonicalized
    (4157, 'Install / Staging / Warehousing',    21000.00, 15);  -- canonicalized

SELECT id, category, total_price, sort_order
FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4157
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4158  4 items, 2 label(s) canonicalized, total 8000.00

BEGIN;

DELETE FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4158;

-- base_price, metric, tier, spec and notes are left NULL: the sheet
-- supplies no figure for them.
INSERT INTO iron_bank.uw_optimization_items
    (underwriting_id, category, total_price, sort_order)
VALUES
    (4158, 'Furniture / Decor / Essentials',         0.00,  0),
    (4158, 'Pool Mural',                          8000.00,  1),
    (4158, 'Design / Project Management',            0.00,  2),  -- canonicalized
    (4158, 'Install / Staging / Warehousing',        0.00,  3);  -- canonicalized

SELECT id, category, total_price, sort_order
FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4158
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4159  11 items, 2 label(s) canonicalized, total 404000.00

BEGIN;

DELETE FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4159;

-- base_price, metric, tier, spec and notes are left NULL: the sheet
-- supplies no figure for them.
INSERT INTO iron_bank.uw_optimization_items
    (underwriting_id, category, total_price, sort_order)
VALUES
    (4159, 'Furniture / Decor / Essentials',    175000.00,  0),
    (4159, 'Mini Golf',                          15000.00,  1),
    (4159, 'Playground',                          9000.00,  2),
    (4159, 'Game Room Upgrades',                 30000.00,  3),
    (4159, 'Landscaping / Lighting',             10000.00,  4),
    (4159, 'Hot Tub (x2)',                       30000.00,  5),
    (4159, 'Sauna (x2)',                         30000.00,  6),
    (4159, 'Misc.',                              15000.00,  7),
    (4159, 'Accent Walls / Murals',              15000.00,  8),
    (4159, 'Design / Project Management',        45000.00,  9),  -- canonicalized
    (4159, 'Install / Staging / Warehousing',    30000.00, 10);  -- canonicalized

SELECT id, category, total_price, sort_order
FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4159
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

-- underwriting_id=4160  12 items, 2 label(s) canonicalized, total 267500.00

BEGIN;

DELETE FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4160;

-- base_price, metric, tier, spec and notes are left NULL: the sheet
-- supplies no figure for them.
INSERT INTO iron_bank.uw_optimization_items
    (underwriting_id, category, total_price, sort_order)
VALUES
    (4160, 'Furniture / Decor / Essentials',         0.00,  0),
    (4160, 'Upgrade game room',                  10000.00,  1),
    (4160, 'Playground',                          6500.00,  2),
    (4160, 'Grading',                            12500.00,  3),
    (4160, 'Inground pool/deck',                125000.00,  4),
    (4160, 'Mini golf',                          12500.00,  5),
    (4160, 'Pickleball court',                   42000.00,  6),
    (4160, 'Landscaping/lighting',               12000.00,  7),
    (4160, 'Fire Pit',                            7000.00,  8),
    (4160, 'Tree Clearing',                      10000.00,  9),
    (4160, 'Design / Project Management',        30000.00, 10),  -- canonicalized
    (4160, 'Install / Staging / Warehousing',        0.00, 11);  -- canonicalized

SELECT id, category, total_price, sort_order
FROM iron_bank.uw_optimization_items
WHERE underwriting_id = 4160
ORDER BY sort_order;

-- Check the SELECT above before committing.
COMMIT;

