# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-006, the Employee Competency Matrix, as a live query rather than a
maintained table.

The paper register is a Word table that lists each employee's designation,
experience, qualification, skills and training needs. A table kept by hand goes
stale the day someone is hired, trained, or re-assessed and nobody edits the
file. Reading the same columns out of Employee Skill Map records means the
matrix is only ever as wrong as the records themselves, which is the failure
mode an assessor can actually audit.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Data", "width": 150},
		{"label": _("Exp. (Yrs)"), "fieldname": "experience_yrs", "fieldtype": "Data", "width": 85},
		{"label": _("Qualification"), "fieldname": "qualification", "fieldtype": "Data", "width": 180},
		{"label": _("Skill"), "fieldname": "skill_actual", "fieldtype": "Data", "width": 300},
		{"label": _("Training Need"), "fieldname": "training_need", "fieldtype": "Data", "width": 300},
	]


def get_data(filters):
	skill_maps = frappe.get_all(
		"Employee Skill Map",
		fields=["name", "employee", "employee_name", "designation"],
		order_by="employee_name asc, name asc",
		limit_page_length=0,
	)
	if not skill_maps:
		return []

	map_names = [d.name for d in skill_maps]
	employee_ids = list({d.employee for d in skill_maps if d.employee})

	# One query per child table, keyed back to the parent, instead of a
	# get_doc round trip per row.
	employees = {}
	qualifications = {}
	if employee_ids:
		employees = {
			d.name: d
			for d in frappe.get_all(
				"Employee",
				filters={"name": ("in", employee_ids)},
				fields=["name", "date_of_joining"],
				limit_page_length=0,
			)
		}
		# Employee has no flat qualification field; it keeps an `education`
		# child table, one row per certificate.
		for d in frappe.get_all(
			"Employee Education",
			filters={"parent": ("in", employee_ids), "parenttype": "Employee"},
			fields=["parent", "qualification"],
			order_by="parent asc, idx asc",
			limit_page_length=0,
		):
			if d.qualification:
				qualifications.setdefault(d.parent, []).append(d.qualification)

	skills = {}
	for d in frappe.get_all(
		"Employee Skill",
		filters={"parent": ("in", map_names), "parenttype": "Employee Skill Map"},
		fields=["parent", "skill", "proficiency"],
		order_by="parent asc, idx asc",
		limit_page_length=0,
	):
		if d.skill:
			skills.setdefault(d.parent, []).append(
				"{0} ({1}/5)".format(d.skill, format_proficiency(d.proficiency))
			)

	trainings = {}
	for d in frappe.get_all(
		"Employee Training",
		filters={"parent": ("in", map_names), "parenttype": "Employee Skill Map"},
		fields=["parent", "training"],
		order_by="parent asc, idx asc",
		limit_page_length=0,
	):
		# Training Event is autonamed from event_name, so the link value is
		# already the readable designation of the training.
		if d.training:
			trainings.setdefault(d.parent, []).append(d.training)

	data = []
	for skill_map in skill_maps:
		employee = employees.get(skill_map.employee)
		data.append({
			"employee_name": skill_map.employee_name,
			"designation": skill_map.designation,
			"experience_yrs": get_experience_yrs(employee),
			"qualification": "; ".join(qualifications.get(skill_map.employee, [])),
			"skill_actual": "; ".join(skills.get(skill_map.name, [])),
			"training_need": "; ".join(trainings.get(skill_map.name, [])),
		})
	return data


def get_experience_yrs(employee):
	if not employee or not employee.date_of_joining:
		return ""
	return "{0:.1f}".format(date_diff(today(), employee.date_of_joining) / 365.25)


def format_proficiency(proficiency):
	# Rating fields store 0-1; the stars the assessor sees are that times 5.
	stars = flt(proficiency)
	if stars <= 1:
		stars = stars * 5
	return "{0:g}".format(stars)
