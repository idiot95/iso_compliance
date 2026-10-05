# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""REG-015, as a live query rather than a maintained table.

Every goods receipt line is already a Purchase Receipt Item, and its inspection
outcome is already a Quality Inspection. Keeping a second hand-written register
of the same facts means the stores clerk transcribes each GRN twice, and the
two copies drift: a line gets skipped, or an inspection result is entered
against material that was never inspected. Reading the register straight out of
Purchase Receipt and Quality Inspection removes that failure mode.

The register answers the four questions an auditor asks of an incoming
consignment, which is why each has a column of its own: was it inspected (the
report reference and its status), was it identified (batch and the supplier's
heat number), did the certificate arrive where one was required (the MTC
column), and what happened to what failed (the rejected quantity and the
nonconformance reference).
"""

import frappe
from frappe import _

from iso_compliance.overrides.purchase_receipt import item_group_requires_mtc


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Receipt Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("GRN No."), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Receipt", "width": 165},
		{"label": _("Challan No."), "fieldname": "supplier_delivery_note", "fieldtype": "Data", "width": 110},
		{"label": _("Supplier"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 170},
		{"label": _("PO No."), "fieldname": "purchase_order", "fieldtype": "Data", "width": 140},
		{"label": _("Material Description"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Qty. Ordered"), "fieldname": "qty_ordered", "fieldtype": "Float", "width": 95},
		{"label": _("Qty. Received"), "fieldname": "received_qty", "fieldtype": "Float", "width": 95},
		{"label": _("Accepted"), "fieldname": "accepted_qty", "fieldtype": "Float", "width": 85},
		{"label": _("Rejected"), "fieldname": "rejected_qty", "fieldtype": "Float", "width": 85},
		{"label": _("Batch / Heat No."), "fieldname": "batch_heat", "fieldtype": "Data", "width": 150},
		{"label": _("Test Cert."), "fieldname": "mtc", "fieldtype": "Data", "width": 90},
		{"label": _("Inspection Report Ref."), "fieldname": "quality_inspection", "fieldtype": "Link", "options": "Quality Inspection", "width": 165},
		{"label": _("Inspection Status"), "fieldname": "inspection_status", "fieldtype": "Data", "width": 110},
		{"label": _("NCR Ref."), "fieldname": "non_conformance", "fieldtype": "Link", "options": "Non Conformance", "width": 150},
	]


def get_conditions(filters) -> dict:
	conditions = {"docstatus": 1}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ("between", [filters.from_date, filters.to_date])
	elif filters.get("from_date"):
		conditions["posting_date"] = (">=", filters.from_date)
	elif filters.get("to_date"):
		conditions["posting_date"] = ("<=", filters.to_date)
	if filters.get("supplier"):
		conditions["supplier"] = filters.supplier
	return conditions


def get_data(filters):
	# One row per receipt line: the child table is pulled in via tab notation,
	# which the query engine turns into a join on the parent Purchase Receipt.
	rows = frappe.get_all(
		"Purchase Receipt",
		filters=get_conditions(filters),
		fields=[
			"name",
			"posting_date",
			"supplier",
			"supplier_name",
			"supplier_delivery_note",
			"custom_material_test_certificate",
			"`tabPurchase Receipt Item`.name as row_name",
			"`tabPurchase Receipt Item`.purchase_order",
			"`tabPurchase Receipt Item`.purchase_order_item",
			"`tabPurchase Receipt Item`.item_code",
			"`tabPurchase Receipt Item`.item_name",
			"`tabPurchase Receipt Item`.item_group",
			"`tabPurchase Receipt Item`.qty",
			"`tabPurchase Receipt Item`.received_qty",
			"`tabPurchase Receipt Item`.rejected_qty",
			"`tabPurchase Receipt Item`.batch_no",
			"`tabPurchase Receipt Item`.serial_and_batch_bundle",
			"`tabPurchase Receipt Item`.quality_inspection",
			"`tabPurchase Receipt Item`.idx",
		],
		limit_page_length=0,
	)
	if not rows:
		return rows

	# Ordered quantities come from the Purchase Order Item each receipt line
	# references; a line received without a PO simply has no ordered quantity.
	po_qty = _ordered_quantities(rows)
	qi_status = _inspection_status(rows)
	batch_labels = _batch_labels(rows)
	ncr = _nonconformances(rows)
	mtc_required = _mtc_requirement_by_group(rows)

	out = []
	for row in rows:
		row.item_name = row.item_name or row.item_code
		row.qty_ordered = po_qty.get(row.purchase_order_item)
		# `received_qty` is the received stock quantity including rejections;
		# `qty` is the accepted quantity. Older rows may carry only `qty`.
		row.received_qty = row.received_qty or row.qty
		row.accepted_qty = row.qty
		row.inspection_status = qi_status.get(row.quality_inspection) or ""
		row.batch_heat = batch_labels.get(row.row_name) or ""
		row.non_conformance = ncr.get(row.quality_inspection) or ncr.get(row.name)
		row.mtc = _mtc_label(row, mtc_required)

		if filters.get("inspection_status") and row.inspection_status != filters.inspection_status:
			continue
		out.append(row)

	# Explicit. v16 lists default to `creation`, which is not a register order.
	out.sort(key=lambda r: (r.posting_date, r.name, r.idx))
	return out


def _mtc_label(row, mtc_required: dict) -> str:
	"""Attached / Missing where a certificate is required, blank where it is not."""
	if not mtc_required.get(row.item_group):
		return ""
	return _("Attached") if row.custom_material_test_certificate else _("Missing")


def _mtc_requirement_by_group(rows) -> dict:
	groups = {r.item_group for r in rows if r.item_group}
	return {g: item_group_requires_mtc(g) for g in groups}


def _ordered_quantities(rows) -> dict:
	names = {r.purchase_order_item for r in rows if r.purchase_order_item}
	if not names:
		return {}
	return {
		d.name: d.qty
		for d in frappe.get_all(
			"Purchase Order Item",
			filters={"name": ("in", names)},
			fields=["name", "qty"],
			parent_doctype="Purchase Order",
			limit_page_length=0,
		)
	}


def _inspection_status(rows) -> dict:
	names = {r.quality_inspection for r in rows if r.quality_inspection}
	if not names:
		return {}
	return {
		d.name: d.status
		for d in frappe.get_all(
			"Quality Inspection",
			filters={"name": ("in", names)},
			fields=["name", "status"],
			limit_page_length=0,
		)
	}


def _batch_labels(rows) -> dict:
	"""Batch, and the supplier's heat number beside it, per receipt line.

	A batch reaches the line one of two ways depending on how the item is set up:
	the plain `batch_no` field, or a Serial and Batch Bundle holding one entry per
	batch. Both are read, because this site uses both.
	"""
	bundles = {r.serial_and_batch_bundle for r in rows if r.serial_and_batch_bundle}
	by_row: dict[str, list[str]] = {}
	batch_ids: set[str] = set()

	for row in rows:
		if row.batch_no:
			by_row.setdefault(row.row_name, []).append(row.batch_no)
			batch_ids.add(row.batch_no)

	if bundles:
		entries = frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": ("in", bundles)},
			fields=["parent", "batch_no"],
			parent_doctype="Serial and Batch Bundle",
			limit_page_length=0,
		)
		per_bundle: dict[str, list[str]] = {}
		for e in entries:
			if e.batch_no:
				per_bundle.setdefault(e.parent, []).append(e.batch_no)
				batch_ids.add(e.batch_no)
		for row in rows:
			for batch in per_bundle.get(row.serial_and_batch_bundle, []):
				by_row.setdefault(row.row_name, []).append(batch)

	heat = {}
	if batch_ids:
		heat = {
			d.name: d.custom_heat_no
			for d in frappe.get_all(
				"Batch",
				filters={"name": ("in", batch_ids)},
				fields=["name", "custom_heat_no"],
				limit_page_length=0,
			)
		}

	labels = {}
	for row_name, batches in by_row.items():
		seen, parts = set(), []
		for batch in batches:
			if batch in seen:
				continue
			seen.add(batch)
			h = heat.get(batch)
			parts.append(f"{batch} ({h})" if h and h != batch else batch)
		labels[row_name] = ", ".join(parts)
	return labels


def _nonconformances(rows) -> dict:
	"""NCRs keyed by the inspection and by the receipt they were raised against."""
	qis = {r.quality_inspection for r in rows if r.quality_inspection}
	prs = {r.name for r in rows}
	if not (qis or prs):
		return {}

	out = {}
	for d in frappe.get_all(
		"Non Conformance",
		or_filters={
			"custom_quality_inspection": ("in", qis or {""}),
			"custom_purchase_receipt": ("in", prs or {""}),
		},
		fields=["name", "custom_quality_inspection", "custom_purchase_receipt"],
		limit_page_length=0,
	):
		# The inspection is the more precise key, so it wins where both are set.
		if d.custom_purchase_receipt:
			out.setdefault(d.custom_purchase_receipt, d.name)
		if d.custom_quality_inspection:
			out[d.custom_quality_inspection] = d.name
	return out
