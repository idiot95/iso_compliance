# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Jinja helpers for the Certificate of Conformity.

The certificate is issued against the Delivery Note, but the evidence is born
earlier: at despatch (the row's own Outgoing inspection), at completion (the
PDI on the Manufacture entry) and during production (the Job Card
inspections). The resolver walks the trace the batches already carry --
delivered batch, the Manufacture entry that produced it, its Work Order, that
order's Job Cards -- and returns every inspection on the chain, staged.
"""

import frappe


def _row_batches(row) -> list[str]:
	batches = []
	if row.get("batch_no"):
		batches.append(row.batch_no)
	if row.get("serial_and_batch_bundle"):
		batches += frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": row.serial_and_batch_bundle, "batch_no": ("is", "set")},
			pluck="batch_no",
		)
	return list(dict.fromkeys(batches))


def _manufacture_entries(item_code: str, batches: list[str]) -> list:
	if not batches:
		return []
	entries = set(
		frappe.get_all(
			"Stock Entry Detail",
			filters={
				"batch_no": ("in", batches),
				"is_finished_item": 1,
				"docstatus": 1,
				"item_code": item_code,
			},
			pluck="parent",
		)
	)
	# v16 keeps batch identity in bundles on the finished row
	bundles = frappe.get_all(
		"Serial and Batch Entry", filters={"batch_no": ("in", batches)}, pluck="parent"
	)
	if bundles:
		entries |= set(
			frappe.get_all(
				"Serial and Batch Bundle",
				filters={
					"name": ("in", bundles),
					"voucher_type": "Stock Entry",
					"item_code": item_code,
				},
				pluck="voucher_no",
			)
		)
	if not entries:
		return []
	return frappe.get_all(
		"Stock Entry",
		filters={"name": ("in", list(entries)), "purpose": "Manufacture", "docstatus": 1},
		fields=["name", "work_order"],
	)


def coc_row_inspections(row) -> dict:
	"""Every inspection behind one delivered row, staged for the certificate."""
	out = {"outgoing": None, "pdi": [], "in_process": [], "work_orders": []}

	if row.get("quality_inspection"):
		out["outgoing"] = frappe.get_doc("Quality Inspection", row.quality_inspection)

	for entry in _manufacture_entries(row.item_code, _row_batches(row)):
		for name in frappe.get_all(
			"Quality Inspection",
			filters={
				"reference_type": "Stock Entry",
				"reference_name": entry.name,
				"item_code": row.item_code,
				"docstatus": ("<", 2),
			},
			pluck="name",
		):
			out["pdi"].append(frappe.get_doc("Quality Inspection", name))
		if entry.work_order and entry.work_order not in out["work_orders"]:
			out["work_orders"].append(entry.work_order)

	if out["work_orders"]:
		job_cards = frappe.get_all(
			"Job Card", filters={"work_order": ("in", out["work_orders"])}, pluck="name"
		)
		if job_cards:
			for name in frappe.get_all(
				"Quality Inspection",
				filters={"reference_type": "Job Card", "reference_name": ("in", job_cards), "docstatus": ("<", 2)},
				order_by="report_date asc, name asc",
				pluck="name",
			):
				out["in_process"].append(frappe.get_doc("Quality Inspection", name))
	return out
