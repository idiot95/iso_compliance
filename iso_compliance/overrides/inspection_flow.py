# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-006 as practised from 2026-10-14: post first, inspect after.

Anything whose Item Group needs quality control waits in the **Inspection
Required** warehouse and leaves only through its inspection:

- **Receipt.** Stores posts the Purchase Receipt after checking quantity,
  material and appearance (ticked on the receipt). Rows of QC items post into
  Inspection Required; the warehouse they were meant for is kept on the row.
  Posting flags the receipt as waiting; hcc's Assignment Rule assigns it to
  Engineering, and it shows on their My Work card. Nothing opens by itself:
  the engineer starts the inspection from the receipt's Inspect button.
- **Production.** Finishing a Work Order (ERPNext's own Finish → Manufacture
  entry) sends the finished item of a QC group into Inspection Required; by-
  products keep their own target. The entry is flagged and assigned the same
  way, for the final inspection.
- **Release.** Submitting the inspection drafts one Material Transfer out of
  Inspection Required: the accepted quantity to the kept warehouse (Stores, or
  the Work Order's target), the rejected quantity to Rejected. Stores posts it
  after racking. Nothing else may take stock out of Inspection Required. Once
  every waiting row of a document is inspected its flag clears and the
  assignment closes.

ERPNext supports the order natively once "Allow to make Quality Inspection
after Purchase / Delivery" is on; the item flag "Inspection Required before
Purchase" is kept in step with the Item Group flag, because ERPNext refuses an
inspection against a receipt without it.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

INSPECTION_WAREHOUSE = "Inspection Required"
QI = "Quality Inspection"
MODULE = "ISO Compliance"

FIELDS = {
	"Item Group": [
		dict(fieldname="custom_qc_required", fieldtype="Check", label="Quality inspection required",
		     insert_after="custom_issue_mtc",
		     description="Receipts and finished production of items in this group (and its sub-groups) wait in "
		                 "Inspection Required until Engineering inspects them (SOP-006)."),
	],
	"Purchase Receipt": [
		dict(fieldname="custom_receiving_section", fieldtype="Section Break", label="Receiving checks",
		     insert_after="custom_recevied_by"),
		dict(fieldname="custom_check_quantity", fieldtype="Check", label="Right quantity",
		     insert_after="custom_receiving_section"),
		dict(fieldname="custom_check_material", fieldtype="Check", label="Right material",
		     insert_after="custom_check_quantity"),
		dict(fieldname="custom_check_visual", fieldtype="Check", label="Visual check OK",
		     insert_after="custom_check_material",
		     description="Packaging and material undamaged. Green sticker on items that need no inspection."),
		dict(fieldname="custom_inspection_pending", fieldtype="Check", label="Waiting for inspection",
		     insert_after="custom_check_visual", read_only=1, hidden=1, allow_on_submit=1, no_copy=1),
	],
	"Purchase Receipt Item": [
		dict(fieldname="custom_release_warehouse", fieldtype="Link", options="Warehouse",
		     label="Warehouse after inspection", insert_after="warehouse", read_only=1,
		     depends_on="custom_release_warehouse"),
	],
	"Stock Entry Detail": [
		dict(fieldname="custom_release_warehouse", fieldtype="Link", options="Warehouse",
		     label="Warehouse after inspection", insert_after="t_warehouse", read_only=1,
		     depends_on="custom_release_warehouse"),
	],
	"Stock Entry": [
		dict(fieldname="custom_quality_inspection", fieldtype="Link", options=QI,
		     label="Released by inspection", insert_after="stock_entry_type", read_only=1,
		     depends_on="custom_quality_inspection"),
		dict(fieldname="custom_inspection_pending", fieldtype="Check", label="Waiting for inspection",
		     insert_after="custom_quality_inspection", read_only=1, hidden=1, allow_on_submit=1, no_copy=1),
	],
	QI: [
		dict(fieldname="custom_accepted_qty", fieldtype="Float", label="Accepted quantity",
		     insert_after="custom_disposition", depends_on="custom_lot_qty",
		     description="Moves out of Inspection Required to stores or finished goods."),
		dict(fieldname="custom_rejected_qty", fieldtype="Float", label="Rejected quantity",
		     insert_after="custom_accepted_qty", depends_on="custom_lot_qty",
		     description="Moves to the Rejected warehouse."),
		dict(fieldname="custom_transfer_entry", fieldtype="Link", options="Stock Entry",
		     label="Release transfer", insert_after="custom_rejected_qty", read_only=1,
		     depends_on="custom_transfer_entry"),
	],
}


def create_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	for rows in FIELDS.values():
		for f in rows:
			f["module"] = MODULE
	create_custom_fields(FIELDS, update=True)


# ---------------------------------------------------------------- lookups --


def _warehouse(company: str | None, base: str) -> str | None:
	if not company:
		return None
	name = f"{base} - {frappe.get_cached_value('Company', company, 'abbr')}"
	return name if frappe.db.exists("Warehouse", name) else None


def inspection_warehouse(company):
	return _warehouse(company, INSPECTION_WAREHOUSE)


def group_requires_qc(item_group: str | None) -> bool:
	from iso_compliance.overrides.purchase_receipt import _group_and_ancestors

	return any(frappe.get_cached_value("Item Group", g, "custom_qc_required") for g in _group_and_ancestors(item_group))


def qc_required(item_code: str | None) -> bool:
	return bool(item_code) and group_requires_qc(frappe.get_cached_value("Item", item_code, "item_group"))


def _is_inspection_warehouse(warehouse: str | None) -> bool:
	return bool(warehouse) and frappe.get_cached_value("Warehouse", warehouse, "warehouse_name") == INSPECTION_WAREHOUSE


# ------------------------------------------------------------------- Item --


def item_validate(doc, method=None):
	"""Keep ERPNext's per-item flag in step with the group's rule."""
	if doc.item_group and doc.is_stock_item:
		doc.inspection_required_before_purchase = 1 if group_requires_qc(doc.item_group) else 0
	ensure_item_barcode(doc)


def ensure_item_barcode(doc):
	"""Items without batches carry their item code as a barcode, so the label's
	barcode resolves in ERPNext's scanner (it matches Item Barcode, not item codes)."""
	code = doc.item_code or doc.name
	if doc.has_batch_no or not doc.is_stock_item or not code:
		return
	if any(b.barcode == code for b in doc.get("barcodes") or []):
		return
	if frappe.db.exists("Item Barcode", {"barcode": code}):  # taken by another item: leave it
		return
	doc.append("barcodes", {"barcode": code})


# -------------------------------------------------------- Purchase Receipt --


def pr_validate(doc, method=None):
	"""QC rows post into Inspection Required; the intended warehouse is kept."""
	if doc.get("is_return"):
		return
	wh = inspection_warehouse(doc.company)
	if not wh:
		return
	for row in doc.get("items") or []:
		if not qc_required(row.item_code):
			continue
		if row.warehouse and row.warehouse != wh:
			row.custom_release_warehouse = row.warehouse
		row.custom_release_warehouse = row.custom_release_warehouse or _warehouse(doc.company, "Stores")
		row.warehouse = wh


def pr_before_submit(doc, method=None):
	if doc.get("is_return"):
		return
	missing = [label for field, label in (("custom_check_quantity", _("Right quantity")),
	                                      ("custom_check_material", _("Right material")),
	                                      ("custom_check_visual", _("Visual check OK"))) if not doc.get(field)]
	if missing:
		frappe.throw(_("Tick the receiving checks before posting: {0}.").format(", ".join(missing)),
		             title=_("Receiving checks"))
	# set before submit: the Assignment Rule runs on on_update, ahead of on_submit
	doc.custom_inspection_pending = int(any(_is_inspection_warehouse(r.warehouse) and flt(r.qty) for r in doc.items))


def pr_on_submit(doc, method=None):
	if not doc.get("is_return") and doc.get("custom_inspection_pending"):
		_tell_waiting(doc, _("{0} waits in Inspection Required.").format(doc.name))


def _tell_waiting(doc, text):
	who = frappe.get_all("ToDo", filters={"reference_type": doc.doctype, "reference_name": doc.name, "status": "Open"},
	                     pluck="allocated_to")
	frappe.msgprint(" ".join([text, _("Assigned to {0} for inspection.").format(", ".join(map(frappe.utils.get_fullname, who)))
	                          if who else _("Engineering inspects it from the Inspect button.")]),
	                indicator="blue", title=_("Inspection required"))


# ---------------------------------------------------- Manufacture (Finish) --


def se_before_validate(doc, method=None):
	"""Finished items of QC groups go to Inspection Required; by-products keep their
	target. Before validate, so ERPNext builds the batch bundle for that warehouse."""
	if doc.purpose == "Manufacture" and doc.docstatus == 0:
		wh = inspection_warehouse(doc.company)
		for row in doc.get("items") or []:
			if wh and row.is_finished_item and row.t_warehouse and qc_required(row.item_code):
				if row.t_warehouse != wh:
					row.custom_release_warehouse = row.t_warehouse
				row.t_warehouse = wh
				_move_draft_bundle(row.get("serial_and_batch_bundle"), wh)
				# inspected afterwards, in Inspection Required: not before posting (a BOM's
				# "Quality Inspection Required" would otherwise demand one first)
				doc.inspection_required = 0


def _move_draft_bundle(bundle, warehouse):
	"""ERPNext builds the finished item's batch bundle with the Work Order's
	target before any hook runs; a draft bundle follows the row."""
	if not bundle or frappe.db.get_value("Serial and Batch Bundle", bundle, "docstatus") != 0:
		return
	frappe.db.set_value("Serial and Batch Bundle", bundle, "warehouse", warehouse, update_modified=False)
	frappe.db.sql("update `tabSerial and Batch Entry` set warehouse = %s where parent = %s", (warehouse, bundle))


def se_before_submit(doc, method=None):
	if doc.purpose == "Manufacture":
		doc.custom_inspection_pending = int(any(r.is_finished_item and _is_inspection_warehouse(r.t_warehouse)
		                                        for r in doc.items))


def se_validate(doc, method=None):
	"""Nothing leaves Inspection Required except through its inspection's transfer."""
	_guard_inspection_stock(doc, [r.s_warehouse for r in doc.get("items") or []])


def se_on_submit(doc, method=None):
	if doc.purpose == "Manufacture" and doc.get("custom_inspection_pending"):
		_tell_waiting(doc, _("The finished goods wait in Inspection Required."))


def se_on_cancel(doc, method=None):
	"""A cancelled Manufacture entry takes its started, unsubmitted inspections with it."""
	if doc.purpose != "Manufacture":
		return
	for name in frappe.get_all(QI, filters={"reference_type": "Stock Entry", "reference_name": doc.name, "docstatus": 0}, pluck="name"):
		frappe.delete_doc(QI, name, ignore_permissions=True, force=True)


def dn_validate(doc, method=None):
	_guard_inspection_stock(doc, [r.warehouse for r in doc.get("items") or []])


def _guard_inspection_stock(doc, warehouses):
	if not any(_is_inspection_warehouse(w) for w in warehouses if w):
		return
	qi = doc.get("custom_quality_inspection") if doc.doctype == "Stock Entry" else None
	if qi and frappe.db.get_value(QI, qi, "docstatus") == 1:
		return
	frappe.throw(_("Stock in Inspection Required leaves only through its quality inspection. "
	               "Submit the inspection; it drafts the transfer to stores and Rejected."),
	             title=_("Awaiting inspection"))


def _wo_customer(work_order):
	so = work_order and frappe.db.get_value("Work Order", work_order, "sales_order")
	return so and frappe.db.get_value("Sales Order", so, "customer")


def _row_batch(row) -> str | None:
	if row.get("batch_no"):
		return row.batch_no
	bundle = row.get("serial_and_batch_bundle")
	if not bundle:
		return None
	batches = frappe.get_all("Serial and Batch Entry", filters={"parent": bundle}, pluck="batch_no")
	return batches[0] if len(set(batches)) == 1 else None


def _open_inspection(*, inspection_type, stage, reference_type, reference_name, row, item_code, lot, batch_no,
                     bom_no=None, extra=None, sample=None) -> str:
	"""A draft inspection for one waiting row, on the item's plan; an item with
	no plan at all gets a one-off plan, built in the inspection. (An item with
	only an old-format plan keeps it until those are phased out.)"""
	from iso_compliance.qi.inspection import default_sample, one_off_plan, resolve_template

	existing = frappe.db.get_value(QI, {"reference_type": reference_type, "reference_name": reference_name,
	                                    "child_row_reference": row, "docstatus": ("<", 2)})
	if existing:
		return existing
	template = resolve_template(item_code, bom_no) or one_off_plan(item_code)
	qi = frappe.get_doc({
		"doctype": QI,
		"inspection_type": inspection_type,
		"custom_stage": stage,
		"reference_type": reference_type,
		"reference_name": reference_name,
		"child_row_reference": row,
		"item_code": item_code,
		"batch_no": batch_no,
		"sample_size": cint(sample) or default_sample(lot),
		"report_date": frappe.utils.nowdate(),
		"inspected_by": frappe.session.user,
		"quality_inspection_template": template,
		"custom_lot_qty": lot,
		**{k: v for k, v in (extra or {}).items() if v},
	})
	qi.insert()
	return qi.name


@frappe.whitelist()
def waiting(reference_type: str, reference_name: str) -> list[dict]:
	"""The rows of a receipt or Manufacture entry still in Inspection Required, with
	the state of their inspection: none, started (draft) or done."""
	from iso_compliance.qi.inspection import default_sample

	if reference_type not in ("Purchase Receipt", "Stock Entry"):
		return []
	frappe.has_permission(reference_type, "read", doc=reference_name, throw=True)
	doc = frappe.get_doc(reference_type, reference_name)
	if doc.docstatus != 1:
		return []
	field = "warehouse" if reference_type == "Purchase Receipt" else "t_warehouse"
	out = []
	for r in doc.items:
		if not _is_inspection_warehouse(r.get(field)) or not flt(r.qty):
			continue
		qi = frappe.db.get_value(QI, {"reference_type": reference_type, "reference_name": reference_name,
		                              "child_row_reference": r.name, "docstatus": ("<", 2)}, ["name", "docstatus"], as_dict=True)
		out.append({"row": r.name, "idx": r.idx, "item_code": r.item_code, "item_name": r.item_name, "qty": flt(r.qty),
		            "default_sample": default_sample(flt(r.qty)),
		            "uom": r.get("stock_uom") or r.get("uom"), "release": r.get("custom_release_warehouse"),
		            "inspection": qi and qi.name, "state": "done" if qi and qi.docstatus == 1 else "started" if qi else "todo"})
	return out


@frappe.whitelist()
def waiting_for_work_order(work_order: str) -> list[dict]:
	"""Finished goods of a Work Order waiting for their final inspection."""
	frappe.has_permission("Work Order", "read", doc=work_order, throw=True)
	out = []
	for se in frappe.get_all("Stock Entry", filters={"work_order": work_order, "purpose": "Manufacture", "docstatus": 1,
	                                                 "custom_inspection_pending": 1}, pluck="name", order_by="posting_date"):
		out += [dict(r, stock_entry=se) for r in waiting("Stock Entry", se) if r["state"] != "done"]
	return out


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def work_orders_waiting(doctype, txt, searchfield, start, page_len, filters):
	"""Work Order picker of the new-inspection dialog: Work Orders with finished
	goods still waiting in Inspection Required. Finishing the Work Order is what
	puts them there, so a fully finished (Completed) Work Order is the usual case."""
	se = frappe.qb.DocType("Stock Entry")
	wo = frappe.qb.DocType("Work Order")
	return (
		frappe.qb.from_(wo)
		.join(se).on(se.work_order == wo.name)
		.select(wo.name, wo.production_item, wo.status)
		.distinct()
		.where((se.purpose == "Manufacture") & (se.docstatus == 1) & (se.custom_inspection_pending == 1)
		       & (wo.docstatus == 1)
		       & (wo.name.like(f"%{txt}%") | wo.production_item.like(f"%{txt}%")))
		.orderby(wo.name, order=frappe.qb.desc)
		.limit(page_len).offset(start)
		.run()
	)


@frappe.whitelist()
def start_inspection(reference_type: str, reference_name: str, row: str, sample_size: int | None = None) -> str:
	"""Engineering starts (or resumes) the inspection of one waiting row, on the
	sample they chose (the settings' percentage of the lot when not given)."""
	from iso_compliance.qi.inspection import _check_can_inspect

	_check_can_inspect()
	w = next((r for r in waiting(reference_type, reference_name) if r["row"] == row), None)
	if not w:
		frappe.throw(_("That row is not waiting in Inspection Required."), title=_("Nothing to inspect"))
	if w["inspection"]:
		return w["inspection"]
	if sample_size is not None and not 1 <= cint(sample_size) <= max(1, w["qty"]):
		frappe.throw(_("The sample must be between 1 and the lot ({0}).").format(frappe.format(w["qty"])))
	doc = frappe.get_doc(reference_type, reference_name)
	src = next(r for r in doc.items if r.name == row)
	if reference_type == "Purchase Receipt":
		return _open_inspection(
			inspection_type="Incoming", stage="Incoming", reference_type=reference_type, reference_name=reference_name,
			row=row, item_code=src.item_code, lot=flt(src.qty), batch_no=_row_batch(src), sample=sample_size,
			extra={"custom_supplier_cert": doc.get("custom_material_test_certificate")})
	return _open_inspection(
		inspection_type="Outgoing", stage="Final", reference_type=reference_type, reference_name=reference_name,
		row=row, item_code=src.item_code, lot=flt(src.qty), batch_no=_row_batch(src), bom_no=doc.get("bom_no"), sample=sample_size,
		extra={"custom_work_order": doc.get("work_order"), "bom_no": doc.get("bom_no"),
		       "custom_customer": _wo_customer(doc.get("work_order"))})


def _sync_pending(reference_type, reference_name):
	"""Flag the document by whether anything on it still waits, and let the
	Assignment Rule close (or reopen) the engineer's task to match."""
	pending = int(any(r["state"] != "done" for r in waiting(reference_type, reference_name)))
	if frappe.db.get_value(reference_type, reference_name, "custom_inspection_pending") == pending:
		return
	frappe.db.set_value(reference_type, reference_name, "custom_inspection_pending", pending, update_modified=False)
	from frappe.automation.doctype.assignment_rule.assignment_rule import apply

	apply(doctype=reference_type, name=reference_name)


# ------------------------------------------------------------- Inspection --


def qi_validate(doc, method=None):
	"""The lot of an inspection whose stock waits in Inspection Required."""
	src = _source_row(doc)
	if src and doc.docstatus == 0 and not flt(doc.get("custom_lot_qty")):
		doc.custom_lot_qty = flt(src.qty)


def qi_before_submit(doc, method=None):
	src = _source_row(doc)
	if not src:
		return
	doc.inspected_by = frappe.session.user  # whoever submits is the inspector of record
	lot = flt(doc.custom_lot_qty) or flt(src.qty)
	doc.custom_lot_qty = lot
	# left blank: the whole lot follows the verdict
	if not flt(doc.custom_accepted_qty) and not flt(doc.custom_rejected_qty):
		if doc.status == "Rejected" and doc.get("custom_disposition") != "Accept under Concession":
			doc.custom_rejected_qty = lot
		else:
			doc.custom_accepted_qty = lot
	total = flt(doc.custom_accepted_qty) + flt(doc.custom_rejected_qty)
	if abs(total - flt(doc.custom_lot_qty)) > 1e-6:
		frappe.throw(_("Accepted ({0}) and rejected ({1}) must add up to the lot ({2}).").format(
			flt(doc.custom_accepted_qty), flt(doc.custom_rejected_qty), flt(doc.custom_lot_qty)), title=_("Quantities"))


def qi_on_submit(doc, method=None):
	src = _source_row(doc)
	if not src or doc.get("custom_transfer_entry"):
		return
	_sync_pending(doc.reference_type, doc.reference_name)
	company = frappe.db.get_value(doc.reference_type, doc.reference_name, "company")
	wh = inspection_warehouse(company)
	release = src.get("custom_release_warehouse") or _warehouse(company, "Stores")
	rejected = _warehouse(company, "Rejected")
	# the batch is created when the receipt posts, after its inspection was opened
	batch = doc.batch_no or _row_batch(frappe.db.get_value(
		"Purchase Receipt Item" if doc.reference_type == "Purchase Receipt" else "Stock Entry Detail",
		src.name, ["batch_no", "serial_and_batch_bundle"], as_dict=True) or {})
	if batch and not doc.batch_no:
		doc.db_set("batch_no", batch, update_modified=False)
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.company = company
	se.custom_quality_inspection = doc.name
	se.remarks = _("Released by {0} ({1} {2})").format(doc.name, doc.reference_type, doc.reference_name)
	for qty, target in ((flt(doc.custom_accepted_qty), release), (flt(doc.custom_rejected_qty), rejected)):
		if qty > 0 and target:
			se.append("items", {"item_code": doc.item_code, "qty": qty, "s_warehouse": wh, "t_warehouse": target,
			                    "batch_no": batch, "use_serial_batch_fields": 1 if batch else 0,
			                    "allow_zero_valuation_rate": 1})
	if not se.items:
		return
	se.flags.ignore_permissions = True
	se.insert()
	doc.db_set("custom_transfer_entry", se.name, update_modified=False)
	frappe.msgprint(_("Transfer {0} drafted: Stores posts it after racking.").format(
		frappe.utils.get_link_to_form("Stock Entry", se.name)), indicator="green", title=_("Release"))


def qi_on_cancel(doc, method=None):
	name = doc.get("custom_transfer_entry")
	if name and frappe.db.get_value("Stock Entry", name, "docstatus") == 0:
		doc.db_set("custom_transfer_entry", None, update_modified=False)
		frappe.delete_doc("Stock Entry", name, ignore_permissions=True, force=True)
	if _source_row(doc):
		_sync_pending(doc.reference_type, doc.reference_name)


def _source_row(doc):
	"""The receipt or manufacture row whose stock waits in Inspection Required."""
	if doc.reference_type not in ("Purchase Receipt", "Stock Entry") or not doc.reference_name:
		return None
	child = "Purchase Receipt Item" if doc.reference_type == "Purchase Receipt" else "Stock Entry Detail"
	field = "warehouse" if doc.reference_type == "Purchase Receipt" else "t_warehouse"
	filters = {"parent": doc.reference_name, "item_code": doc.item_code}
	if doc.child_row_reference:
		filters["name"] = doc.child_row_reference
	row = frappe.db.get_value(child, filters, ["name", "qty", field, "custom_release_warehouse"], as_dict=True)
	if not row or not _is_inspection_warehouse(row.get(field)):
		return None
	return row
