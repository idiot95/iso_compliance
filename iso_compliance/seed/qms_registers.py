# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Load REG-002 to REG-005 content from the reviewed seed file, and remove it again.

These four registers had no home in ERPNext, so their content lived in Word and
Excel. The DocTypes now exist; this puts the existing content into them so the
registers are populated rather than empty covers.

Records carry the same batch token as the document seed, so one purge removes
everything this app imported.
"""

import json
import os

import frappe

from iso_compliance.seed.controlled_documents import SEED_BATCH

#: Target DocType keyed by the section of the seed file, with the field that
#: carries the batch token. None means the DocType has no such field, so those
#: records are matched for purge by the values they were created with.
SECTIONS = {
	"internal_external_issues": "Internal External Issue",
	"interested_parties": "Interested Party",
	"risks_and_opportunities": "Risk and Opportunity",
	"legal_requirements": "Legal Requirement",
}


def seed_file_path() -> str:
	return os.path.join(frappe.get_app_path("iso_compliance"), "seed_data", "qms_registers.json")


def load_seed() -> dict:
	with open(seed_file_path()) as fh:
		return json.load(fh)


def import_registers(batch: str = SEED_BATCH, commit: bool = True) -> dict:
	data = load_seed()
	result = {}

	for section, doctype in SECTIONS.items():
		rows = data.get(section) or []
		created = skipped = 0
		for row in rows:
			payload = {k: v for k, v in row.items() if v not in (None, "")}
			payload["doctype"] = doctype
			payload["seed_batch"] = batch

			if _already_present(doctype, row):
				skipped += 1
				continue

			doc = frappe.get_doc(payload)
			doc.insert(ignore_permissions=True)
			created += 1
		result[doctype] = {"created": created, "skipped": skipped}

	if commit:
		frappe.db.commit()
	return result


def _already_present(doctype: str, row: dict) -> bool:
	"""Re-running the import must not duplicate rows.

	Matched on the natural key of each register rather than on name, because
	most of these are auto-numbered and a second run would otherwise create a
	second copy of every row under a new number.
	"""
	keys = {
		"Internal External Issue": ("issue_title",),
		"Interested Party": ("party_name",),
		"Risk and Opportunity": ("title", "entry_type"),
		"Legal Requirement": ("requirement",),
	}[doctype]
	filters = {k: row.get(k) for k in keys if row.get(k)}
	return bool(filters) and bool(frappe.db.exists(doctype, filters))


def purge_registers(batch: str = SEED_BATCH, commit: bool = True) -> dict:
	result = {}
	for doctype in SECTIONS.values():
		names = frappe.get_all(doctype, filters={"seed_batch": batch}, pluck="name", order_by="name asc")
		for name in names:
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
			doc.delete(ignore_permissions=True, force=True)
		result[doctype] = len(names)
	if commit:
		frappe.db.commit()
	return result
