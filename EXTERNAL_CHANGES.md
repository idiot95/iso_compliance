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
clusters, Purchase Order warn gate; the Quality Action closure rule was built
and then reverted at the developer's direction), alongside the
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

### 3. Drawing-based inspection templates — Phase A — APPROVED 2026-10-12, applied on the local site

Approved by the developer 2026-10-12. Applied on `frontend`; reaches production with the next deploy. See the Approved and applied table.

Spec: `hcc_erp_edits/docs/qi-build/SPEC.md` v2, §3.2 and §4.2. Turns a Quality
Inspection Template into one drawing revision with ballooned dimensions, tests
and visual checks. **Legacy templates are untouched**: everything below only
acts on a template that has at least one row with `custom_row_type` set, and
none of the 28 existing templates has one. All fields are additive, ship as
fixtures under module "ISO Compliance", and deleting them restores ERPNext
exactly.

**Quality Inspection Template** — custom fields

| Fieldname | Type | Purpose |
| --- | --- | --- |
| `custom_drawing_section` | Section Break "Drawing" | groups the fields below |
| `custom_item` | Link Item | the item whose BOMs/attachments supply the drawing |
| `custom_used_by` | HTML | lists the BOMs and Items pointing at this template (read from their native fields; nothing stored) |
| `custom_drawing` | Attach | the drawing, copied as a private File on the template so deleting the BOM's copy doesn't break it |
| `custom_drawing_hash` | Data, hidden | hash of the drawing; page images are rebuilt only when it changes |
| `custom_drawing_pages` | Long Text, hidden | URLs of page PNGs used by the printed inspection record |
| `custom_drawing_source` | Select: Customer / In-house / None | |
| `custom_customer` | Link Customer | shown when source = Customer |
| `custom_drawing_no`, `custom_drawing_revision` | Data | |
| `custom_general_tolerance` | Select: None / ISO 2768-f / -m / -c / -v | title-block general tolerance |
| `custom_general_geometric` | Select: None / H / K / L | ISO 2768-2 |
| `custom_product_wi` | Link Controlled Document | product work instruction (WI-004…007) |
| `custom_locked` | Check, read-only | set when the first inspection on the template is submitted (Phase B) |
| `custom_superseded_by` | Link Quality Inspection Template, read-only | set by New Revision |

**Item Quality Inspection Parameter** (template rows) — custom fields

| Fieldname | Type | Purpose |
| --- | --- | --- |
| `custom_row_type` | Select: Dimension / Test / Visual | marks a drawing row; its presence makes the template a drawing template |
| `custom_balloon_no` | Data | the row's key (1, 2… / T1… / V1…), unique per template |
| `custom_spec_text` | Data | the spec exactly as printed on the drawing |
| `custom_tolerance_type` | Select (11 types, SPEC §4.1) | |
| `custom_nominal`, `custom_upper_dev`, `custom_lower_dev`, `custom_tol`, `custom_bonus_tol` | Float | tolerance inputs; `min_value`/`max_value` (native) are computed from them |
| `custom_fit_class` | Data | ISO 286 class, e.g. H11 |
| `custom_gdt_symbol` | Select (14 symbols) | |
| `custom_datums` | Data | |
| `custom_unit` | Link UOM (was Data; changed 2026-10-13, see the Approved table) | |
| `custom_class` | Select: CTQ / Major / Minor | |
| `custom_stage_incoming`, `custom_stage_in_process`, `custom_stage_final`, `custom_stage_fai`, `custom_stage_type_test` | Check | stages that load the row |
| `custom_frequency` | Select: Every lot / First article only / Every N lots / Every N months | |
| `custom_frequency_n` | Int | |
| `custom_sampling` | Select: Lot sample / Fixed number | |
| `custom_fixed_count` | Int | |
| `custom_test_method` | Link Test Method (new iso doctype) | Test rows |
| `custom_conditions` | Code (JSON) | per-part overrides of the method's set values |
| ~~`custom_instrument_item`~~ → `custom_instruments` | Small Text (Asset names) | replaced 2026-10-13: the measuring-instrument Assets the inspector may choose from; see the Approved table |
| `custom_position` | Data (JSON) | the balloon's box on the drawing |

**Behaviour and records**

| Target | Change | Type |
| --- | --- | --- |
| Quality Inspection Template | `validate`: on drawing templates only, compute min/max from the tolerance type, require unique balloons, a stage per row and a Test Method on Test rows; once `custom_locked`, refuse changes to drawing, balloons, limits and stages | doc_events |
| Quality Inspection Template | template builder: drawing picker, pdf.js canvas, balloon popup, "Tag Items / BOMs", New Revision | doctype_js (display + whitelisted calls) |
| BOM / Item | `quality_inspection_template` (native field) written by the explicit "Tag Items / BOMs" action only. It never overwrites a different template without the user confirming the listed conflicts, and it leaves a Comment on each record (old → new). Item is tagged only when all its active BOMs share the template or it has no BOM, so group templates from the SOP-006 backfill survive. | data on a core field |
| BOM | `quality_inspection_template` allow_on_submit = 1 | Property Setter |

