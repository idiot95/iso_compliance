# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Load the QMS document set from a reviewed seed file, and remove it again.

The seed file is produced on a workstation from the source Word documents and
committed to this repo, so what gets imported is reviewable in a diff rather
than being parsed live out of a zip on the server. That also makes the import
reproducible: the same file loaded on the clone and on production gives the same
records.

Everything written here is tagged with a batch token. A purge removes exactly
what carries that token and nothing else, so documents created by hand are never
at risk.
"""

import json
import os
import re

import frappe
from frappe import _
from frappe.utils import add_months, getdate

SEED_BATCH = "zip-2026-08-07"

TYPES = [
	("QM", "Quality Manual", "Rich Text", None),
	("POL", "Policy", "Rich Text", 24),
	("SOP", "Standard Operating Procedure", "Structured SOP", 12),
	("WI", "Work Instruction", "Structured SOP", 12),
	("FRM", "Form", "Mapped Data", 24),
	("REG", "Register", "Mapped Data", 12),
]

#: Lifecycle states. Frappe ships only Open/Rejected/Approved/Pending, so the rest
#: are created here. They are configuration for the document workflow rather than
#: imported content, so a purge leaves them in place.
WORKFLOW_STATES = [
	("Draft", "Danger"),
	("Under Review", "Warning"),
	("Approved", "Info"),
	("Active", "Success"),
	("Superseded", ""),
	("Obsolete", ""),
]

#: SOP bodies cite some forms by an unfilled placeholder -- "FRMxxx - Job Card",
#: "FRM0XX", "FRMXX" -- even where the form exists in REG-001 with a real number.
#: FRM-007 Job Card is in the register; three SOPs simply never wrote the number in.
#:
#: These are resolved from a reviewed map rather than by matching titles, because
#: matching gets it wrong in ways that matter: "Supplier Corrective Action Request"
#: fuzzy-matches SOP-014, a procedure, and "Production Plan" matches SOP-007 itself.
#: A controlled document citing the wrong document is worse than one citing none.
#:
#: Keyed by the placeholder text as it appears in the source, lowercased.
PLACEHOLDER_ALIASES = {
	"supplier evaluation form": "FRM005",
	"incoming inspection report": "FRM006",
	"job card": "FRM007",
	"job cards": "FRM007",
	"material requisition": "FRM008",
	"in-process inspection reports": "FRM009",
	"packing checklist": "FRM018",
	"dispatch checklist": "FRM019",
	# The delivery challan is the ERPNext Delivery Note. FRM-029 is the only form in
	# REG-001 whose data source is Delivery Note, so a challan cited as a record
	# generated resolves there; REG-024 Dispatch Register is the register of them.
	"delivery challan": "FRM029",
	"delivery challans": "FRM029",
	# Same artefact under a different name in the SOP text.
	"contract review checklist": "FRM003",
	"supplier performance evaluation": "FRM005",
}

#: REG-001 names the department that fills each document in. Five of the thirteen
#: it names have no Department record in ERPNext, so the register's own label is
#: kept as text and the Link is set only where a real Department exists. Assigning
#: scope of work to a department that does not exist in the ERP would be a fiction.
#: "M gmt." is a typo in the source, carried by two documents.
#: Keyed on the six folded departments (see DEPARTMENT_BUCKETS below), so every
#: document also carries the real ERPNext Department link where one exists.
DEPARTMENT_MAP = {
	"Quality": "Quality - HCCPL",
	"Management": "Management - HCCPL",
	"Sales & Marketing": "Sales - HCCPL",
	"Purchase": "Purchase - HCCPL",
	"Production": "Production - HCCPL",
	"Accounts": "Accounts - HCCPL",
}

BASELINE_NOTE = (
	"Baseline entry created when the document was brought under ERPNext document control. "
	"The source document recorded no evidence of preparation, review or approval, so the "
	"authority columns are left empty rather than assumed."
)


def seed_file_path() -> str:
	return os.path.join(
		frappe.get_app_path("iso_compliance"), "seed_data", "controlled_documents.json"
	)


def load_seed() -> list[dict]:
	with open(seed_file_path()) as fh:
		return json.load(fh)["documents"]


# ----------------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------------


def import_seed(batch: str = SEED_BATCH, commit: bool = True) -> dict:
	"""Create the controlled document set. Safe to re-run: existing names are skipped."""
	documents = load_seed()
	_ensure_workflow_states()
	created_types = _ensure_types(batch)

	# Legacy number -> new document number, so cross-references between documents
	# resolve to the records actually being created.
	resolve = {d["legacy_document_number"]: d["name"] for d in documents}

	created, skipped = [], []
	# The flag spans the whole run, not just record creation: the cross-reference
	# pass below saves Active documents, and the change-control gate would
	# otherwise demand a Document Change Request from the importer itself.
	frappe.flags.in_import = True
	try:
		for entry in documents:
			if frappe.db.exists("Controlled Document", entry["name"]):
				skipped.append(entry["name"])
				continue
			_create_document(entry, resolve, batch)
			created.append(entry["name"])

		# Documents cross-reference each other, and a reference can point forward:
		# SOP-001 cites REG-001 and FRM-001, which are created later in the same
		# run. Link fields are therefore filled once every record exists.
		linked = _resolve_cross_references(documents, resolve)
	finally:
		frappe.flags.in_import = False
	advanced = _advance_naming_series(documents)

	if commit:
		frappe.db.commit()

	return {
		"types_created": created_types,
		"documents_created": len(created),
		"documents_skipped": len(skipped),
		"cross_references_linked": linked,
		"series_advanced": advanced,
		"batch": batch,
	}


def _resolve_placeholder(title: str, resolve: dict) -> str | None:
	"""Link a citation whose number was left as a placeholder in the source.

	Only exact entries in the reviewed map are honoured. A citation that is not in
	the map keeps its original text and no link, which prints as written and stays
	visible as something to fix.
	"""
	if not title:
		return None
	text = re.sub(r"^\s*FRM\s*[xX0-9]*\s*[-–—]\s*", "", title).strip().lower()
	legacy = PLACEHOLDER_ALIASES.get(text)
	return resolve.get(legacy) if legacy else None


def _advance_naming_series(documents: list[dict]) -> dict:
	"""Move each type's counter past the highest number the import consumed.

	Imported documents are named explicitly, which bypasses the counter entirely.
	Left alone it stays at zero, and the first document anyone creates by hand
	collides with SOP-001.
	"""
	from frappe.model.naming import NamingSeries

	highest: dict[str, int] = {}
	for entry in documents:
		abbr = entry["document_type"]
		match = re.search(r"(\d+)$", entry["name"])
		if match:
			highest[abbr] = max(highest.get(abbr, 0), int(match.group(1)))

	advanced = {}
	for abbr, top in sorted(highest.items()):
		if not frappe.db.exists("Controlled Document Type", abbr):
			continue
		doc_type = frappe.get_cached_doc("Controlled Document Type", abbr)
		series = NamingSeries(doc_type.get_naming_series())
		if series.get_current_value() < top:
			series.update_counter(top)
			advanced[abbr] = top
	return advanced


def _resolve_cross_references(documents: list[dict], resolve: dict) -> int:
	linked = 0
	for entry in documents:
		if not entry.get("sop"):
			continue
		doc = frappe.get_doc("Controlled Document", entry["name"])
		changed = False
		for table in ("records_generated",):
			for row in doc.get(table) or []:
				target = resolve.get(row.document_number) or (
					row.document_number if frappe.db.exists("Controlled Document", row.document_number) else None
				)
				if not target:
					target = _resolve_placeholder(row.document_title, resolve)
				if target and row.document != target:
					row.document = target
					if not row.document_number or row.document_number == row.document_title:
						row.document_number = target
					changed = True
					linked += 1

		# References citing an internal document by its legacy number ("QM001 -
		# Quality Manual") link to the controlled document itself; standards and
		# other external citations stay as text.
		for row in doc.get("references") or []:
			target = _reference_target(row.reference, resolve)
			if target and row.linked_document != target:
				row.linked_document = target
				changed = True
				linked += 1
		if changed:
			doc.save(ignore_permissions=True)
	return linked


_ISO_CLAUSE = re.compile(r"ISO\s*9001(?:\s*:\s*2015)?\s*[,\u2013\u2014-]?\s*Clause\s*([\d.]+)", re.I)


def _reference_rows(entry: dict, sop: dict | None) -> list[dict]:
	rows = []
	has_iso = False
	for r in (sop or {}).get("references", []):
		text = r.get("reference")
		if not text:
			continue
		row = {"reference": text}
		match = _ISO_CLAUSE.search(text)
		if match:
			row["clause"] = match.group(1)
			has_iso = True
		rows.append(row)
	clause = entry.get("clause_reference")
	if clause and not has_iso:
		rows.insert(0, {"reference": "ISO 9001:2015", "clause": clause})
	return rows


#: "QM001", "REG 001", "FRM-020" at the start of a citation line.
_REFERENCE_NUMBER = re.compile(r"^\s*([A-Z]{2,4})\s*-?\s*0*(\d{1,4})\b")


def _reference_target(text: str | None, resolve: dict) -> str | None:
	match = _REFERENCE_NUMBER.match(text or "")
	if not match:
		return None
	return resolve.get(f"{match.group(1)}{int(match.group(2)):03d}")


def _ensure_workflow_states():
	for state, style in WORKFLOW_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)


def _ensure_types(batch: str) -> int:
	created = 0
	for abbr, label, mode, review_months in TYPES:
		if frappe.db.exists("Controlled Document Type", abbr):
			continue
		frappe.get_doc(
			{
				"doctype": "Controlled Document Type",
				"abbreviation": abbr,
				"type_name": label,
				"body_mode": mode,
				"naming_series_prefix": f"HCCPL/QMS/{abbr}-",
				"number_padding": 3,
				"review_frequency_months": review_months,
				"enabled": 1,
				"seed_batch": batch,
			}
		).insert(ignore_permissions=True)
		created += 1
	return created


def _create_document(entry: dict, resolve: dict, batch: str):
	payload = {
		"doctype": "Controlled Document",
		"name": entry["name"],
		"title": entry["title"],
		"document_type": entry["document_type"],
		"legacy_document_number": entry["legacy_document_number"],
		"clause_reference": entry.get("clause_reference") or None,
		# in_import skips _set_defaults, so the control block is supplied explicitly.
		"issue_number": entry.get("issue_number") or "01",
		"issue_date": entry.get("issue_date"),
		"revision_number": entry.get("revision_number") or "00",
		"body_mode": entry.get("body_mode"),
		"body_content": entry.get("body_content"),
		"mapped_doctype": entry.get("mapped_doctype"),
		"mapped_filters": entry.get("mapped_filters"),
		"mapped_report": entry.get("mapped_report"),
		"print_columns": json.dumps(entry["print_columns"]) if entry.get("print_columns") else None,
		"print_layout": entry.get("print_layout") or "Table",
		"static_table": json.dumps(entry["static_table"]) if entry.get("static_table") else None,
		"workflow_state": "Active" if entry.get("has_source_file") else "Draft",
		"owning_department": _department_label(entry.get("department_label")),
		"approval_authority": entry.get("approval_authority") or None,
		"seed_batch": batch,
	}

	erp_department = DEPARTMENT_MAP.get(_department_label(entry.get("department_label")))
	if erp_department and frappe.db.exists("Department", erp_department):
		payload["department"] = erp_department

	# A review interval is only useful if it resolves to a date something can fall
	# past. Derive it from the issue date so the review-due reporting is live from
	# day one rather than after someone fills 93 dates in by hand.
	months = _review_months(entry["document_type"])
	if months and payload.get("issue_date"):
		payload["review_frequency_months"] = months
		payload["next_review_date"] = add_months(getdate(payload["issue_date"]), months)

	sop = entry.get("sop")
	if sop:
		payload["purpose"] = sop.get("purpose")
		payload["scope"] = sop.get("scope")
		pass  # references built below for every entry, SOP or not
		payload["definitions"] = [
			{"term": d["term"], "definition": d["definition"]} for d in sop.get("definitions", [])
		]
		payload["responsibilities"] = [
			{"role": r["role"], "responsibility": r["responsibility"]}
			for r in sop.get("responsibilities", [])
		]
		payload["procedure_steps"] = sop.get("procedure_steps", [])
		payload["records_generated"] = _link_rows(sop.get("records_generated", []), resolve)

	# Every document cites at least the ISO clause it answers to. SOP citations
	# come with their own texts; other documents get a bare ISO 9001:2015 row
	# carrying the clause, so the References table is the single home of clause
	# information and the hidden header field derives from it.
	payload["references"] = _reference_rows(entry, sop)

	# The importer holds frappe.flags.in_import for the whole run: set_new_name
	# only honours the supplied historical number under that flag (it also skips
	# _set_defaults, which is why the control block is supplied explicitly above).
	doc = frappe.get_doc(payload)
	doc.append(
		"revisions",
		{
			"issue_number": doc.issue_number,
			"issue_date": doc.issue_date,
			"revision_number": doc.revision_number,
			"revision_date": None,
			"clause_section_affected": _("All"),
			"description_of_change": _baseline_note(entry),
		},
	)
	doc.insert(ignore_permissions=True)


#: The thirteen department spellings REG-001 uses, folded into the six
#: departments the company actually filters by. Functions without their own
#: department land where they report: Design/Engineering and Maintenance under
#: Production, Stores under Purchase (the materials function), Dispatch under
#: Sales (outbound), HR and company-wide documents under Management. Accounts
#: exists as a bucket for future documents; none of the 93 belong to it today.
DEPARTMENT_BUCKETS = {
	"QA": "Quality",
	"Mgmt.": "Management",
	"M gmt.": "Management",
	"Management": "Management",
	"HR": "Management",
	"All": "Management",
	"Production": "Production",
	"Design / Engineering": "Production",
	"Maintenance": "Production",
	"Sales": "Sales & Marketing",
	"Dispatch": "Sales & Marketing",
	"Stores / Dispatch": "Sales & Marketing",
	"Purchase": "Purchase",
	"Stores": "Purchase",
	"Accounts": "Accounts",
}


def _department_label(label: str | None) -> str | None:
	"""Fold REG-001's thirteen spellings into the six filterable departments."""
	if not label:
		return None
	return DEPARTMENT_BUCKETS.get(label.strip(), label.strip())


