# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The make-Work-Order dialog shows the BOM that will actually be used.

The dialog fills itself from get_work_order_items, which reads only the
item's default BOM -- so a user who chose a customer-variant BOM on the Sales
Order row saw the wrong BOM in the dialog even though the before_insert hook
would build correctly. This wrapper calls the core function and then swaps in
each row's chosen BOM, so what the dialog displays, what it submits, and what
the Work Order builds are the same thing. The raw-material-request dialog
uses the same endpoint and is corrected by the same swap.
"""

import frappe
from erpnext.selling.doctype.sales_order.sales_order import (
	get_work_order_items as _core_get_work_order_items,
)


@frappe.whitelist()
def get_work_order_items(sales_order, for_raw_material_request=0):
	items = _core_get_work_order_items(sales_order, for_raw_material_request)
	if not items:
		return items

	chosen = {
		row.name: row.bom_no
		for row in frappe.get_all(
			"Sales Order Item",
			filters={"parent": sales_order, "bom_no": ("is", "set")},
			fields=["name", "bom_no"],
		)
	}
	for item in items:
		selected = chosen.get(item.get("sales_order_item") or item.get("name"))
		if selected:
			item["bom"] = selected
	return items