### 4. Drawing-based inspection — Phase B, the inspector — APPROVED 2026-10-12, applied on the local site

Approved by the developer 2026-10-12. Applied on `frontend` (fields, role, permissions by patch `qi_inspector_role`, page `inspect`); reaches production with the next deploy.

Spec: `hcc_erp_edits/docs/qi-build/SPEC.md` v2, §3.2–3.4, §4.3–4.5. Inspectors
record measurements against a drawing template on a phone or tablet. Each value
saves on its own, and the inspection gets a disposition.

**Existing inspections are untouched.** Every hook below starts with the legacy
guard. It acts only on a *draft* inspection whose template has drawing rows. The
~1,300 existing inspections and every inspection on the 28 existing templates
behave exactly as today, and a regression test proves it before anything is
called done.

**Quality Inspection** — custom fields

| Fieldname | Type | Purpose |
| --- | --- | --- |
| `custom_inspection_section` | Section Break "Drawing inspection" | groups the fields below; collapsed when empty |
| `custom_stage` | Select: Incoming / In Process / Final / FAI / Type Test | which template rows load; maps to `inspection_type` (Final → Outgoing) |
| `custom_lot_qty` | Float | the lot the sample is drawn from |
| `custom_work_order` | Link Work Order, read-only | the lot's work order (final inspection) |
| `custom_customer` | Link Customer, read-only | from the work order's Sales Order |
| `custom_drawing_no`, `custom_drawing_revision` | Data, read-only | snapshot of the template at inspection time |
| `custom_drawing` | Attach, read-only | snapshot of the drawing file |
| `custom_disposition` | Select: Accepted / Accept under Concession / Rework / Rejected | |
| `custom_concession_no` | Data | shown for a concession |
| `custom_non_conformance` | Link Non Conformance | |
| `custom_conditions` | Table → QI Condition (new iso child doctype) | test conditions: set value vs actual |
| `custom_work_instructions` | Table → QI Work Instruction (new iso child doctype), read-only | WI number and revision in force when inspected |
| `custom_measurements_html` | HTML | shows the measured values (stored in the new QI Measurement doctype) |
| `custom_created_entry` | Data, hidden, no_copy | the draft Manufacture Stock Entry this inspection created, so it can be deleted with it |

**Quality Inspection Reading** — custom fields

`custom_row_type`, `custom_balloon_no`, `custom_class`, `custom_spec_text`,
`custom_tolerance_type`, `custom_unit`, `custom_test_method` (Link Test Method),
`custom_sample_count` (Int: how many are required), `custom_instrument` (Link
Asset), `custom_cal_due` (Date), `custom_cal_cert` (Data), `custom_n` (Int: how many
measured), `custom_obs_min`, `custom_obs_max`, `custom_mean` (Float),
`custom_out_of_spec` (Int). All read-only snapshots and summaries. The native
reading fields keep their meaning; `reading_1..10` hold the first ten values for
display.

**Behaviour**

