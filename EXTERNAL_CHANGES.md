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

## Status: no external changes made

No Custom Fields, Property Setters or other modifications have been applied to any
DocType outside this app.

## Proposed — awaiting approval

Two registers in REG-001 have no data source in ERPNext because the fields they
depend on do not exist. Neither proposal changes existing behaviour: both are
additive Custom Fields shipped as fixtures, and removing them leaves ERPNext exactly
as it is today.

### 1. Asset — calibration control (REG-011, SOP-017, FRM-025, ISO 9001 clause 7.1.5)

All 33 Assets on the site are in the `Measuring Instruments` category, but `Asset`
carries **zero** custom fields and the table has no calibration column — only
`next_depreciation_date` and `maintenance_required`. There is nowhere to record when
an instrument was last calibrated or when it is next due, so calibration status
cannot be reported, and clause 7.1.5 cannot be evidenced from the ERP at all.

| Fieldname | Type | Label | Purpose |
| --- | --- | --- | --- |
| `custom_calibration_required` | Check | Calibration Required | Distinguishes instruments under calibration control from other assets |
| `custom_calibration_frequency_months` | Int | Calibration Frequency (Months) | Drives the due-date calculation |
| `custom_last_calibration_date` | Date | Last Calibration Date | Evidence of the last calibration performed |
| `custom_next_calibration_date` | Date | Next Calibration Due | Stored rather than computed so it is filterable and reportable |
| `custom_calibration_agency` | Link (Supplier) | Calibration Agency | External calibration provider, traceable to the supplier record |
| `custom_calibration_certificate` | Attach | Calibration Certificate | The certificate itself, which is the auditable record |

Note: 31 of the 33 Assets are in Draft and 2 are Cancelled — none are submitted. The
instrument register is not live regardless of these fields, which is a process matter
rather than a schema one.

### 2. Supplier — approval status (REG-007, SOP-005, ISO 9001 clause 8.4)

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
| —    | —              | —              | —    | —      | —       |
