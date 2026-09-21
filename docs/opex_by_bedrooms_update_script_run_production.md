# opex_by_bedrooms_update_script_run_production

> **Production run log** · OPEX by bedrooms · **315 rows committed**

## Run at a glance

| Metric | Result |
| :--- | ---: |
| Source file | `opex-by-bedrooms-master.csv` |
| Target table | `opex_by_bedrooms` |
| Source rows | 315 |
| Source value columns | 18 |
| Markets | 45 |
| Bedrooms per market | 1–7 |
| Rows to update | 315 |
| Already current | 0 |
| Rows committed (reported by log) | **315** |
| Individual field changes | **480** |

## Change summary

**Every row:** `pool_and_hot_tub` changed from `NULL` → `350`.

| Column | Rows changed |
| :--- | ---: |
| `pool_and_hot_tub` | 315 |
| `appreciation` | 78 |
| `land_value` | 29 |
| `cleaning_fee` | 12 |
| `pool_hot_tub_high` | 12 |
| `pool_hot_tub_low` | 12 |
| `num_of_turns` | 10 |
| `capex_reserve` | 6 |
| `insurance_hoi` | 5 |
| `supplies` | 1 |

## Market details

Expand a market to inspect each bedroom count. Values retain the exact numeric notation and `NULL` markers from the supplied log.

