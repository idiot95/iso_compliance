# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-011, the Monitoring & Measuring Equipment register, as a live query.

Read from Asset and Asset Maintenance rather than a spreadsheet. Each
instrument is an Asset in the Measuring Instruments category, and its
calibration dates already live on the Calibration tasks of its Asset
Maintenance record: last done is the latest completion, due is the nearest
next due date. A register that is a query over those records cannot drift
from them the way a transcribed one does.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Equipment ID"), "fieldname": "name", "fieldtype": "Link", "options": "Asset", "width": 160},
		{"label": _("MME Description"), "fieldname": "asset_name", "fieldtype": "Data", "width": 240},
		{"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Date of Calibration"), "fieldname": "last_calibration", "fieldtype": "Date", "width": 130},
		{"label": _("Due Date of Calibration"), "fieldname": "calibration_due", "fieldtype": "Date", "width": 150},
	]


def get_data(filters):
	conditions = {
		"asset_category": filters.get("asset_category") or "Measuring Instruments",
		# Draft and submitted alike belong on the register; only equipment
		# that has left service does not.
		"status": ("not in", ("Scrapped", "Sold")),
	}

	assets = frappe.get_all(
		"Asset",
		filters=conditions,
		fields=["name", "asset_name", "location", "status"],
		# Explicit. v16 lists default to `creation`, which is not a register order.
		order_by="name asc",
		limit_page_length=0,
	)

	# One pass over every Calibration task; the join key on Asset Maintenance
	# is `asset_name`, which despite its label holds the Asset ID.
	tasks = frappe.db.sql(
		"""
		select
			am.asset_name as asset, t.last_completion_date, t.next_due_date
		from `tabAsset Maintenance Task` t
		inner join `tabAsset Maintenance` am on am.name = t.parent
		where t.maintenance_type = 'Calibration'
		""",
		as_dict=True,
	)

	last_done, next_due = {}, {}
	for t in tasks:
		if t.last_completion_date:
			if t.asset not in last_done or t.last_completion_date > last_done[t.asset]:
				last_done[t.asset] = t.last_completion_date
		if t.next_due_date:
			if t.asset not in next_due or t.next_due_date < next_due[t.asset]:
				next_due[t.asset] = t.next_due_date

	for a in assets:
		a.last_calibration = last_done.get(a.name)
		a.calibration_due = next_due.get(a.name)
	return assets
