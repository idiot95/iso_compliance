# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The suppliers that need evaluating, biggest spend first (SOP-005).

Purchase Orders lock unless the supplier is Approved, so this is the
worklist that keeps purchasing moving: every enabled supplier we bought from
in the last 12 months that isn't Approved, or whose review is due within 30
days, with the open evaluation if one is already drafted. Ranking by spend
puts the suppliers that matter -- and that would most often need an override
-- at the top.
"""

import frappe
from frappe import _
from frappe.utils import add_days, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), rows(filters)


def columns():
	return [
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 220},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 100},
		{"fieldname": "spend", "label": _("Spend, 12 months"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "orders", "label": _("Orders"), "fieldtype": "Int", "width": 70},
		{"fieldname": "last_evaluated", "label": _("Last Evaluated"), "fieldtype": "Date", "width": 110},
		{"fieldname": "next_review", "label": _("Next Review"), "fieldtype": "Date", "width": 110},
		{"fieldname": "open_evaluation", "label": _("Open Evaluation"), "fieldtype": "Link", "options": "Supplier Evaluation", "width": 190},
		{"fieldname": "action", "label": _("Next Step"), "fieldtype": "Data", "width": 150},
	]


def rows(filters):
	since = add_days(today(), -365)
	review_soon = add_days(today(), 30)
	conditions = ""
	values = {"since": since, "review_soon": review_soon}
	if filters.get("category"):
		conditions += " and s.custom_category = %(category)s"
		values["category"] = filters.category
	if filters.get("status"):
		conditions += " and ifnull(s.custom_approval_status, '') = %(status)s"
		values["status"] = "" if filters.status == "Not evaluated" else filters.status

	data = frappe.db.sql(
		f"""
		select s.name as supplier, s.custom_approval_status as status, s.custom_category as category,
			s.custom_reapproval_due as next_review,
			sum(po.base_grand_total) as spend, count(po.name) as orders
		from `tabSupplier` s
		join `tabPurchase Order` po on po.supplier = s.name and po.docstatus = 1
			and po.transaction_date >= %(since)s
		where s.disabled = 0
			and (ifnull(s.custom_approval_status, '') != 'Approved'
				or s.custom_reapproval_due is null or s.custom_reapproval_due <= %(review_soon)s)
			{conditions}
		group by s.name
		order by spend desc
		""",
		values,
		as_dict=True,
	)
	if not data:
		return []

	names = [row.supplier for row in data]
	last = dict(
		frappe.db.sql(
			"""select supplier, max(evaluation_date) from `tabSupplier Evaluation`
			where docstatus = 1 and supplier in %(names)s group by supplier""",
			{"names": names},
		)
	)
	drafts = dict(
		frappe.db.sql(
			"""select supplier, max(name) from `tabSupplier Evaluation`
			where docstatus = 0 and supplier in %(names)s group by supplier""",
			{"names": names},
		)
	)
	for row in data:
		row.status = row.status or _("Not evaluated")
		row.last_evaluated = last.get(row.supplier)
		row.open_evaluation = drafts.get(row.supplier)
		if row.open_evaluation:
			row.action = _("Finish evaluation")
		elif row.status == "Suspended":
			row.action = _("Re-evaluate to lift")
		elif row.status == "Approved":
			row.action = _("Review due")
		else:
			row.action = _("Evaluate")
	return data
