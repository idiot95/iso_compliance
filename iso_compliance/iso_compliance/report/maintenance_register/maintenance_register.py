# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-021, the Maintenance Register.

One row per maintenance task per equipment, its schedule and completion state,
read from ERPNext's Asset Maintenance model. Nothing here is a second copy of
anything: the register is the maintenance records themselves, so a task that is
rescheduled or completed shows up here the moment it is saved.

Note the field naming trap: on Asset Maintenance, `asset_name` is the Link to
Asset (it holds the Asset's ID), while the human-readable name lives on the
Asset itself, also as `asset_name`.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Equipment ID"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 150},
		{"label": _("Machine / Equipment Name"), "fieldname": "asset_display_name", "fieldtype": "Data", "width": 200},
		{"label": _("Maintenance Task"), "fieldname": "maintenance_task", "fieldtype": "Data", "width": 200},
		{"label": _("Maintenance Type"), "fieldname": "maintenance_type", "fieldtype": "Data", "width": 145},
		{"label": _("Frequency"), "fieldname": "periodicity", "fieldtype": "Data", "width": 100},
		{"label": _("Assigned To"), "fieldname": "assign_to_name", "fieldtype": "Data", "width": 140},
		{"label": _("Last Done"), "fieldname": "last_completion_date", "fieldtype": "Date", "width": 100},
		{"label": _("Next Due"), "fieldname": "next_due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Status"), "fieldname": "maintenance_status", "fieldtype": "Data", "width": 95},
	]


def get_data(filters):
	return frappe.db.sql(
		"""
		select
			am.asset_name as asset,
			a.asset_name as asset_display_name,
			t.maintenance_task, t.maintenance_type, t.periodicity,
			t.assign_to_name, t.last_completion_date, t.next_due_date,
			t.maintenance_status
		from `tabAsset Maintenance Task` t
		inner join `tabAsset Maintenance` am on am.name = t.parent
		left join `tabAsset` a on a.name = am.asset_name
		order by t.next_due_date is null, t.next_due_date asc, am.asset_name asc
		""",
		as_dict=True,
	)
