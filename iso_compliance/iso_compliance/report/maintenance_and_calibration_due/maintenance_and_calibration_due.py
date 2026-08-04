# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Every jig, die and instrument with maintenance or calibration falling due.

Built on ERPNext's own Asset Maintenance model rather than fields bolted onto
Asset: a maintenance record holds tasks, each with a type of Preventive
Maintenance or Calibration, a periodicity and a next due date. That is the whole
requirement, and it was already there.

Overdue first, because this report is a worklist.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Due"), "fieldname": "due_state", "fieldtype": "Data", "width": 95},
		{"label": _("Next Due"), "fieldname": "next_due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Days"), "fieldname": "days", "fieldtype": "Int", "width": 65},
		{"label": _("Asset"), "fieldname": "asset_name", "fieldtype": "Link", "options": "Asset", "width": 150},
		{"label": _("Asset Name"), "fieldname": "asset_label", "fieldtype": "Data", "width": 200},
		{"label": _("Category"), "fieldname": "asset_category", "fieldtype": "Data", "width": 150},
		{"label": _("Task"), "fieldname": "maintenance_task", "fieldtype": "Data", "width": 200},
		{"label": _("Type"), "fieldname": "maintenance_type", "fieldtype": "Data", "width": 145},
		{"label": _("Periodicity"), "fieldname": "periodicity", "fieldtype": "Data", "width": 100},
		{"label": _("Assigned To"), "fieldname": "assign_to_name", "fieldtype": "Data", "width": 140},
		{"label": _("Last Done"), "fieldname": "last_completion_date", "fieldtype": "Date", "width": 100},
		{"label": _("Maintenance"), "fieldname": "parent", "fieldtype": "Link", "options": "Asset Maintenance", "width": 150},
	]


def get_data(filters):
	horizon = int(filters.get("days") or 90)
	cutoff = add_days(nowdate(), horizon)

	rows = frappe.db.sql(
		"""
		select
			t.next_due_date, t.maintenance_task, t.maintenance_type, t.periodicity,
			t.assign_to_name, t.last_completion_date, t.parent,
			am.asset_name, am.asset_category
		from `tabAsset Maintenance Task` t
		inner join `tabAsset Maintenance` am on am.name = t.parent
		where ifnull(t.maintenance_status, '') != 'Cancelled'
			and t.next_due_date is not null
			and t.next_due_date <= %(cutoff)s
		order by t.next_due_date asc, am.asset_name asc
		""",
		{"cutoff": cutoff},
		as_dict=True,
	)

	today = getdate(nowdate())
	out = []
	for r in rows:
		days = (getdate(r.next_due_date) - today).days
		r.days = days
		r.due_state = _("Overdue") if days < 0 else (_("Due") if days <= 30 else _("Upcoming"))
		r.asset_label = frappe.db.get_value("Asset", r.asset_name, "asset_name") or r.asset_name
		out.append(r)
	return out
