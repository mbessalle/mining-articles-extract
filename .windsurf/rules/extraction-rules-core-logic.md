---
trigger: manual
---

# Rule: M&A Data Extraction - Core Logic
# Activation: Always On
# Description: Contains the primary schema, entity resolution, and core logic for extracting raw data from mining M&A articles. This file is supplemented by extraction_rules_edge_cases.md.

<schema>
# CRITICAL: For EACH field, you must provide a `value` and a `justification`.
# The `justification` MUST be a direct quote or very close paraphrase from the source text that proves the `value`.
# If a value is null because no information exists, the justification can be null. If a value is null because a candidate value was REJECTED based on a rule (e.g., wrong project), the justification MUST explain the rejection with a supporting quote.
{
  "ceo_buyer": { "value": "string | null", "justification": "string | null" },
  "interest_acquired_percent": { "value": "number | null", "justification": "string | null" },
  "currency": { "value": "string | null", "justification": "string | null" },
  "cash_payments_raw": { "value": "number | null", "justification": "string | null" },
  "share_payments_raw": { "value": "number | null", "justification": "string | null" },
  "cash_and_share_payments_combined_raw": { "value": "number | null", "justification": "string | null" },
  "amount_of_shares_issued": { "value": "number | null", "justification": "string | null" },
  "issued_share_price": { "value": "number | null", "justification": "string | null" },
  "exploration_commitment_meters": { "value": "number | null", "justification": "string | null" },
  "exploration_commitment_value_raw": { "value": "number | null", "justification": "string | null" },
  "nsr_acquired_percent": { "value": "number | null", "justification": "string | null" },
  "coverage_area_raw": { "value": "number | null", "justification": "string | null" },
  "coverage_area_unit": { "value": "string | null", "justification": "string | null" },
  "resource_size": { "value": "string | null", "justification": "string | null" },
  "buyer_ticker_and_exchange": { "value": "string | null", "justification": "string | null" }
}
</schema>

---
<entity_resolution_protocol>
- **Identify Roles First:** Before any extraction, you must perform these steps:
  1. Identify the Acquiring Company (`BUYER`). Keywords: "acquire", "purchase", "invest in", "farm-in".
  2. Identify the Target/Selling Company (`SELLER`).
  3. The `ceo_buyer` and `buyer_ticker_and_exchange` fields MUST belong to the `BUYER` entity.
</entity_resolution_protocol>

---
<extraction_logic>
- **PRINCIPLE:** RAW DATA ONLY. You must not perform any calculations or unit conversions. Your job is to find the raw numbers and labels.

- **Financial Data Extraction Hierarchy (IMPORTANT & MUTUALLY EXCLUSIVE):**
  - **PRIORITY 1 (Explicit Values):** If text has separate cash/share values, populate `cash_payments_raw` & `share_payments_raw`. Other financial fields null.
  - **PRIORITY 2 (Calculable Share Value):** If text has # shares & price, populate `amount_of_shares_issued` & `issued_share_price`. Other financial fields null.
  - **PRIORITY 3 (Combined Value):** If text has one combined value, populate `cash_and_share_payments_combined_raw`. Other financial fields null.

- **Rule for `resource_size_desc` (CRITICAL):**
  - **CONTENT:** The `value` for this field MUST be a concise string representing the mineral resource itself. It should ONLY include the quantity, grade, and total metal content.
    - **GOOD EXAMPLE:** `60Mt @ 1.2g/t Au for 2.3Moz`
    - **BAD EXAMPLE (too verbose):** `The project hosts a JORC 2012 Mineral Resource Estimate of 60Mt @ 1.2g/t Au for 2.3Moz of gold.`
  - **UNIT TYPE:** This field is for **MASS or VOLUME** (e.g., tonnes, ounces, pounds, Mt, Moz).
    - **CRITICAL:** You MUST NOT extract values representing **length** (e.g., '80,000 meters of drilling') or **area** (e.g., '127 sq km') into this field. That data belongs in `exploration_commitment_meters` or `coverage_area_raw`. Any length or area measurement is INVALID for `resource_size_desc`.

- **CEO:** The `value` must be the person's full name only. NO titles (CEO, Chair) or punctuation (,-) are allowed.
- **Currency:** The `value` must be the three-letter ISO code (AUD, CAD, USD). Infer the currency from context (e.g., ASX listed company implies AUD) if only a generic "$" symbol is used.
# ... (the rest of the logic rules remain the same) ...
</extraction_logic>