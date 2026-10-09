# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Scheduled jobs. Daily: draft the supplier evaluations that have come due."""

import frappe
from frappe.utils import add_days, today


def create_due_supplier_evaluations():
	"""A supplier whose re-approval date is within a week (or past) gets a
	drafted FRM-005 evaluation, once -- an existing draft for the supplier
	blocks a duplicate. The 'Supplier Evaluation Due' notification fires on
	the insert and tells Purchase and Quality."""
	due = frappe.get_all(
		"Supplier",
		filters={
			"disabled": 0,
			"custom_reapproval_due": ("<=", add_days(today(), 7)),
		},
		fields=["name", "custom_category"],
		limit_page_length=0,
	)
	for supplier in due:
		if frappe.db.exists("Supplier Evaluation", {"supplier": supplier.name, "docstatus": 0}):
			continue
		# The re-evaluation starts where the last one left off: same category
		# (so the same template), same product line.
		last = frappe.db.get_value(
			"Supplier Evaluation",
			{"supplier": supplier.name, "docstatus": 1},
			["category", "product_service"],
			order_by="evaluation_date desc, creation desc",
			as_dict=True,
		) or {}
		doc = frappe.new_doc("Supplier Evaluation")
		doc.supplier = supplier.name
		doc.evaluation_type = "Periodic"
		doc.category = supplier.custom_category or last.get("category") or "Non-Critical"
		doc.product_service = last.get("product_service")
		doc.flags.ignore_permissions = True
		doc.insert()
