# Installing on the live site

Short version: **there is nothing to recreate by hand.** No DocType outside this
app was modified, no Custom Field was added to ERPNext, and no site setting needs
changing. Installing the app and running one import command reproduces everything
that exists on the clone.

## What the app brings with it automatically

Installed by `bench install-app`, carried by `bench migrate` on every upgrade:

| | |
| --- | --- |
| DocTypes | 16, all in the `ISO Compliance` module |
| Print Format | `Controlled Document`, one format serving every body type; registers print landscape in their source file's own column layout |
| Workspaces | `ISO Compliance` (home) and `Compliance Dashboard` (child) |
| Desk navigation | Desktop Icon (shield, in the ERPNext group) and Workspace Sidebar, restored by hook — see below |
| Number Cards | 13 |
| Dashboard Charts | 5 |
| Script Reports | Master Document Register, Compliance Gaps, Maintenance and Calibration Due, Customer PO Amendment Register, Form Responsibility by Department, Employee Competency Matrix, Measuring Equipment Register, Incoming Material Register, Maintenance Register |
| Notification | Maintenance or Calibration Due, 14 days ahead |
| Workflow States | Draft, Under Review, Approved, Active, Superseded, Obsolete |
| Role permissions | Quality Manager: full control of every QMS DocType. Employee: read and print everything, raise (not approve) Document Change Requests. Assign ERPNext's existing Quality Manager role to whoever runs the QMS — at least two people, because a DCR's requester cannot approve it. "All" is deliberately not used: it includes portal logins (customers, suppliers). |

Two pieces of configuration live outside this app's own DocTypes, both created
by the `after_install` / `after_migrate` hook, idempotent, touching nothing that
already exists:

- **Workflow States.** Frappe ships only Open, Rejected, Approved and Pending,
  and `Controlled Document.workflow_state` links to Workflow State, so the rest
  must exist.
- **Desk registration.** Frappe 16 builds the desk grid and workspace switcher
  from Desktop Icon and Workspace Sidebar records grouped by app. For ISO
  Compliance to be listed alongside Assets and Quality (not in a third-party
  silo), its records say `app: erpnext` — and migrate's orphan sweep deletes
  cross-app records on every run, so the hook re-imports them after each
  migrate. Self-healing; no manual step.

## What resolves automatically on your site, and what does not

**Automatic.** All 42 register mappings point at DocTypes that exist wherever
ERPNext and HRMS are installed: 19 belong to erpnext, 4 to hrms, 7 to this app.
None depend on india_compliance, crm or hatim_carbon. A mapped register reads live
data, so on production it shows production's rows the moment the app is installed
— no re-pointing, no configuration. The cross-references between controlled
documents are resolved during import, against the documents being imported.

`required_apps = ["erpnext"]` is declared, so installing without it fails at
install time rather than part-way through a migrate. HRMS is not required: it owns
four mappings (training records, competency matrix) and without it those four
registers are simply unmapped.

**Not automatic, by design.** Seeded records are created by the two import
commands below, not by a migrate hook.

**Nothing to re-point.** No seeded document carries a link to a User, Department
or Employee — `prepared_by`, `reviewed_by`, `approved_by`, `process_owner` and
`department` are empty on all 93, because the source documents recorded no such
evidence. Nothing can dangle against a different user list.

## Steps

```bash
# 1. Install the app (Frappe Cloud: add it to the bench from the git repo,
#    then install it on the site).
bench --site <site> install-app iso_compliance

# 2. Load the document set: 93 controlled documents and 6 document types.
bench --site <site> execute iso_compliance.seed.controlled_documents.import_seed

# 3. Load the register content: REG-002, REG-003, REG-004, REG-005.
bench --site <site> execute iso_compliance.seed.qms_registers.import_registers
```

Both imports are idempotent. Running them twice creates nothing the second time.

Seed loading is deliberately **not** in a migrate hook. A routine upgrade must
never write 93 controlled documents into production on its own.

## Removing the imported data

```bash
bench --site <site> execute iso_compliance.seed.qms_registers.purge_registers
bench --site <site> execute iso_compliance.seed.controlled_documents.purge_seed
```

Every imported record carries a batch token and the purge removes exactly those.
Anything created by hand is untouched, and a document type still used by a
hand-created document is kept.

## What was NOT changed, and why that matters

Nothing below needs replicating on production, because none of it was altered in
a way the app depends on.

- **No Custom Fields on any ERPNext DocType.** Verified directly: zero exist.
  The Asset calibration proposal has been **withdrawn** as unnecessary --
  ERPNext's own Asset Maintenance model already covers calibration and annual
  maintenance, so nothing needs adding to Asset. Only the Supplier approval set
  in [EXTERNAL_CHANGES.md](EXTERNAL_CHANGES.md) remains proposed and unbuilt.
- **No Property Setters, Client Scripts or permission changes** on existing
  DocTypes.
- **No change to core behaviour.** The app adds Link fields on *its own*
  DocTypes pointing at `User`, `Department`, `DocType`, `Asset`, `Supplier` and
  so on. That adds nothing to those DocTypes and needs no fixture.
- **`Print Settings.pdf_generator` is untouched.** It was briefly set to `chrome`
  on the clone during development and has been set back to `wkhtmltopdf`, the
  value restored from production. The print format carries
  `pdf_generator = chrome` on the Print Format record itself, which is what
  actually governs rendering, so nothing site-wide is required and no existing
  print format changes behaviour.
- **`developer_mode` is enabled on the clone only.** It is required to export
  DocTypes to files during development. Do not enable it on production.

## Things to know before you promote

- **`sites/apps.txt` can lose entries when containers are recreated.** On the clone,
  recreating the frontend container re-ran the configurator and rewrote apps.txt from
  what that image could see, dropping `iso_compliance`, `crm` and
  `email_delivery_service`. The symptom is `Module ISO Compliance not found` and
  print formats silently failing to sync. This is a docker-compose artifact and does
  not arise on Frappe Cloud, but it is worth recognising.
- **The six print formats that hardcode a document number** (Sales Order
  Acknowledgement, Purchase Order, Material Request, Purchase Receipt, Quotation,
  Work Order) still carry the old `HCCPL-SLS-001` style numbers. They are not
  touched by this app. If the numbering convention changes, those six need
  editing, and `legacy_document_number` on each Controlled Document keeps the old
  number searchable in the meantime.
- **Compiling more than 25 documents into one PDF is queued**, not run in the web
  process. Each document is rendered by its own headless Chrome and those
  accumulate; the full 93-document set exhausted memory when run synchronously.
- **Page numbers are absent from the printed footer.** Frappe 16.29 is missing
  the script that stamps them (`update_page_no.js`), so the footer repeats the
  document number, issue and revision instead. See EXTERNAL_CHANGES.md.
