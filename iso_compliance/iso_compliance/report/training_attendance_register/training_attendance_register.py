# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-027, one row per attendee per training session.

Attendance in ERPNext is not a separate sheet: it lives as the employee rows
of each Training Event, marked Present or Absent when the session is held.
This report reads those rows straight, so the attendance register is the
training records themselves -- never a second transcription of them.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Training Event"), "fieldname": "event", "fieldtype": "Link", "options": "Training Event", "width": 170},
		{"label": _("Training Topic"), "fieldname": "event_name", "fieldtype": "Data", "width": 240},
		{"label": _("Type"), "fieldname": "event_type", "fieldtype": "Data", "width": 90},
		{"label": _("Date"), "fieldname": "training_date", "fieldtype": "Date", "width": 100},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Attendance"), "fieldname": "attendance", "fieldtype": "Data", "width": 90},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	conditions = {}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["start_time"] = ("between", [filters.from_date, filters.to_date])

	rows = frappe.get_all(
		"Training Event",
		filters=conditions,
		fields=[
			"name", "event_name", "type", "start_time",
			"`tabTraining Event Employee`.employee",
			"`tabTraining Event Employee`.employee_name",
			"`tabTraining Event Employee`.attendance",
			"`tabTraining Event Employee`.status",
		],
		# Explicit: session order then attendee, which is how a register is read.
		order_by="start_time asc, `tabTraining Event Employee`.idx asc",
		limit_page_length=0,
	)
	return [
		{
			"event": r.name,
			"event_name": r.event_name,
			"event_type": r.type,
			"training_date": r.start_time.date() if r.start_time else None,
			"employee": r.employee,
			"employee_name": r.employee_name,
			"attendance": r.attendance,
			"status": r.status,
		}
		for r in rows
		if r.employee
	]
