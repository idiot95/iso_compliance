# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Who fills in what, and where in ERPNext they do it.

Written to be pasted into a scope of work. Each row names one department, one
document they are responsible for, the ERPNext DocType they fill it in through,
and who approves it. Sorted by department so a single person's obligations are
contiguous.

Documents with no ERPNext data source are still listed: those are filled in on
paper or in the document itself, and leaving them out would understate what a
department is accountable for.
"""

import frappe
from frappe import _

#: Roles that documents are approved by, mapped to the named holder in REG-013
#: where one exists. The Quality Manager role is deliberately left unresolved --
#: nobody in REG-013 holds that title, which is a real gap rather than a lookup
#: failure, and it should stay visible in this report until it is filled.
AUTHORITY_HOLDER = {
	"Director": "Managing Director & CEO",
	"QA Manager": "",
	"Maintenance Head": "",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Department"), "fieldname": "owning_department", "fieldtype": "Data", "width": 150},
		{"label": _("In ERPNext"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 165},
		{"label": _("Document No."), "fieldname": "name", "fieldtype": "Link", "options": "Controlled Document", "width": 165},
		{"label": _("Document"), "fieldname": "title", "fieldtype": "Data", "width": 270},
		{"label": _("Type"), "fieldname": "document_type", "fieldtype": "Data", "width": 60},
		{"label": _("Filled In Through"), "fieldname": "mapped_doctype", "fieldtype": "Link", "options": "DocType", "width": 175},
		{"label": _("Entries"), "fieldname": "entries", "fieldtype": "Int", "width": 75},
		{"label": _("Approved By"), "fieldname": "approval_authority", "fieldtype": "Data", "width": 130},
		{"label": _("Clause"), "fieldname": "clause_reference", "fieldtype": "Data", "width": 90},
		{"label": _("Status"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 90},
	]


def get_data(filters):
	conditions = {"document_type": ("in", filters.get("document_type") or ["FRM", "REG"])}
	if filters.get("owning_department"):
		conditions["owning_department"] = filters.owning_department

	rows = frappe.get_all(
		"Controlled Document",
		filters=conditions,
		fields=[
			"name", "title", "document_type", "owning_department", "department",
			"mapped_doctype", "mapped_filters", "approval_authority",
			"clause_reference", "workflow_state",
		],
		# Explicit, and by department first: this report is read one department at
		# a time by whoever owns that scope of work.
		order_by="owning_department asc, document_type asc, name asc",
		limit_page_length=0,
	)

	for r in rows:
		r["entries"] = _count(r)
	return rows


def _count(row):
	"""How many entries exist today, so a scope of work reflects real volume."""
	if not row.get("mapped_doctype") or not frappe.db.exists("DocType", row["mapped_doctype"]):
		return 0
	try:
		import json

		filters = json.loads(row["mapped_filters"]) if row.get("mapped_filters") else {}
		return frappe.db.count(row["mapped_doctype"], filters)
	except Exception:
		return 0
