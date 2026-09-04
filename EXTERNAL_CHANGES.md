# External Changes Register

Every change this app makes to a DocType **outside** `iso_compliance` is recorded here
before it is built. That includes Custom Fields, Property Setters, Client Scripts,
Workflows and permission changes applied to `frappe`, `erpnext`, `hrms`,
`india_compliance`, `crm`, `wiki` or `hatim_carbon` DocTypes.

Rules for this file:

1. Nothing is added to any external DocType until the entry below is approved by the
   developer.
2. Every entry names the exact target DocType, fieldname, fieldtype and the reason.
3. Anything listed here ships as a **fixture**, so installing the app on production
   reproduces it exactly and reversibly.
4. Core ERPNext behaviour is not modified. Additive Custom Fields only — no changes to
   existing field definitions, no monkeypatching, no overridden core methods.

## Status: six applied changes — four display/naming, two behaviour (Work Order BOM from Sales Order: insert hook + dialog override)

One display-only HTML Custom Field (Quality Meeting minutes guidance) and one
Document Naming Rule (Quality Meeting numbers as FRM-024). Both additive, both
reversible, both in the Approved and applied table at the end of this file. No
data-bearing Custom Field exists on any external DocType; those remain proposals.

## Proposed — awaiting approval

Two registers in REG-001 have no data source in ERPNext because the fields they
depend on do not exist. Neither proposal changes existing behaviour: both are
additive Custom Fields shipped as fixtures, and removing them leaves ERPNext exactly
as it is today.

### ~~1. Asset — calibration control~~ — WITHDRAWN, not needed

Six custom fields were proposed on `Asset` to record calibration frequency, last and
next calibration date, agency and certificate. **That proposal is withdrawn.**

ERPNext already models all of it and the schema was simply unused: an
`Asset Maintenance` record holds `Asset Maintenance Task` rows, each with a
`maintenance_type` of Preventive Maintenance **or Calibration**, a `periodicity`
(including Yearly), a `next_due_date`, a `last_completion_date` and an assignee.
Completion is recorded as an `Asset Maintenance Log`, which carries a certificate
attachment.

So calibration and annual maintenance need **no schema change at all** — the
dashboard, the report and the notification all run off ERPNext's own tables. This
covers jigs and dies as well as measuring instruments, which the custom fields would
not have.

What remains is a data task, not a development one: 31 of 33 Assets have no
maintenance plan, and none are submitted into service.

### 1. Supplier — approval status (REG-007, SOP-005, ISO 9001 clause 8.4)

REG-007 is the Approved Suppliers Register, but there is currently no way to express
approval: of 945 Suppliers, 943 have no supplier group, none are on hold, none are
disabled, and only 3 have a scorecard. A register built on `Supplier` today would
list all 945, which is not a controlled list of approved suppliers.

Supplier Group was considered instead and rejected: it already carries a different
meaning, and overloading it would make approval status invisible to anyone reading
the group.

| Fieldname | Type | Label | Purpose |
| --- | --- | --- | --- |
| `custom_approval_status` | Select | Approval Status | `Approved` / `Provisional` / `Not Approved` / `Suspended` |
| `custom_approved_on` | Date | Approved On | When approval was granted |
| `custom_approved_by` | Link (User) | Approved By | Who granted it |
| `custom_reapproval_due` | Date | Re-approval Due | Drives periodic re-evaluation required by 8.4 |

### 2. Register columns awaiting fields (2026-08-07 register-format alignment)

The printed registers now follow the column layout of the source register files.
Where a source column has no ERPNext field, the print shows the column **blank**
(the heading is there, the cells are empty) until the field below exists. Each
field is additive, ships as a fixture, and its only purpose is to let the named
register column carry live data. Approving a row here and installing the fixture
makes the corresponding blank column fill in; nothing else changes.