<details>
<summary><strong>Albrightsville - PA</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.0425` | `0.035` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.0425` | `0.035` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.0425` | `0.035` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.0425` | `0.035` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.0425` | `0.035` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.0425` | `0.035` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.0425` | `0.035` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Albuquerque - NM</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.0425` | `0.035` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.0425` | `0.035` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.0425` | `0.035` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.0425` | `0.035` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.0425` | `0.035` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.0425` | `0.035` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.0425` | `0.035` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Asheville - NC</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.045` | `0.046` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.045` | `0.046` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.045` | `0.046` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.045` | `0.046` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.045` | `0.046` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.045` | `0.046` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.045` | `0.046` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Austin - TX - No Lake</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Blue Ridge - GA</strong> · 7 rows · 8 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.0475` | `0.045` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Bradenton - FL</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.05` | `0.03` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.05` | `0.03` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.05` | `0.03` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.05` | `0.03` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.05` | `0.03` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.05` | `0.03` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.05` | `0.03` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Broken Bow - OK</strong> · 7 rows · 46 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.0425` | `0.0475` |
| 1 | `capex_reserve` | `350` | `300` |
| 1 | `cleaning_fee` | `170` | `125` |
| 1 | `insurance_hoi` | `300` | `250` |
| 1 | `num_of_turns` | `8` | `8.5` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 1 | `pool_hot_tub_high` | `350` | `275` |
| 1 | `pool_hot_tub_low` | `175` | `125` |
| 2 | `appreciation` | `0.0425` | `0.0475` |
| 2 | `capex_reserve` | `350` | `325` |
| 2 | `cleaning_fee` | `190` | `150` |
| 2 | `insurance_hoi` | `300` | `275` |
| 2 | `num_of_turns` | `7.5` | `8` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_hot_tub_high` | `346` | `275` |
| 2 | `pool_hot_tub_low` | `175` | `125` |
| 3 | `appreciation` | `0.0425` | `0.0475` |
| 3 | `capex_reserve` | `400` | `350` |
| 3 | `cleaning_fee` | `225` | `175` |
| 3 | `insurance_hoi` | `400` | `325` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_hot_tub_high` | `350` | `275` |
| 3 | `pool_hot_tub_low` | `175` | `125` |
| 4 | `appreciation` | `0.0425` | `0.0475` |
| 4 | `capex_reserve` | `500` | `400` |
| 4 | `cleaning_fee` | `275` | `225` |
| 4 | `insurance_hoi` | `425` | `375` |
| 4 | `num_of_turns` | `6` | `6.25` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_hot_tub_high` | `350` | `275` |
| 4 | `pool_hot_tub_low` | `175` | `125` |
| 5 | `appreciation` | `0.0425` | `0.0475` |
| 5 | `capex_reserve` | `600` | `500` |
| 5 | `cleaning_fee` | `325` | `275` |
| 5 | `insurance_hoi` | `450` | `425` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_hot_tub_high` | `350` | `275` |
| 5 | `pool_hot_tub_low` | `175` | `125` |
| 5 | `supplies` | `275` | `250` |
| 6 | `appreciation` | `0.0425` | `0.0475` |
| 6 | `capex_reserve` | `700` | `600` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_hot_tub_high` | `350` | `275` |
| 6 | `pool_hot_tub_low` | `175` | `125` |
| 7 | `appreciation` | `0.0425` | `0.0475` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Charlotte - NC</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Clearwater - FL - Greater Area</strong> · 7 rows · 21 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.05` | `0.04` |
| 1 | `land_value` | `0.28` | `0.3` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.05` | `0.04` |
| 2 | `land_value` | `0.28` | `0.3` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.05` | `0.04` |
| 3 | `land_value` | `0.28` | `0.3` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.05` | `0.04` |
| 4 | `land_value` | `0.28` | `0.3` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.05` | `0.04` |
| 5 | `land_value` | `0.28` | `0.3` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.05` | `0.04` |
| 6 | `land_value` | `0.28` | `0.3` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.05` | `0.04` |
| 7 | `land_value` | `0.28` | `0.3` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Columbus - OH</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.04` | `0.0425` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.04` | `0.0425` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.04` | `0.0425` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.04` | `0.0425` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.04` | `0.0425` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.04` | `0.0425` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.04` | `0.0425` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Cripple Creek - CO</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Denver - CO - Greater Area</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>East Stroudsburg - PA</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.0425` | `0.03` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.0425` | `0.03` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.0425` | `0.03` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.0425` | `0.03` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.0425` | `0.03` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.0425` | `0.03` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.0425` | `0.03` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Ellijay - GA</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Finger Lakes - NY</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Fort Lauderdale - FL</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.055` | `0.045` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.055` | `0.045` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.055` | `0.045` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.055` | `0.045` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.055` | `0.045` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.055` | `0.045` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.055` | `0.045` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Galena - IL</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.0425` | `0.04` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.0425` | `0.04` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.0425` | `0.04` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.0425` | `0.04` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.0425` | `0.04` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.0425` | `0.04` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.0425` | `0.04` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Gatlinburg - TN</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Greene County - NY</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Hot Springs - AR</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Indianapolis - IN</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `appreciation` | `0.045` | `0.04` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `appreciation` | `0.045` | `0.04` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `appreciation` | `0.045` | `0.04` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `appreciation` | `0.045` | `0.04` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `appreciation` | `0.045` | `0.04` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `appreciation` | `0.045` | `0.04` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `appreciation` | `0.045` | `0.04` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Lake Harmony - PA</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Lower Hudson Valley - NY</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Massanuten - VA</strong> · 7 rows · 21 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `cleaning_fee` | `125` | `NULL` |
| 1 | `num_of_turns` | `7` | `NULL` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `cleaning_fee` | `150` | `NULL` |
| 2 | `num_of_turns` | `7` | `NULL` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `cleaning_fee` | `175` | `NULL` |
| 3 | `num_of_turns` | `6.5` | `NULL` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `cleaning_fee` | `225` | `NULL` |
| 4 | `num_of_turns` | `6.25` | `NULL` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `cleaning_fee` | `275` | `NULL` |
| 5 | `num_of_turns` | `5.5` | `NULL` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `cleaning_fee` | `350` | `NULL` |
| 6 | `num_of_turns` | `5` | `NULL` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `cleaning_fee` | `400` | `NULL` |
| 7 | `num_of_turns` | `5` | `NULL` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Miami - FL</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>North Scottsdale - AZ</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Pagosa Springs - CO</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Panama City Beach - FL</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Penn Estates - PA</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Pigeon Forge - TN</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Poconos Pines - PA</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Rockbridge - OH</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>San Antonio - TX</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `land_value` | `0.2` | `0.22` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `land_value` | `0.2` | `0.22` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `land_value` | `0.2` | `0.22` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `land_value` | `0.2` | `0.22` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `land_value` | `0.2` | `0.22` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `land_value` | `0.2` | `0.22` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `land_value` | `0.2` | `0.22` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Sedona - AZ</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `land_value` | `0.24` | `0.25` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `land_value` | `0.24` | `0.25` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `land_value` | `0.24` | `0.25` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `land_value` | `0.24` | `0.25` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `land_value` | `0.24` | `0.25` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `land_value` | `0.24` | `0.25` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `land_value` | `0.24` | `0.25` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Sevierville - TN</strong> · 7 rows · 19 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 1 | `pool_hot_tub_high` | `350` | `275` |
| 1 | `pool_hot_tub_low` | `175` | `125` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_hot_tub_high` | `350` | `275` |
| 2 | `pool_hot_tub_low` | `175` | `125` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_hot_tub_high` | `350` | `275` |
| 4 | `pool_hot_tub_low` | `175` | `125` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_hot_tub_high` | `350` | `275` |
| 5 | `pool_hot_tub_low` | `175` | `125` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_hot_tub_high` | `350` | `275` |
| 6 | `pool_hot_tub_low` | `175` | `125` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_hot_tub_high` | `350` | `275` |
| 7 | `pool_hot_tub_low` | `175` | `125` |

</details>

<details>
<summary><strong>Shenandoah Valley - VA</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Saint Augustine - FL</strong> · 7 rows · 14 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `land_value` | `0.3` | `0.32` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `land_value` | `0.3` | `0.32` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `land_value` | `0.3` | `0.32` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `land_value` | `0.3` | `0.32` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `land_value` | `0.3` | `0.32` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `land_value` | `0.3` | `0.32` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `land_value` | `0.3` | `0.32` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Tampa - FL</strong> · 7 rows · 8 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `land_value` | `0.3` | `0.32` |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Texas Hill Country - TX</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Tobyhanna - PA</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Tucson - AZ</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Upper Hudson Valley - NY</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>West Palm Beach - FL</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Western Hudson Valley - NY</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

<details>
<summary><strong>Wintergreen - VA</strong> · 7 rows · 7 field changes</summary>

| Bedrooms | Column | Before | After |
| ---: | :--- | ---: | ---: |
| 1 | `pool_and_hot_tub` | `NULL` | `350` |
| 2 | `pool_and_hot_tub` | `NULL` | `350` |
| 3 | `pool_and_hot_tub` | `NULL` | `350` |
| 4 | `pool_and_hot_tub` | `NULL` | `350` |
| 5 | `pool_and_hot_tub` | `NULL` | `350` |
| 6 | `pool_and_hot_tub` | `NULL` | `350` |
| 7 | `pool_and_hot_tub` | `NULL` | `350` |

</details>

## Reported result

```text
opex_by_bedrooms: 315 row(s) to update, 0 already current
Committed 315 row(s).
```

*Formatted from the supplied script output.*
