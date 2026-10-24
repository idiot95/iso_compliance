# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""In-process check points renamed (2026-10-24): First-off, Patrol and Last-off
are First Check, Random Check and Last Check. Stored values follow."""

import frappe

RENAMES = {
	("Quality Inspection", "custom_check_point"): {
		"First-off": "First Check",
		"Patrol": "Random Check",
		"Last-off": "Last Check",
	},
	("Item Quality Inspection Parameter", "custom_in_process_at"): {
		"First-off only": "First Check only",
		"First-off and last-off": "First and Last Check",
	},
}


def execute():
	for (doctype, field), names in RENAMES.items():
		if not frappe.db.has_column(doctype, field):
			continue
		for old, new in names.items():
			frappe.db.sql(f"update `tab{doctype}` set `{field}` = %s where `{field}` = %s", (new, old))
