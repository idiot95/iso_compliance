# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Review parameter responses moved from Yes/No/NA to OK/Not OK/NA.

The questions were normalised so that the favourable answer is always the
same word; reviews answered before the change carry Yes/No values the Select
no longer offers, which would fail validation on their next save."""

import frappe


def execute():
	if not frappe.db.table_exists("Techno Commercial Review Parameter"):
		return
	for old, new in (("Yes", "OK"), ("No", "Not OK")):
		names = frappe.get_all(
			"Techno Commercial Review Parameter", filters={"response": old}, pluck="name"
		)
		for name in names:
			frappe.db.set_value(
				"Techno Commercial Review Parameter", name, "response", new, update_modified=False
			)
