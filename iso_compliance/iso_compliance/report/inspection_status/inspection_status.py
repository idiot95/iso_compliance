# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""What waits in Inspection Required, and whose move it is (SOP-006).

One row per receipt row or finished-goods row that posted into Inspection
Required, oldest first:

- **To inspect**: Engineering's turn (no inspection yet, or one still in draft).
- **To rack**: inspected; Stores racks it and posts the drafted transfer.
- **Done**: the transfer is posted.

"Waiting" counts days since posting, so everyone sees how long it has sat.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, today

from iso_compliance.overrides.inspection_flow import INSPECTION_WAREHOUSE

STATUS_OPEN = ("To inspect", "To rack")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), rows(filters)


def columns():
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "waiting", "label": _("Waiting, days"), "fieldtype": "Int", "width": 100},
		{"fieldname": "stage", "label": _("Stage"), "fieldtype": "Data", "width": 80},
		{"fieldname": "reference_type", "label": _("Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "reference_name", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "reference_type", "width": 170},
		{"fieldname": "posting_date", "label": _("Posted"), "fieldtype": "Date", "width": 95},
		{"fieldname": "party", "label": _("Supplier / Work Order"), "fieldtype": "Data", "width": 170},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "assigned_to", "label": _("Assigned To"), "fieldtype": "Data", "width": 130},
		{"fieldname": "inspection", "label": _("Inspection"), "fieldtype": "Link", "options": "Quality Inspection", "width": 160},
		{"fieldname": "transfer", "label": _("Transfer"), "fieldtype": "Link", "options": "Stock Entry", "width": 150},
	]


def rows(filters):
	since = filters.get("from_date") or add_days(today(), -90)
	values = {"since": since, "wh": INSPECTION_WAREHOUSE}
	receipts = frappe.db.sql(
		"""
		select 'Incoming' as stage, 'Purchase Receipt' as reference_type, pr.name as reference_name,
			pr.posting_date, pr.supplier_name as party, pri.name as row_name,
			pri.item_code, pri.item_name, pri.qty
		from `tabPurchase Receipt Item` pri
		join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1 and pr.is_return = 0
		join `tabWarehouse` w on w.name = pri.warehouse and w.warehouse_name = %(wh)s
		where pr.posting_date >= %(since)s and pri.qty > 0
		""",
		values,
		as_dict=True,
	)
	finished = frappe.db.sql(
		"""
		select 'Final' as stage, 'Stock Entry' as reference_type, se.name as reference_name,
			se.posting_date, se.work_order as party, sed.name as row_name,
			sed.item_code, sed.item_name, sed.qty
		from `tabStock Entry Detail` sed
		join `tabStock Entry` se on se.name = sed.parent and se.docstatus = 1 and se.purpose = 'Manufacture'
		join `tabWarehouse` w on w.name = sed.t_warehouse and w.warehouse_name = %(wh)s
		where se.posting_date >= %(since)s and sed.is_finished_item = 1 and sed.qty > 0
		""",
		values,
		as_dict=True,
	)
	data = [r for r in receipts + finished if not filters.get("stage") or r.stage == filters.stage]
	if not data:
		return []

	inspections = {
		q.child_row_reference: q
		for q in frappe.get_all(
			"Quality Inspection",
			filters={"child_row_reference": ("in", [r.row_name for r in data]), "docstatus": ("<", 2)},
			fields=["name", "child_row_reference", "docstatus", "custom_transfer_entry"],
		)
	}
	transfers = dict(
		frappe.get_all(
			"Stock Entry",
			filters={"name": ("in", [q.custom_transfer_entry for q in inspections.values() if q.custom_transfer_entry])},
			fields=["name", "docstatus"],
			as_list=True,
		)
	)
	todos = {}
	for t in frappe.get_all(
		"ToDo",
		filters={"status": "Open", "reference_name": ("in", list({r.reference_name for r in data}))},
		fields=["reference_name", "allocated_to"],
	):
		todos.setdefault(t.reference_name, []).append(frappe.utils.get_fullname(t.allocated_to))

	out = []
	for r in data:
		q = inspections.get(r.row_name)
		transfer = q and q.custom_transfer_entry
		if not q or q.docstatus == 0:
			status = "To inspect"
		elif transfer and transfers.get(transfer) == 1:
			status = "Done"
		else:
			status = "To rack"
		if filters.get("status") == "Open" and status not in STATUS_OPEN:
			continue
		if filters.get("status") not in (None, "", "Open") and status != filters.status:
			continue
		r.update(
			status=status,
			waiting=date_diff(today(), r.posting_date) if status != "Done" else None,
			inspection=q and q.name,
			transfer=transfer,
			assigned_to=", ".join(todos.get(r.reference_name, [])) if status == "To inspect" else "",
			qty=flt(r.qty),
		)
		out.append(r)
	order = {"To inspect": 0, "To rack": 1, "Done": 2}
	out.sort(key=lambda r: (order[r.status], r.posting_date))
	return out
