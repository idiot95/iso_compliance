# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The Sales Order's chosen BOM survives into the Work Order.

A Sales Order row can name the BOM to build against -- the customer-variant
drawing rather than the item's default. ERPNext's make-work-order flow ignores
it (get_work_order_items reads only get_default_bom), so an order sold as the
Marathon variant would be manufactured to the Kirloskar default. This hook
runs when a Work Order is created against a Sales Order row: if the row chose
a BOM and the Work Order carries only the automatic default, the chosen BOM
replaces it and the operations are rebuilt from it. A BOM somebody set on the
Work Order deliberately -- anything that is not the plain default -- is never
overridden.
"""

import frappe
from erpnext.stock.get_item_details import get_default_bom


def apply_sales_order_bom(doc, method=None):
	if doc.docstatus != 0 or not (doc.sales_order and doc.sales_order_item and doc.production_item):
		return

	chosen = frappe.db.get_value("Sales Order Item", doc.sales_order_item, "bom_no")
	if not chosen or chosen == doc.bom_no:
		return

	# only replace the automatic default; a manual choice on the WO stands
	if doc.bom_no and doc.bom_no != get_default_bom(doc.production_item):
		return

	doc.bom_no = chosen
	# operations were built from the default before insert; rebuild from the
	# chosen BOM (required items rebuild in validate for a draft anyway)
	doc.set_work_order_operations()
