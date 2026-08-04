# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Every open compliance gap on one page, with the next action spelled out.

Deliberately not a score. A percentage tells nobody what to do on Monday; a row
saying "56 register entries have no document written" does. Gaps that are closed
drop off the report entirely, so an empty report is the goal state.
"""

from frappe import _

from iso_compliance.api.dashboard import get_gap_rows


def execute(filters=None):
	return get_columns(), get_data()


def get_columns():
	return [
		{"label": _("Area"), "fieldname": "area", "fieldtype": "Data", "width": 150},
		{"label": _("Clause"), "fieldname": "clause", "fieldtype": "Data", "width": 70},
		{"label": _("Finding"), "fieldname": "finding", "fieldtype": "Data", "width": 380},
		{"label": _("Count"), "fieldname": "count", "fieldtype": "Int", "width": 80},
		{"label": _("Next Action"), "fieldname": "action", "fieldtype": "Data", "width": 430},
		{"label": _("Recorded In"), "fieldname": "doctype", "fieldtype": "Link", "options": "DocType", "width": 160},
	]


def get_data():
	# Largest gaps first: this report is a worklist, not an inventory.
	return sorted(get_gap_rows(), key=lambda r: -r["count"])
