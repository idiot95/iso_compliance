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

## Status

Everything applied is in the table at the end of this file, newest first: the
SOP-004 build (Sales Order review gate, Issue and Quality Feedback fields) and
the SOP-005 build (Supplier approval block, Non Conformance and Quality Action
clusters, Purchase Order warn gate, Quality Action closure rule), alongside the
earlier Work Order BOM behaviour pair and display/naming records. Every custom
field ships as a fixture under module "ISO Compliance" and is reversible by
deletion. Remaining proposals: Asset identification, Quality Meeting, Quality
Feedback summary/status, and Employee rows in the table below.

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

### ~~1. Supplier — approval status~~ — APPLIED 2026-09-05

Applied as part of the SOP-005 build, extended with `custom_rating` (stars),
`custom_score` (%), `custom_category` and `custom_qualification_method` from
the register-column list below. See the Approved and applied table.

### 2. Register columns awaiting fields (2026-08-07 register-format alignment)

The printed registers now follow the column layout of the source register files.
Where a source column has no ERPNext field, the print shows the column **blank**
(the heading is there, the cells are empty) until the field below exists. Each
field is additive, ships as a fixture, and its only purpose is to let the named
register column carry live data. Approving a row here and installing the fixture
makes the corresponding blank column fill in; nothing else changes.

| Target DocType | Fieldname | Type | Register column it fills |
| --- | --- | --- | --- |
| Asset | `custom_make` | Data | REG-011 "Make" / REG-020 "Make / Manufacturer" |
| Asset | `custom_model` | Data | REG-020 "Model" |
| Asset | `custom_serial_no` | Data | REG-011 / REG-020 "Serial No." |
| Asset | `custom_range` | Data | REG-011 "Range" |
| Asset | `custom_least_count` | Data | REG-011 "Least Count (mm)" |
| Asset | `custom_critical_equipment` | Check | REG-020 "Critical Equipment (Y/N)" |
| Quality Meeting | `custom_meeting_date` | Date | REG-019 "Meeting Date" (today: creation date) |
| Quality Meeting | `custom_review_period` | Data | REG-019 "Review Period" |
| Quality Meeting | `custom_chairperson` | Data | REG-019 "Chairperson" |
| Quality Feedback | `custom_summary` | Small Text | REG-025 "Feedback Summary" |
| Quality Feedback | `custom_feedback_status` | Select (Open / Closed) | REG-025 "Status" |
| Employee | `custom_roles_responsibilities` | Small Text | REG-013 "Roles & Responsibilities" |
| Employee | `custom_authority` | Small Text | REG-013 "Authority" |

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
| 2026-09-05 | Supplier | `custom_approval_status`, `custom_category`, `custom_rating`, `custom_score`, `custom_approved_on`, `custom_approved_by`, `custom_reapproval_due`, `custom_qualification_method` (+ section/column breaks) | Custom Fields | The QMS approval block written by submitted FRM-005 Supplier Evaluations; REG-007 reads these. Requested by the developer. | yes |
| 2026-09-05 | Supplier | `search_fields` = approval status, category | Property Setter (display) | Every supplier dropdown shows approval standing under the name. Requested by the developer. | yes |
| 2026-09-05 | Non Conformance | 13 `custom_*` fields (source, QI link, item, batch, qty, conditional PR/WO/DN links, supplier, disposition per SOP-013, re-inspection, approved by, closure date) | Custom Fields | Makes FRM-020 a product NCR and fills REG-009's columns; reference links appear conditionally on the source. Requested by the developer. | yes |
| 2026-09-05 | Non Conformance | `procedure` no longer mandatory | Property Setter (requirement relaxed) | Stock ERPNext assumes NCs come from audits of a Quality Procedure; most here come from inspections. Deleting the setter restores the requirement. Requested by the developer. | yes |
| 2026-09-05 | Quality Action | 11 `custom_*` fields (source per SOP-014, NC link, supplier, related ref, RCA method, root cause, target/completion dates, effectiveness verified/by/date) | Custom Fields | Makes FRM-021 the CAR and fills REG-018's columns. Requested by the developer. | yes |
| 2026-09-05 | Quality Action | `validate` hook | doc_events (behaviour) | SOP-014's closure rule: status cannot be Completed while effectiveness verification is Pending; completion/verification dates auto-stamp. Requested by the developer. | code (hooks.py) |
| 2026-09-05 | Purchase Order | `before_submit` hook | doc_events (behaviour, warn-first) | SOP-005's approval check: non-Approved suppliers warn, Suspended suppliers block. `SUPPLIER_GATE` in overrides/purchase_order.py flips to "block". Requested by the developer. | code (hooks.py) |
| 2026-09-05 | Supplier / Purchase Order / Quality Inspection | form scripts | doctype_js (display only) | Approval banner + Create → Supplier Evaluation on Supplier; standing banner on Purchase Order; Create → Non Conformance (pre-filled, incl. failed readings) on rejected Quality Inspections. Requested by the developer. | code (hooks.py) |
| 2026-09-05 | Terms and Conditions | "Purchase Quality Requirements" record | record, not schema | The nine supplier quality requirements (F-PUR-02 Section C), selectable on any Purchase Order. Created by the ensure hook. | via hook |
| 2026-09-05 | Notification | "Supplier Evaluation Due" record | record, not schema | Bell notification to Purchase Manager and Quality Manager when an FRM-005 evaluation is drafted (the daily scheduler drafts one when a supplier's re-approval date arrives). | via hook |
| 2026-09-04 | Quality Feedback | `custom_mode`, `custom_feedback_type`, `custom_action_required` | Custom Fields, Select (all optional) | Mode (Email/Phone/Survey/Verbal), Type (Positive/Suggestion/Complaint) and Action Required (Yes/No) — fills three REG-025 columns; the doctype also serves internal and production feedback via document_type User. Promoted from the pending proposal. Requested by the developer. | yes |
| 2026-09-04 | Sales Order | form script: Create → Customer Feedback button | doctype_js (display only) | Opens a new Quality Feedback pre-filled with the customer. Requested by the developer. | code (hooks.py) |
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