| Target DocType | Fieldname | Type | Register column it fills |
| --- | --- | --- | --- |
| Non Conformance | `custom_supplier` | Link (Supplier) | REG-009 "Supplier" |
| Non Conformance | `custom_product` | Data | REG-009 "Product / Part No." |
| Non Conformance | `custom_batch_wo` | Data | REG-009 "Batch / WO No." |
| Non Conformance | `custom_qty` | Float | REG-009 "Qty." |
| Non Conformance | `custom_disposition` | Select (Rework / Repair / Reject / Use As Is / Return) | REG-009 "Disposition" |
| Non Conformance | `custom_approved_by` | Link (User) | REG-009 "Approved By" |
| Non Conformance | `custom_closure_date` | Date | REG-009 "Closure Date" |
| Asset | `custom_make` | Data | REG-011 "Make" / REG-020 "Make / Manufacturer" |
| Asset | `custom_model` | Data | REG-020 "Model" |
| Asset | `custom_serial_no` | Data | REG-011 / REG-020 "Serial No." |
| Asset | `custom_range` | Data | REG-011 "Range" |
| Asset | `custom_least_count` | Data | REG-011 "Least Count (mm)" |
| Asset | `custom_critical_equipment` | Check | REG-020 "Critical Equipment (Y/N)" |
| Quality Action | `custom_related_reference` | Data | REG-018 "Related NCR / Audit / Complaint" |
| Quality Action | `custom_root_cause` | Small Text | REG-018 "Root Cause" |
| Quality Action | `custom_target_date` | Date | REG-018 "Target Date" |
| Quality Action | `custom_completion_date` | Date | REG-018 "Completion Date" |
| Quality Action | `custom_effectiveness_verified` | Select (Pending / Yes / No) | REG-018 "Effectiveness Verified (Y/N)" |
| Quality Meeting | `custom_meeting_date` | Date | REG-019 "Meeting Date" (today: creation date) |
| Quality Meeting | `custom_review_period` | Data | REG-019 "Review Period" |
| Quality Meeting | `custom_chairperson` | Data | REG-019 "Chairperson" |
| Quality Feedback | `custom_mode` | Select (Email / Phone / Survey / Verbal) | REG-025 "Mode of Feedback" |
| Quality Feedback | `custom_feedback_type` | Select (Positive / Suggestion / Complaint) | REG-025 "Feedback Type" |
| Quality Feedback | `custom_summary` | Small Text | REG-025 "Feedback Summary" |
| Quality Feedback | `custom_action_required` | Select (Yes / No) | REG-025 "Action Required" |
| Quality Feedback | `custom_feedback_status` | Select (Open / Closed) | REG-025 "Status" |
| Employee | `custom_roles_responsibilities` | Small Text | REG-013 "Roles & Responsibilities" |
| Employee | `custom_authority` | Small Text | REG-013 "Authority" |
| Supplier | `custom_category_critical` | Select (Critical / Non-Critical) | REG-007 "Category" (joins proposal 1's approval fields) |
| Supplier | `custom_qualification_method` | Data | REG-007 "Qualification Method" |

## Observations about the site (no change made)

### Print Settings still selects wkhtmltopdf

`Print Settings.pdf_generator` on the restored production data is `wkhtmltopdf`, not
`chrome`. This app's print format sets `pdf_generator = "chrome"` on the Print Format
record itself, which is what actually governs rendering, so nothing site-wide was
changed and no existing print format was affected.

It is worth knowing that every other print format on the site is still rendered by
wkhtmltopdf, which does not support modern CSS. Switching the site default is a
deliberate decision with blast radius across all existing formats, so it is recorded
here rather than made.

### Per-page numbering is unavailable on frappe 16.29

The framework asks the footer page to run `clone_and_update(...)` to stamp per-page
numbers, but the script that defines that function is not present in the installed
frappe, so the call fails silently. A substitute was written and tested; it restored
numbering but the framework still inserts a blank footer page in second position,
which shifts every later page's number by one.

A controlled document with wrong page numbers is worse than one with none, so the
footer is static and instead repeats the document number, issue and revision on every
page. Worth revisiting when frappe ships the missing asset.

## Approved and applied

| Date | Target DocType | Field / Change | Type | Reason | Fixture |
| ---- | -------------- | -------------- | ---- | ------ | ------- |
| 2026-09-04 | Issue | `custom_sales_order` | Custom Field, Link (Sales Order) | A customer complaint traced to the order it concerns; also the target of the Sales Order form's Create → Customer Complaint button. Requested by the developer. | yes |
| 2026-09-04 | Issue | `custom_root_cause` | Custom Field, Small Text | Fills REG-008's "Investigation / Root Cause" column (promoted from the pending proposal). Requested by the developer. | yes |
| 2026-09-04 | Sales Order | form script: Create → Customer Complaint button | doctype_js (display only) | Opens a new Issue pre-filled with the order and customer — the QMS's complaint entry point (FRM-028). Shown on drafts and submitted orders. Requested by the developer. | code (hooks.py) |
| 2026-09-04 | Notification | five "Techno-Commercial Review: …" records | Notification records (record, not schema) | In-app bell notifications as the review changes hands: each stage pings its reviewer role, send-back and approval ping the review's creator. Created by the ensure hook; deleting the records reverts the site untouched. Requested by the developer. | via hook |
| 2026-09-04 | Sales Order | `before_submit` hook | doc_events (behaviour) | SOP-004's contract-review gate: an order of ₹ 5,00,000+ cannot be submitted without an approved Techno-Commercial Review (FRM-036) of the required tier concluding Accept; an in-flight review of any order must finish first; a review concluding Reject always blocks. `TCR_ENFORCEMENT` in overrides/sales_order.py flips to "warn" for an advisory-only rollout. Requested by the developer. | code (hooks.py) |
| 2026-09-04 | Sales Order | form script (button + banner) | doctype_js (display only) | Adds Create → Techno-Commercial Review, opening FRM-036 pre-filled from the order, and an intro banner when the slabs demand a review. No behaviour change; the gate is server-side. Requested by the developer. | code (hooks.py) |
| 2026-09-02 | Sales Order | `get_work_order_items` override | override_whitelisted_methods (wrapper) | The make-Work-Order and raw-material-request dialogs display and submit the row's chosen BOM instead of the item default. Calls the core function first; only BOM values are corrected. Requested by the developer. | code (hooks.py) |
| 2026-09-02 | Work Order | `before_insert` hook | doc_events (behaviour) | A Sales Order row's chosen `bom_no` replaces the automatic default on the Work Order created from that row; a manually chosen (non-default) BOM on the Work Order is never overridden. Fixes ERPNext ignoring the row's BOM in get_work_order_items. Requested by the developer. | code (hooks.py) |
| 2026-08-26 | BOM | `inspection_required` description | Property Setter (tooltip only) | Explains that checking it gates Work Order completion behind a Quality Inspection of the output (the PDI). Requested by the developer. | yes |
| 2026-08-26 | Item | `inspection_required_before_delivery` description | Property Setter (tooltip only) | Explains that checking it blocks Delivery Note submission without an accepted Outgoing inspection (the dispatch gate). Requested by the developer. | yes |
| 2026-08-16 | Quality Meeting | `custom_minutes_guidance` | HTML (display only) | Explains, above the minutes table, when a minute links to a Quality Review, Quality Action or Quality Feedback and what to write. Prints as a note on FRM-024's blank form. Requested by the developer. | yes |
| 2026-08-14 | Quality Meeting | Document Naming Rule `HCCPL/QMS/FRM-024-` | Naming rule (record, not schema) | Meeting records number themselves as the form the register knows them by. Created by the ensure hook; deleting the rule reverts naming. | via hook |
