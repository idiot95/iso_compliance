# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-015, as a live query rather than a maintained table.

Every goods receipt line is already a Purchase Receipt Item, and its inspection
outcome is already a Quality Inspection. Keeping a second hand-written register
of the same facts means the stores clerk transcribes each GRN twice, and the
two copies drift: a line gets skipped, or an inspection result is entered
against material that was never inspected. Reading the register straight out of
Purchase Receipt and Quality Inspection removes that failure mode.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Receipt Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("GRN No."), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Receipt", "width": 175},
		{"label": _("Supplier"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
		{"label": _("PO No."), "fieldname": "purchase_order", "fieldtype": "Data", "width": 150},
		{"label": _("Material Description"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Qty. Ordered"), "fieldname": "qty_ordered", "fieldtype": "Float", "width": 100},
		{"label": _("Qty. Received"), "fieldname": "received_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Inspection Report Ref."), "fieldname": "quality_inspection", "fieldtype": "Link", "options": "Quality Inspection", "width": 175},
		{"label": _("Inspection Status"), "fieldname": "inspection_status", "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	# One row per receipt line: the child table is pulled in via tab notation,
	# which the query engine turns into a join on the parent Purchase Receipt.
	rows = frappe.get_all(
		"Purchase Receipt",
		filters={"docstatus": 1},
		fields=[
			"name",
			"posting_date",
			"supplier_name",
			"`tabPurchase Receipt Item`.purchase_order",
			"`tabPurchase Receipt Item`.purchase_order_item",
			"`tabPurchase Receipt Item`.item_code",
			"`tabPurchase Receipt Item`.item_name",
			"`tabPurchase Receipt Item`.qty",
			"`tabPurchase Receipt Item`.received_qty",
			"`tabPurchase Receipt Item`.quality_inspection",
			"`tabPurchase Receipt Item`.idx",
		],
		limit_page_length=0,
	)

	# Ordered quantities come from the Purchase Order Item each receipt line
	# references; a line received without a PO simply has no ordered quantity.
	po_item_names = {r.purchase_order_item for r in rows if r.purchase_order_item}
	po_qty = {}
	if po_item_names:
		po_qty = {
			d.name: d.qty
			for d in frappe.get_all(
				"Purchase Order Item",
				filters={"name": ("in", po_item_names)},
				fields=["name", "qty"],
				parent_doctype="Purchase Order",
				limit_page_length=0,
			)
		}

	qi_names = {r.quality_inspection for r in rows if r.quality_inspection}
	qi_status = {}
	if qi_names:
		qi_status = {
			d.name: d.status
			for d in frappe.get_all(
				"Quality Inspection",
				filters={"name": ("in", qi_names)},
				fields=["name", "status"],
				limit_page_length=0,
			)
		}

	for row in rows:
		row.item_name = row.item_name or row.item_code
		row.qty_ordered = po_qty.get(row.purchase_order_item)
		# `received_qty` is the received stock quantity including rejections;
		# `qty` is the accepted quantity. Older rows may carry only `qty`.
		row.received_qty = row.received_qty or row.qty
		row.inspection_status = qi_status.get(row.quality_inspection) or ""

	# Explicit. v16 lists default to `creation`, which is not a register order.
	rows.sort(key=lambda r: (r.posting_date, r.name, r.idx))
	return rows
