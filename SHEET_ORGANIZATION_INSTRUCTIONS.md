# Standard Operating Procedure (SOP): Sheet Organization & Country Grouping

This document outlines the standard procedure and rules for maintaining, sorting, and organizing rows within the PhD Outreach Tracking Google Sheet (`Professors List`).

---

## 1. Objective & Core Principles

The primary objective of this procedure is to ensure that prospective professors in the Google Sheet are logically organized into contiguous geographical blocks while strictly maintaining data integrity and historical record ordering.

### Principles:
1. **Contiguous Country Blocks**: All records belonging to the same country must appear together in one continuous section of the sheet.
2. **Institutional & Departmental Grouping**:
   - Within each country block, records are grouped and sorted by **`University` (A–Z)** so that all faculty members of the same institution appear together in a single contiguous block.
   - Within each university, records are grouped and sorted by **`Department/Lab` (A–Z)**.
3. **Strict Preservation of Row Integrity**:
   - Every row is treated as an atomic unit spanning all columns (`Professor Name` through `Next Action`).
   - No cell values, formulas, notes, or column alignments may be altered during reordering.
4. **Stable Relative Ordering ("Upper Data Stays Upper")**:
   - Within any specific department, the original relative order of candidates is strictly preserved.
5. **Country Block Sequencing**:
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

## 3. Stable Multi-Tier Grouping Algorithm (Python Reference)

When reorganizing the sheet, the following Python logic must be used to ensure stable grouping by Country, University, and Department:

```python
from collections import OrderedDict

def group_and_sort_sheet_rows(rows: list, country_order: list, country_idx: int = 2, univ_idx: int = 1, dept_idx: int = 3) -> list:
    """
    Groups tabular rows by Country -> University (A-Z) -> Department/Lab (A-Z):
    - Country blocks ordered by established sequence (first chronological appearance).
    - Within each country block, rows are sorted by University (A-Z) and Department/Lab (A-Z).
    - Within each department, original relative order is preserved.
    """
    country_groups = OrderedDict((c, []) for c in country_order)
    for idx, row in enumerate(rows):
        country = row[country_idx].strip() if len(row) > country_idx else ""
        if country not in country_groups:
            country_groups[country] = []
        country_groups[country].append((idx, row))

    reordered = []
    for country, indexed_rows in country_groups.items():
        sorted_rows = sorted(indexed_rows, key=lambda x: (
            x[1][univ_idx].strip().lower(),  # University A-Z
            x[1][dept_idx].strip().lower(),  # Department/Lab A-Z
            x[0]                             # Stable relative order
        ))
        reordered.extend([x[1] for x in sorted_rows])
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
