# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Draft reviews get the Technical check "Is existing tooling available?", added to the
checklists on 2026-11-24. Placed where a new review has it: after "We can make it" on a
Detailed review, after the first check on a Standard one. Submitted reviews are left as
they were reviewed."""

import frappe

QUESTION = "Is existing tooling available?"
AFTER_DETAILED = "We can make it: machines, people and material available"
CHILD = "Techno Commercial Review Parameter"


def execute():
	for review in frappe.get_all("Techno Commercial Review", filters={"docstatus": 0}, pluck="name"):
		rows = frappe.get_all(
			CHILD,
			filters={"parent": review, "parenttype": "Techno Commercial Review", "parentfield": "technical_parameters"},
			fields=["name", "idx", "parameter"],
			order_by="idx asc",
		)
		if not rows or any(r.parameter == QUESTION for r in rows):
			continue
		after = next((r.idx for r in rows if r.parameter == AFTER_DETAILED), rows[0].idx)
		for r in rows:
			if r.idx > after:
				frappe.db.set_value(CHILD, r.name, "idx", r.idx + 1, update_modified=False)
		frappe.get_doc(
			{
				"doctype": CHILD,
				"parent": review,
				"parenttype": "Techno Commercial Review",
				"parentfield": "technical_parameters",
				"idx": after + 1,
				"parameter": QUESTION,
			}
		).db_insert()
