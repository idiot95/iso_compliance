# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-001, as a live query rather than a maintained table.

The assessor's finding was partly that the register is maintained by hand. A
document set that has to be transcribed into a register drifts from it, which is
how a register ends up claiming 93 documents are Active when 56 were never
written. Reading it back out of the document records removes that failure mode.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Document No."), "fieldname": "name", "fieldtype": "Link", "options": "Controlled Document", "width": 175},
		{"label": _("Title"), "fieldname": "title", "fieldtype": "Data", "width": 280},
		{"label": _("Type"), "fieldname": "document_type", "fieldtype": "Link", "options": "Controlled Document Type", "width": 70},
		{"label": _("Department"), "fieldname": "owning_department", "fieldtype": "Data", "width": 90},
		{"label": _("Approval Authority"), "fieldname": "approval_authority", "fieldtype": "Data", "width": 110},
		{"label": _("Clause"), "fieldname": "clause_reference", "fieldtype": "Data", "width": 80},
		{"label": _("Issue"), "fieldname": "issue_number", "fieldtype": "Data", "width": 55},
		{"label": _("Issue Date"), "fieldname": "issue_date", "fieldtype": "Date", "width": 95},
		{"label": _("Rev."), "fieldname": "revision_number", "fieldtype": "Data", "width": 50},
		{"label": _("Rev. Date"), "fieldname": "revision_date", "fieldtype": "Date", "width": 95},
		{"label": _("Status"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 95},
		{"label": _("Prepared By"), "fieldname": "prepared_by_name", "fieldtype": "Data", "width": 130},
		{"label": _("Reviewed By"), "fieldname": "reviewed_by_name", "fieldtype": "Data", "width": 130},
		{"label": _("Approved By"), "fieldname": "approved_by_name", "fieldtype": "Data", "width": 130},
		{"label": _("Next Review"), "fieldname": "next_review_date", "fieldtype": "Date", "width": 100},
		{"label": _("Data Source"), "fieldname": "mapped_doctype", "fieldtype": "Link", "options": "DocType", "width": 150},
		{"label": _("Legacy No."), "fieldname": "legacy_document_number", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	conditions = {}
	if filters.get("document_type"):
		conditions["document_type"] = filters.document_type
	if filters.get("status"):
		conditions["workflow_state"] = filters.status
	if not filters.get("include_retired"):
		conditions["workflow_state"] = ("not in", ("Superseded", "Obsolete"))

	rows = frappe.get_all(
		"Controlled Document",
		filters=conditions,
		fields=[
			"name", "title", "document_type", "owning_department", "approval_authority",
			"clause_reference", "issue_number",
			"issue_date", "revision_number", "revision_date", "workflow_state",
			"prepared_by_name", "reviewed_by_name", "approved_by_name",
			"next_review_date", "mapped_doctype", "legacy_document_number",
		],
		# Explicit. v16 lists default to `creation`, which is not a register order.
		order_by="name asc",
		limit_page_length=0,
	)

	# The register reads in document hierarchy, not alphabetically: the manual,
	# then policies, procedures, work instructions, registers, and forms last.
	rank = {"QM": 0, "POL": 1, "SOP": 2, "WI": 3, "REG": 4, "FRM": 5}
	rows.sort(key=lambda r: (rank.get(r.document_type, 9), r.name))
	return rows
