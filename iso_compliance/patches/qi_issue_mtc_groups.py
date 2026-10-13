# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Item Groups whose deliveries carry a 3.1 MTC (developer, 2026-10-13).
Set once; after that the flag on each group is Quality's to change."""

import frappe

GROUPS = (
	"Carbon Block",
	"Copper Wire",
	"Chemicals",
	"Pipe Fittings",
	"Terminal",
	"Sheet Metal",
	"Tamping Powder",
	"Tubes & Rods",
	"Raw Insulation Sheet",
	"Machinery Tools",
	"Machined FG Parts",
	"Rubberized Insulation Sheet",
)


def execute():
	if not frappe.get_meta("Item Group").has_field("custom_issue_mtc"):
		from iso_compliance.qi.custom_fields import create_phase_c2

		create_phase_c2()
	for name in GROUPS:
		if frappe.db.exists("Item Group", name):
			frappe.db.set_value("Item Group", name, "custom_issue_mtc", 1, update_modified=False)