| Target | Change | Type |
| --- | --- | --- |
| Quality Inspection | `before_validate`: build readings from the template rows due at this stage and lot. Copy the balloon and tolerance fields. Summarise the measurements. Set each drawing row's verdict ourselves (`reading.manual_inspection = 1`, so ERPNext skips it). Map disposition to status: concession → Accepted; Rework/Rejected → Rejected. | doc_events |
| Quality Inspection | `validate`: undo ERPNext's Job Card quirk, which overwrites limits from the Item's template by parameter name, by restoring them from the inspection's own template, matched by balloon. Refuse "Accepted" while a row is out of spec. Warn on test conditions outside tolerance and on overdue calibration (Warn/Block per Inspection Settings; no calibration record never blocks). | doc_events |
| Quality Inspection | `before_submit`: CTQ rows need every required sample. A concession shows an orange warning listing the failed rows and **never blocks** (developer's decision). `on_submit`: lock the template; refresh the lot's draft Manufacture entry. `on_trash`/`on_cancel`: delete the draft Manufacture entry this inspection created, if still draft. | doc_events |
| Quality Inspection | form script: "Open inspector" button, measurements view. Added as a second file beside the existing `quality_inspection.js`; the hooks.py value becomes a list. | doctype_js |
| Quality Inspection | "Create → Non Conformance" prefill (existing SOP-005/006 script) lists failed readings by balloon, not just by parameter | change to existing iso script |
| Work Order | "Final inspection" button and dialog: lot qty, sample size; creates a draft Manufacture Stock Entry for the lot and the inspection, then opens the inspector | doctype_js |
| Purchase Receipt | "Inspect" button per row on a drawing template (legacy templates keep ERPNext's own button) | doctype_js (added to the existing list) |
| Job Card | "Inspect" button on a drawing template | doctype_js |
| Stock Entry | draft Manufacture entries created by "Final inspection" (records, not schema) | data |
| Role | "Quality Inspector" (new role, desk access) | record, via patch |
| Custom DocPerm | Quality Inspection: Quality Inspector and **Stock User** get read/create/write/submit. Read for both on Quality Inspection Template, Test Method, Inspection Settings, QI Measurement, Asset, Asset Maintenance, Asset Maintenance Task. Applied with `frappe.permissions.add_permission`, which copies the standard rows first, so **Quality Manager keeps every right it has today**; the patch asserts it. | permissions, via patch |
| Page | `inspect` (new iso page, `/app/inspect/<inspection>`): the mobile/tablet inspector screen. Roles: Quality Inspector, Quality Manager, Stock User, System Manager. | new page (iso) |

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
| 2026-10-14 | Purchase Receipt / Stock Entry / Quality Inspection / Item / Item Group / Warehouse / Stock Settings | SOP-006 post first, inspect after (`overrides/inspection_flow.py`, patch `sop_006_post_first`). New warehouse **Inspection Required** per company. Item Group `custom_qc_required` (inherited; seeded on Adhesives & Resins, Carbon Block, Chemicals, Copper Wire, Finished Goods, Raw Insulation Sheet, Rubberized Insulation Sheet, Sheet Metal, Sleeving, Slipring Unit, Tamping Powder, Terminal, Tubes & Rods); each stock item's *Inspection Required before Purchase* follows it (916 on, 1 off). Stock Settings *Allow to make Quality Inspection after Purchase / Delivery* on. Receipt: receiving checks (right quantity, right material, visual OK) required to post; QC rows post into Inspection Required (`custom_release_warehouse` keeps the intended one) and posting flags the receipt (`custom_inspection_pending`) so hcc's Assignment Rule *Incoming inspection owed* assigns it to the Engineer (My Work); no inspection opens by itself, the engineer presses **Inspect** on the receipt. Finish (Manufacture): the finished item of a QC group goes to Inspection Required (draft batch bundle moved with it; the BOM's *Quality Inspection Required* no longer demands an inspection first), by-products keep their target; the entry is flagged and assigned the same way (*Final inspection owed*), Inspect on the entry or *Final inspection* on the Work Order. Inspection: `custom_accepted_qty` / `custom_rejected_qty`; submitting drafts one Material Transfer (accepted → kept warehouse, rejected → Rejected) for Stores to post, linked both ways (`custom_transfer_entry`, Stock Entry `custom_quality_inspection`); when nothing on the document still waits the flag clears and the assignment closes. Nothing else may take stock out of Inspection Required (Stock Entry, Delivery Note). Work Order shows what waits and starts the final inspection (Finish is the way in). Items without batches get their item code as an Item Barcode (118); labels print it. Labels print on A4 (8) or a thermal roll (100×50, 75×50, 50×25 mm); new page **Stock Labels**: Scan (what it is, where the books have it, where it belongs, inspection state) and Print (labels for stock on the shelves). | Custom Fields + Warehouse + Stock Settings + data + code | The developer, 2026-10-14: Stores lands and receives, Engineering (ERPNext role Quality Manager, designation Engineer) inspects, Stores racks by stock entry, rejected only to Rejected; the same hold for finished production. | yes (fields) / patch (data) |
| 2026-10-14 | Delivery Note (print formats) | EN 10204:2004 inspection documents as three separate print formats sharing one layout (`templates/includes/en10204.html`, data `qi.certificates.en10204`, jinja method): new **Declaration of Compliance 2.1** (FRM-040: statement only), new **Test Report 2.2** (FRM-041: statement + results of non-specific inspection, from the delivered batches or the product's latest accepted inspection), and **Material Test Certificate 3.1** reworked (name kept; title "Inspection certificate 3.1": results of the delivered batches, signed by the independent inspection representative; material groups keep the supplier trace and properties). Company logo embedded. `certificate_readiness` adds `d21` and `d22`; `mtc` is now applicable to every delivery, with `default` true only for groups that issue a 3.1. `coc_row_aggregate` rows carry `unit`. 3.2 is not offered. Printed titles (developer, 2026-10-14): "EN 10204:2004" above "2.1 Certificate of Conformity", "2.2 Inspection Report", "3.1 Detailed Inspection Report" (print format names unchanged). Reference labels in the standard's wording (title, "Inspection document type x according to EN 10204:2004", purchaser, purchaser's order no. / date, delivery note no. / date, document no. / date of issue, manufacturer with address). The plan form no longer offers the Material (3.1) row type (none existed). | Print Format + code | The developer, 2026-10-14: 2.1, 2.2 and 3.1 all selectable in the dispatch email. FRM-040 / FRM-041 to be entered in REG-001. | yes (print formats are standard, module ISO Compliance) |
| 2026-10-13 | Quality Inspection | A blank new inspection opens a start dialog: stage (Incoming / In process / Final), then the Purchase Receipt row, Job Card and checkpoint, or Work Order with lot and sample, and a preview of the plan that will load (`qi.inspection.plan_preview`, drawing thumbnail). "Start inspection" uses the existing start functions; "Old-format form" closes the dialog and leaves ERPNext's form. A form opened with an item or reference already filled (buttons elsewhere) is left alone. Desktop (≥ 992 px), drafts on a new-format plan: the form opens on the drawing and an entry grid (one row per characteristic, one box per sample) that saves each value as typed through `qi.inspector.save_measurement`; out-of-spec values turn red, Enter moves on, the focused characteristic is shown on the drawing. Save and Submit are ERPNext's own. A drawing inspection's form shows only the entry screen and the steps 2 · Disposition (disposition, concession, Non Conformance) and 3 · Sign-off (inspected / verified by, remarks) plus Print every drawing sheet; every other field is hidden client-side, and "Show all fields" in the menu brings them back. The grid scales: one fixed column per sample, sticky header and first columns, filters (All / To do / Out of spec / CTQ), search, Enter and ↑ ↓ keys, the drawing can be hidden; submitted inspections show it read only. | doctype_js (display + whitelisted calls) | The developer, 2026-10-13: a new inspection should start from what is inspected and show the drawing with entry fields on desktop. | code |
| 2026-10-13 | BOM / Item / Item Quality Inspection Parameter / Quality Inspection Template | BOM and Item: the Inspection Plan tab is the one place a plan is set: the plan in use, "Use an existing plan" (the item's plans, an earlier one included, or search all) and "Build a new plan" (drawings previewed before choosing; built from a BOM, that BOM uses it). ERPNext's `quality_inspection_template` field is hidden there (the panel sets it, `qi.template.use_plan`, with a comment on the record); the "Create › Inspection template" button is removed. Plan rows: new `custom_work_instruction` (Link Controlled Document): an Operational row is chosen through its work instruction, then its Test Method. `custom_instruments` lines may carry a stage (`Incoming: ASSET`); bare lines apply at every stage, so existing rows are unchanged. Plan form labels: section "Item and drawing", "Drawing file", "Drawing number", "General tolerance, linear and angular (ISO 2768-1)", "General tolerance, geometric (ISO 2768-2)". | doctype_js + Custom Field + labels | The developer, 2026-10-13: one way to give a BOM a plan (existing or new), drawings seen before choosing from BOM and Item too, formal names, operational checks through the work instruction, instruments per inspection stage. | yes |
| 2026-10-13 | Quality Inspection | `custom_print_all_sheets` (Check "Print every drawing sheet", Print Settings section, allow on submit). Inspection record print: the whole drawing with every number green (conforms) / red (out of spec) / grey (not fully measured), a key and a count summary; only the sheets that carry numbers unless ticked. Drawing page images are now made on the server (pypdfium2, already an ERPNext dependency) when the plan is saved or a print finds them missing. "Print inspection record" button on drawing inspections; the doctype's default print format is not changed. | Custom Field + print template | The developer, 2026-10-13: print the readings with the whole drawing, non-conforming numbers marked; extra sheets as a tick under the inspection's print settings. | yes |
| 2026-10-13 | Quality Inspection Template / Quality Inspection | New format only. Plan form: the parameter grid, `custom_drawing`, `custom_locked`, `custom_superseded_by`, `custom_used_by` and the Characteristics heading are hidden (the builder shows all of them); a plan may be saved empty and needs neither Item nor drawing (`qi.template.validate` no longer requires rows). A template with rows but no Item and no drawing rows opens archived: read only, its checks listed, a button to start the new-format plan. Row numbers are one running number for every row type (older T1/V1/M1 kept); `custom_balloon_no` labelled "No." on both child tables. Inspection: `qi.inspection.resolve_template` prefers a new-format plan anywhere in BOM → Item → Item Group, then a new-format plan made for the item but not tagged; a **new** inspection that arrives with an old plan switches to that new plan (`before_validate`). Drawing inspections only: Inspection Type, Manual Inspection, Readings grid, Serial No (when empty), Description (from Ref Doc) hidden; item, BOM, plan, reference, stage, work order, customer, drawing snapshot, check point read only once saved; the plan in use is named at the top. | doctype_js (display) + app validation + Custom Field label | The developer, 2026-10-13: the old fields hid the new form and duplicated it (type = stage, grid = measurements, manual = disposition), and it was unclear which plan an inspection would load. Nothing is deleted or migrated: the 28 old templates and their inspections keep working and stay readable; hiding is client-side. | label only |
| 2026-10-13 | UOM | 23 records: mm, µm, °, N, kV, V, mV, A, Ω, mΩ, MΩ, µΩ·m, MPa, g/cm³, MS/m, % IACS, HRB, HRC, Shore A, Shore D, kg, g, % | record, not schema | Units as drawings and certificates print them; template rows and Test Methods now link to UOM, and ERPNext ships only long names (Newton, Micrometer, Percent…). Created by `qi.setup.ensure_uoms` (from `ensure_qi_setup`, after_migrate) only when no UOM of that name exists; matched by name, never renamed or edited afterwards, so a unit already on the site is left as it is. Follows the developer's request of 2026-10-13 that the row unit come from the unit table. | no (after_migrate hook) |
| 2026-10-13 | Item Quality Inspection Parameter | `custom_unit` Data → **Link UOM**; `custom_instrument_item` (Link Item) **replaced by** `custom_instruments` (Small Text: measuring-instrument Asset names, one per line, from Asset Category "Measuring Instruments") | Custom Fields | The developer, 2026-10-13: unit picked from the unit table; instruments multi-selected from the measuring instruments (a whole instrument type at once), and the inspector chooses the one in hand from that list. Neither field has reached production, so the fixture creates them in their final form. | yes |
| 2026-10-13 | Item Group | `custom_issue_mtc` (Check, inherited down the tree); set on Carbon Block, Copper Wire, Chemicals, Pipe Fittings, Terminal, Sheet Metal, Tamping Powder, Tubes & Rods, Raw Insulation Sheet, Machinery Tools, Machined FG Parts, Rubberized Insulation Sheet | Custom Field + data (patch `qi_issue_mtc_groups`, once) | QI Phase C2: deliveries of these groups carry an EN 10204 3.1 Material Test Certificate (print format "Material Test Certificate 3.1", Delivery Note), traced batch → receipt → supplier certificate, or through the Manufacture entry to raw-material receipts. Missing certificate or properties warn and never block, at dispatch and at goods-in. Developer, 2026-10-13. | yes |
| 2026-10-13 | Quality Inspection / Item Quality Inspection Parameter | `custom_check_point` (First-off / Patrol / Last-off), `custom_supplier_cert` (Attach, from the receipt); row `custom_in_process_at` (Every check / First-off only / First-off and last-off); row type "Material" added to `custom_row_type` | Custom Fields | QI Phase E: supplier 3.1 values read at goods-in (Material rows, the PR's MTC linked); in-process first-off / patrol / last-off on Job Cards, several inspections per Job Card. Built on the developer's go-ahead for Phase E, 2026-10-13. | yes |
| 2026-10-13 | Stock Entry (draft, Manufacture) | `allow_zero_valuation_rate` set on the rows of the lot entry Final inspection drafts | data on a core field | Stock carries no value on this site (accounting in Tally, every valuation rate zero); without it ERPNext refuses the entry and final inspection cannot start. Developer, 2026-10-13. | code |
| 2026-10-13 | Quality Inspection Template | parameter table not mandatory (`reqd` 0); `qi.template.validate` required rows on any template without an Item (dropped 2026-10-13: plans start empty) | Property Setter (requirement moved into app validation) | A drawing template is saved with its drawing before its rows exist (they come from the balloons); without this the BOM button and the cascade could not create one. Old-style templates keep the rule. Found in the developer's test, 2026-10-13. | yes |
| 2026-10-13 | Quality Inspection Template | `custom_bom` (Link BOM, filtered to the item), `custom_drawing_file` (Select of that BOM's drawings), `custom_rows_section` (Section Break "Characteristics") | Custom Fields | Item → BOM → drawing cascade on the template, and the parameter table in its own full-width section. Requested by the developer 2026-10-13. | yes |
| 2026-10-13 | Item Quality Inspection Parameter | grid columns: Balloon, Parameter, As printed, Tolerance type, Min, Max, Value, Class (`numeric` off the grid; column widths) | Property Setters + custom field list-view flags | The template's rows table shows tolerances at a glance. Requested by the developer 2026-10-13. | yes |
| 2026-10-13 | BOM | "Inspection Plan" tab (`custom_inspection_plan_tab`, `custom_inspection_plan_html`); `inspection_required` and `quality_inspection_template` moved into it (field_order); `quality_inspection_template` no longer hidden behind `inspection_required` (depends_on cleared) | Custom Fields + Property Setters | One place on the BOM for its inspection: the requirement, the tagged template, and a summary of the template's rows with tolerances. Requested by the developer 2026-10-13. | yes |
| 2026-10-13 | Item | `custom_inspection_plan_html` in the existing Quality tab | Custom Field (HTML) | The same template summary on the Item. Requested by the developer 2026-10-13. | yes |
| 2026-10-12 | BOM / Item / Quality Inspection Template (list) | Create › Inspection template button on BOM and Item (replaced 2026-10-13 by the Inspection Plan panel); "New from drawing" button on the template list | doctype_js / doctype_list_js (display + whitelisted calls) | Entry points to the drawing template builder (§5 of the QI build): opens the drawing template already in use, or creates one for the item with the chosen BOM drawing attached. Shown to Quality Manager / System Manager only. Approved by the developer 2026-10-12. | code (hooks.py) |
| 2026-10-12 | Quality Inspection / Quality Inspection Reading | 20 + 16 `custom_*` fields (stage, lot, work order, customer, drawing snapshot, disposition, concession, NC link, conditions, WIs, measurements; reading balloon/class/tolerance/test/instrument/summary) | Custom Fields | Drawing-based inspection (QI SPEC v2 §3.2). Requested by the developer. | yes |
| 2026-10-12 | Quality Inspection | `before_validate`, `validate`, `before_submit`, `on_submit`, `on_cancel`, `on_trash` hooks | doc_events | Readings from the drawing template by stage/frequency, own verdict per row, disposition → status, Job Card limit quirk undone by balloon, CTQ completeness, concession warning (never blocks), template lock, the lot's draft Manufacture entry kept with its inspection. Act only on drafts on drawing templates: verified identical with and without the hooks on existing drafts. Requested by the developer. | code (hooks.py) |
| 2026-10-12 | Quality Inspection / Work Order / Job Card / Purchase Receipt | form scripts: Open inspector, Final inspection, Inspect buttons; NC prefill names the balloon | doctype_js | Entry points to the inspector screen, shown only where a drawing template applies. Requested by the developer. | code (hooks.py) |
| 2026-10-12 | Role / Custom DocPerm | "Quality Inspector" role; Quality Inspector and Stock User: create/write/submit on Quality Inspection, read on templates, Test Method, settings, measurements, Asset, Asset Maintenance | permissions | Inspectors and stores record inspections (developer's decision: Stock User may submit). Applied with add_permission; Quality Manager's rights verified unchanged. | via patch |
| 2026-10-12 | Quality Inspection Template / Item Quality Inspection Parameter | 16 + 31 `custom_*` fields (drawing, tolerance, class, stages, frequency, sampling, test method, position) | Custom Fields | Drawing-based inspection templates (QI SPEC v2 §3.2): one template = one drawing revision, rows keyed by balloon, limits computed from the tolerance as printed. Act only on templates with drawing rows; the 28 existing templates are untouched. Requested by the developer. | yes |
| 2026-10-12 | Quality Inspection Template | `validate` hook + form script (template builder) | doc_events + doctype_js | Limits from tolerances, unique balloons, stage/test-method checks, lock after first submitted inspection; drawing picker, pdf.js canvas, balloon popup, Tag Items / BOMs, New Revision. Legacy templates pass through unchanged (verified). Requested by the developer. | code (hooks.py) |
| 2026-10-12 | BOM / Item | `quality_inspection_template` written by the explicit Tag action only; asks before replacing another template; Comment on each record; Item tagged only when all its active BOMs share the template | data on a core field | So inspections started from a BOM load its drawing template without silently replacing item-group templates from the SOP-006 backfill. Requested by the developer. | no (action) |
| 2026-10-12 | BOM | `quality_inspection_template` allow_on_submit | Property Setter | Re-tag a submitted BOM by hand. Requested by the developer. | yes |
| 2026-10-06 | Purchase Receipt / Delivery Note | form scripts | doctype_js (display only) | SOP-006 step 3 material identification labels, eight to an A4 sheet: Print > Material Labels on a submitted receipt (item, batch as Code128, supplier, date of goods in) and Print > Dispatch Labels on a submitted delivery note (item, batch as Code128, customer, their PO, the sales order). The label count is typed per batch, never derived from the received quantity. Reads only; writes nothing. Requested by the developer. | code (hooks.py) |
| 2026-10-09 | Purchase Order | `custom_supplier_override`, `custom_supplier_override_reason`, `custom_supplier_override_by` | Custom Fields (Check, Small Text, Link User; no_copy) | The urgent-order override for SOP-005's lock: ticked with a reason, submitted only by a Purchase Manager or Quality Manager, who is stamped on the order. Shown only when the supplier isn't Approved. Requested by the developer. | yes |
| 2026-10-09 | Purchase Order | `before_submit` hook now **blocks** | doc_events (behaviour) | Was warn-first. Now only an Approved supplier's order submits; others need the override above; Suspended always blocks. Requested by the developer. | code (hooks.py) |
| 2026-10-09 | Notification / Workflow | five "Techno-Commercial Review: …" notifications and the "Techno-Commercial Review" workflow REMOVED | records deleted by patch `retire_tcr_review_chain` | FRM-036 became one form: Sales names a Technical, Costing and Commercial reviewer, who are assigned with ERPNext's own assignment (ToDo, bell, email) and given edit access by document share. The sequential chain and its stage notifications are no longer needed. The reviewer roles are left in place. Requested by the developer. | via patch |
| 2026-10-05 | Quality Inspection Template | "Non-Confirmative Material Report & CAPA" **deleted** | record, not schema | The template was a nonconformance form built out of inspection readings (description, disposition and quantity, all numeric with a zero-width range, so any reading fails). That job belongs to FRM-020 and FRM-021, which hold those as real fields. Referenced by nothing; the patch re-checks all six link fields and declines to delete if anything points at it. The doctype has no disabled flag, so a retired template would otherwise stay in every dropdown. Requested by the developer. | no (patch) |
| 2026-10-05 | Item Group | `custom_mtc_required`, `custom_default_qi_template` | Custom Fields | SOP-006 defines inspection requirements per item group: which groups must arrive with a Material Test Certificate, and the default inspection template for items in the group. Flags are inherited down the group tree. Requested by the developer. | yes |
| 2026-10-05 | Purchase Receipt | `custom_material_test_certificate` | Custom Field, Attach | The MTC is a supplier document that arrives with the consignment, so it is held on the receipt rather than restated as a form. Fills REG-015's certificate column. Requested by the developer. | yes |
| 2026-10-05 | Purchase Receipt | `custom_recevied_by` **adopted** | Custom Field, ownership only | The field was created by hand with `module` unset, so it belonged to no app, shipped in no fixture and would never reach production -- while holding the only record of who received goods (415 of 415 receipts). Adopted into module "ISO Compliance" so it ships. Fieldname typo kept deliberately: renaming would orphan 415 rows. Requested by the developer. | yes |
| 2026-10-05 | Purchase Receipt | `validate` + `before_submit` hooks | doc_events (behaviour, warn-only) | SOP-006 step 1-2: warn when a consignment whose item group requires an MTC carries no certificate (warn, never block, at the developer's direction), and default the rejected warehouse on any line with a rejected quantity. | code (hooks.py) |
| 2026-10-05 | Batch | `custom_heat_no` | Custom Field, Data | SOP-006 step 3 identifies incoming material by heat or lot number, which the supplier assigns and which ERPNext's `batch_id` does not hold. Fills REG-015's identification column. Requested by the developer. | yes |
| 2026-10-05 | Batch | `supplier` populated from the receipt | doc_events (fills an existing core field) | 355 batches were born from Purchase Receipts and not one recorded its supplier, so no batch could be traced back to who supplied it. Sets the field ERPNext already ships; a patch backfills history. | code (hooks.py) |
| 2026-10-05 | Stock Settings | `action_if_quality_inspection_is_rejected`: Stop -> Warn | one-time patch (value, not schema) | With "Stop" a receipt carrying a rejected inspection cannot be submitted, so in 372 incoming inspections not one was ever recorded as Rejected and SOP-006 step 5 had no executable path. "Warn" lets the receipt post with the rejected quantity segregated, which is what makes a nonconformity record possible at all. Applied once by patch, not by an ensure hook, so the setting stays the site's to change. Requested by the developer. | no (patch) |
| 2026-10-05 | Warehouse | "Rejected - HCCPL" record | record, not schema | SOP-006 step 5 requires rejected material to be segregated from accepted stock; rejections had been going to Goods In Transit, and twice back into Stores. One warehouse serves incoming and production rejections. Created per company by the ensure hook. | via hook |
| 2026-10-05 | Item | `quality_inspection_template` backfilled | data patch (fills an existing core field) | 521 items require inspection at receipt and only 2 named a template, so the inspector chose one by hand each time. Backfilled from each item's own inspection history, falling back to the item group default. Core field, no schema change. | no (patch) |
| 2026-10-05 | Notification | "Incoming Material Rejected" record | record, not schema | SOP-006 step 5 requires rejections to be reported to Purchase. Created by the ensure hook alongside the six the app already ships. | via hook |
| 2026-09-05 | Supplier | `custom_approval_status`, `custom_category`, `custom_rating`, `custom_score`, `custom_approved_on`, `custom_approved_by`, `custom_reapproval_due`, `custom_qualification_method` (+ section/column breaks) | Custom Fields | The QMS approval block written by submitted FRM-005 Supplier Evaluations; REG-007 reads these. Requested by the developer. | yes |
| 2026-09-05 | Supplier | `search_fields` = approval status, category | Property Setter (display) | Every supplier dropdown shows approval standing under the name. Requested by the developer. | yes |
| 2026-09-05 | Non Conformance | 13 `custom_*` fields (source, QI link, item, batch, qty, conditional PR/WO/DN links, supplier, disposition per SOP-013, re-inspection, approved by, closure date) | Custom Fields | Makes FRM-020 a product NCR and fills REG-009's columns; reference links appear conditionally on the source. Requested by the developer. | yes |
| 2026-09-05 | Non Conformance | `procedure` no longer mandatory | Property Setter (requirement relaxed) | Stock ERPNext assumes NCs come from audits of a Quality Procedure; most here come from inspections. Deleting the setter restores the requirement. Requested by the developer. | yes |
| 2026-09-05 | Quality Action | 11 `custom_*` fields (source per SOP-014, NC link, supplier, related ref, RCA method, root cause, target/completion dates, effectiveness verified/by/date) | Custom Fields | Makes FRM-021 the CAR and fills REG-018's columns. Requested by the developer. | yes |
| 2026-09-05 | Quality Action | ~~`validate` hook~~ REVERTED same day | doc_events (behaviour) | The SOP-014 closure rule (no Completed while effectiveness Pending) was built, then removed at the developer's direction: Quality Actions complete normally, and the effectiveness fields are optional record-keeping. | — |
| 2026-09-05 | Purchase Order | `before_submit` hook (made blocking 2026-10-09) | doc_events (behaviour, warn-first) | SOP-005's approval check: non-Approved suppliers warn, Suspended suppliers block. `SUPPLIER_GATE` in overrides/purchase_order.py flips to "block". Requested by the developer. | code (hooks.py) |
| 2026-09-05 | Supplier / Purchase Order / Quality Inspection | form scripts | doctype_js (display only) | Approval banner + Create → Supplier Evaluation on Supplier; standing banner on Purchase Order; Create → Non Conformance (pre-filled, incl. failed readings) on rejected Quality Inspections. Requested by the developer. | code (hooks.py) |
| 2026-09-05 | Terms and Conditions | "Purchase Quality Requirements" record | record, not schema | The nine supplier quality requirements (F-PUR-02 Section C), selectable on any Purchase Order. Created by the ensure hook. | via hook |
| 2026-09-05 | Notification | "Supplier Evaluation Due" record | record, not schema | Bell notification to Purchase Manager and Quality Manager when an FRM-005 evaluation is drafted (the daily scheduler drafts one when a supplier's re-approval date arrives). | via hook |
| 2026-09-04 | Quality Feedback | `custom_mode`, `custom_feedback_type`, `custom_action_required` | Custom Fields, Select (all optional) | Mode (Email/Phone/Survey/Verbal), Type (Positive/Suggestion/Complaint) and Action Required (Yes/No) — fills three REG-025 columns; the doctype also serves internal and production feedback via document_type User. Promoted from the pending proposal. Requested by the developer. | yes |
| 2026-09-04 | Sales Order | form script: Create → Customer Feedback button | doctype_js (display only) | Opens a new Quality Feedback pre-filled with the customer. Requested by the developer. | code (hooks.py) |
| 2026-09-04 | Issue | `custom_sales_order` | Custom Field, Link (Sales Order) | A customer complaint traced to the order it concerns; also the target of the Sales Order form's Create → Customer Complaint button. Requested by the developer. | yes |
| 2026-09-04 | Issue | `custom_root_cause` | Custom Field, Small Text | Fills REG-008's "Investigation / Root Cause" column (promoted from the pending proposal). Requested by the developer. | yes |
| 2026-09-04 | Sales Order | form script: Create → Customer Complaint button | doctype_js (display only) | Opens a new Issue pre-filled with the order and customer — the QMS's complaint entry point (FRM-028). Shown on drafts and submitted orders. Requested by the developer. | code (hooks.py) |
| 2026-09-04 | Notification | ~~five "Techno-Commercial Review: …" records~~ removed 2026-10-09 | Notification records (record, not schema) | In-app bell notifications as the review changes hands: each stage pings its reviewer role, send-back and approval ping the review's creator. Created by the ensure hook; deleting the records reverts the site untouched. Requested by the developer. | via hook |
| 2026-09-04 | Sales Order | `before_submit` hook | doc_events (behaviour) | SOP-004's contract-review gate: an order of ₹ 5,00,000+ cannot be submitted without an approved Techno-Commercial Review (FRM-036) of the required tier concluding Accept; an in-flight review of any order must finish first; a review concluding Reject always blocks. `TCR_ENFORCEMENT` in overrides/sales_order.py flips to "warn" for an advisory-only rollout. Requested by the developer. | code (hooks.py) |
| 2026-09-04 | Sales Order | form script (button + banner) | doctype_js (display only) | Adds Create → Techno-Commercial Review, opening FRM-036 pre-filled from the order, and an intro banner when the slabs demand a review. No behaviour change; the gate is server-side. Requested by the developer. | code (hooks.py) |
| 2026-09-02 | Sales Order | `get_work_order_items` override | override_whitelisted_methods (wrapper) | The make-Work-Order and raw-material-request dialogs display and submit the row's chosen BOM instead of the item default. Calls the core function first; only BOM values are corrected. Requested by the developer. | code (hooks.py) |
| 2026-09-02 | Work Order | `before_insert` hook | doc_events (behaviour) | A Sales Order row's chosen `bom_no` replaces the automatic default on the Work Order created from that row; a manually chosen (non-default) BOM on the Work Order is never overridden. Fixes ERPNext ignoring the row's BOM in get_work_order_items. Requested by the developer. | code (hooks.py) |
| 2026-08-26 | BOM | `inspection_required` description | Property Setter (tooltip only) | Explains that checking it gates Work Order completion behind a Quality Inspection of the output (the PDI). Requested by the developer. | yes |
| 2026-08-26 | Item | `inspection_required_before_delivery` description | Property Setter (tooltip only) | Explains that checking it blocks Delivery Note submission without an accepted Outgoing inspection (the dispatch gate). Requested by the developer. | yes |
| 2026-08-16 | Quality Meeting | `custom_minutes_guidance` | HTML (display only) | Explains, above the minutes table, when a minute links to a Quality Review, Quality Action or Quality Feedback and what to write. Prints as a note on FRM-024's blank form. Requested by the developer. | yes |
| 2026-08-14 | Quality Meeting | Document Naming Rule `HCCPL/QMS/FRM-024-` | Naming rule (record, not schema) | Meeting records number themselves as the form the register knows them by. Created by the ensure hook; deleting the rule reverts naming. | via hook |
