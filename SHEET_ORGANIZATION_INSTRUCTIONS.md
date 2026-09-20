# Standard Operating Procedure (SOP): Sheet Organization & Country Grouping

This document outlines the standard procedure and rules for maintaining, sorting, and organizing rows within the PhD Outreach Tracking Google Sheet (`Professors List`).

---

## 1. Objective & Core Principles

The primary objective of this procedure is to ensure that prospective professors in the Google Sheet are logically organized into contiguous geographical blocks while strictly maintaining data integrity and historical record ordering.

### Principles:
1. **Contiguous Country Blocks**: All records belonging to the same country must appear together in one continuous section of the sheet.
2. **Strict Preservation of Row Integrity**:
   - Every row is treated as an atomic unit spanning all columns (`Professor Name` through `Next Action`).
   - No cell values, formulas, notes, or column alignments may be altered during reordering.
3. **Stable Relative Ordering ("Upper Data Stays Upper")**:
   - Within any country block, the original relative order of candidates must be strictly preserved.
   - If Professor A was positioned above Professor B in the original sheet, Professor A must remain above Professor B after grouping.
4. **Country Block Sequencing**:
   - Country blocks are ordered according to their **first chronological appearance** in the sheet (e.g., Germany first, then Japan, etc.).
   - This ensures top-level layout continuity and prevents disruptions to ongoing outreach campaigns.

---

## 2. Spreadsheet Schema Reference (29 Columns)

The table below defines the exact column ordering that must be preserved:

| Col Index | Column Header | Description |
| :---: | :--- | :--- |
| **A** (1) | `Professor Name` | Full name with title |
| **B** (2) | `University` | Institution name |
| **C** (3) | `Country` | Primary grouping key (e.g., Germany, Japan, USA, China) |
| **D** (4) | `Department/Lab` | Department or laboratory |
| **E** (5) | `Contact Group (Lock)` | Departmental mutual exclusion lock |
| **F** (6) | `Priority` | Outreach priority (1, 2, 3) |
| **G** (7) | `Professor Email` | Official academic contact email |
| **H** (8) | `Professor Profile URL` | Personal or faculty profile URL |
| **I** (9) | `Google Scholar URL` | Google Scholar profile link |
| **J** (10) | `Research Area` | Key research keywords |
| **K** (11) | `Funding Status` | Availability of funding / scholarships |
| **L** (12) | `Deadline` | Application deadline (if applicable) |
| **M** (13) | `Pipeline Status` | Current pipeline stage (Pending, Needs Review, etc.) |
| **N** (14) | `Target Timezone` | Local timezone of institution |
| **O** (15) | `Preferred Send Day/Time(BDTime)` | Optimal sending window in Bangladesh Time |
| **P** (16) | `LLM Research Summary` | AI-generated summary of recent research |
| **Q** (17) | `LLM Fit Score (1-10)` | Research alignment rating |
| **R** (18) | `Email Subject` | Synthesized email subject line |
| **S** (19) | `Email Draft` | Generated cold outreach email draft |
| **T** (20) | `Response Status` | Status of advisor reply |
| **U** (21) | `First Contact Date` | Date initial email was sent |
| **V** (22) | `Last Contact Date` | Date of most recent communication |
| **W** (23) | `Response Date` | Date professor replied |
| **X** (24) | `Follow-up #1 Date` | Scheduled/sent date for follow-up 1 |
| **Y** (25) | `Follow-up #2 Date` | Scheduled/sent date for follow-up 2 |
| **Z** (26) | `Meeting Scheduled` | Scheduled interview / discussion details |
| **AA** (27) | `Application Submitted` | Formal application status |
| **AB** (28) | `Notes` | Freeform notes and reminders |
| **AC** (29) | `Next Action` | Pending task or action item |

---

## 3. Stable Grouping Algorithm (Python Reference)

When reorganizing the sheet, the following Python logic must be used to ensure stable grouping:

```python
from collections import OrderedDict

def group_rows_stably_by_country(rows: list, country_col_idx: int = 2) -> list:
    """
    Groups tabular rows by country stably:
    - Country blocks ordered by first appearance in original rows.
    - Within each country block, original relative order is preserved.
    """
    country_groups = OrderedDict()
    for row in rows:
        country = row[country_col_idx].strip() if len(row) > country_col_idx else ""
        if not country:
            country = "Unspecified"
        country_groups.setdefault(country, []).append(row)

    reordered = []
    for country, grouped_rows in country_groups.items():
        reordered.extend(grouped_rows)
    return reordered
```

---

## 4. Execution & Validation Protocol

1. **Pre-reorganization Audit**:
   - Record total non-empty row count.
   - Record checksum / hash of all rows to ensure zero row loss or data modification.
2. **In-Memory Transformation**:
   - Extract records from row 2 downward.
   - Apply the stable grouping function.
3. **Atomic Sheet Update**:
   - Write reordered rows to range `A2:AC{total_rows}` using `worksheet.update(values=..., range_name=..., value_input_option="USER_ENTERED")`.
4. **Post-reorganization Verification**:
   - Confirm total row count matches exactly.
   - Verify that each country appears in a single, contiguous block.
   - Verify that for any two rows within the same country, their relative order is identical to the original order.