def _review_months(abbr: str) -> int | None:
	for code, _label, _mode, months in TYPES:
		if code == abbr:
			return months
	return None


def _baseline_note(entry: dict) -> str:
	note = BASELINE_NOTE
	declared = (entry.get("sop") or {}).get("declared_number")
	if declared and declared != entry["legacy_document_number"]:
		note += (
			f" Identification defect carried over from the source: the document body declared "
			f"{declared} while the file was held as {entry['legacy_document_number']}. "
			f"Recorded here rather than silently corrected."
		)
	if not entry.get("has_source_file"):
		note += " No source document exists for this entry; it is listed in REG-001 but was never written."
	return note


def _link_rows(rows: list[dict], resolve: dict) -> list[dict]:
	"""Build link rows without the Link field set.

	The number and title are recorded now so nothing is lost if the target does not
	exist; _resolve_cross_references fills the Link field once every record is in.
	"""
	out = []
	for r in rows:
		number = r.get("number") or ""
		out.append(
			{
				"document_number": resolve.get(number) or number,
				"document_title": r.get("title") or "",
			}
		)
	return out


# ----------------------------------------------------------------------------
# Purge
# ----------------------------------------------------------------------------


def purge_seed(batch: str = SEED_BATCH, commit: bool = True) -> dict:
	"""Remove every record created by a seed import, and nothing else.

	Only records carrying the batch token are touched. Anything created by hand,
	or by a different batch, is left alone.
	"""
	docs = frappe.get_all(
		"Controlled Document", filters={"seed_batch": batch}, pluck="name", order_by="name asc"
	)

	# Clear links between seeded documents first, so deletion order cannot trip
	# link validation on documents that reference each other.
	for name in docs:
		frappe.db.set_value("Controlled Document", name, "superseded_by", None, update_modified=False)
		frappe.db.set_value("Controlled Document", name, "supersedes", None, update_modified=False)

	deleted = 0
	for name in docs:
		doc = frappe.get_doc("Controlled Document", name)
		if doc.docstatus == 1:
			doc.cancel()
		doc.delete(ignore_permissions=True, force=True)
		deleted += 1

	types = frappe.get_all(
		"Controlled Document Type", filters={"seed_batch": batch}, pluck="name", order_by="name asc"
	)
	types_deleted, types_kept = 0, []
	for name in types:
		if frappe.db.exists("Controlled Document", {"document_type": name}):
			# A hand-created document still uses this type, so it stays.
			types_kept.append(name)
			continue
		frappe.delete_doc("Controlled Document Type", name, ignore_permissions=True, force=True)
		frappe.db.sql("delete from tabSeries where name like %s", (f"HCCPL/QMS/{name}-%",))
		types_deleted += 1

	if commit:
		frappe.db.commit()

	return {
		"documents_deleted": deleted,
		"types_deleted": types_deleted,
		"types_kept_in_use": types_kept,
		"batch": batch,
	}


@frappe.whitelist()
def purge_seed_ui(batch: str = SEED_BATCH):
	"""Purge from the desk. Restricted to System Manager."""
	frappe.only_for("System Manager")
	result = purge_seed(batch)
	frappe.msgprint(
		_("Removed {0} controlled documents and {1} document types from batch {2}.").format(
			result["documents_deleted"], result["types_deleted"], batch
		),
		title=_("Seed Data Purged"),
		indicator="orange",
	)
	return result
