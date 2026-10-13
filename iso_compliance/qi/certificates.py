# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Certificates built from drawing inspections (SPEC §4.7–4.8).

- `qi_record(name)`: everything the Sampling & Inspection Record prints for
  one inspection -- the marked drawing (page images with the balloons laid
  over them) and every measured value.
- `dn_records(row)`: the records behind one delivered row.
- `certificate_readiness(delivery_note)`: what the dispatch email may attach
  (hcc_erp_edits calls it; OVERLAPS.md).

Print formats are rendered by wkhtmltopdf or Chrome, neither of which can run
pdf.js, so the drawing prints from the page images the template builder made;
they are embedded as data URIs because private files are not reachable by
the PDF renderer's own requests.
"""

import base64

import frappe
from frappe import _
from frappe.utils import cint, flt

from iso_compliance.qi import tolerance as T
from iso_compliance.qi.inspection import calibration, drawing_rows, measurements
from iso_compliance.qi.template import ROWS, is_drawing_template

RECORD_FORMAT = "Sampling and Inspection Record"
COC_FORMAT = "Certificate of Conformity"
MTC_FORMAT = "Material Test Certificate 3.1"
#: Next free form number after FRM-037 (developer, 2026-10-13); REG-001 entry by iso's document set.
RECORD_FORM_NO = "HCCPL/QMS/FRM-038"


def _data_uri(file_url: str) -> str | None:
	if not file_url:
		return None
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return None
	content = frappe.get_doc("File", name).get_content()
	if isinstance(content, str):
		content = content.encode()
	mime = "image/png" if file_url.lower().endswith(".png") else "image/jpeg"
	return f"data:{mime};base64,{base64.b64encode(content).decode()}"


def _pages(template: str) -> list[str]:
	raw = frappe.db.get_value("Quality Inspection Template", template, "custom_drawing_pages")
	try:
		return (frappe.parse_json(raw) or {}).get("pages") or []
	except Exception:
		return []


def _limit_text(r) -> str:
	if r.custom_row_type == "Visual":
		return "OK / NG"
	lo, hi = T.display_limit(r.min_value), T.display_limit(r.max_value)
	if lo == "—":
		return f"≤ {hi}"
	if hi == "—":
		return f"≥ {lo}"
	if r.custom_tolerance_type == T.MAX_ONLY and flt(r.min_value) == 0:
		return f"≤ {hi}"
	return f"{lo} – {hi}"


def qi_record(name: str) -> dict | None:
	"""The Sampling & Inspection Record for one drawing inspection."""
	qi = frappe.get_doc("Quality Inspection", name)
	if not is_drawing_template(qi.quality_inspection_template):
		return None
	data = measurements(qi.name)
	tpl_rows = {r.custom_balloon_no: r for r in frappe.get_doc("Quality Inspection Template", qi.quality_inspection_template).get(ROWS)}

	rows, boxes = [], {}
	for r in drawing_rows(qi):
		vals = data.get(r.custom_balloon_no, [])
		lo, hi = flt(r.min_value), flt(r.max_value)
		values = []
		for m in vals:
			if r.custom_row_type == "Visual":
				bad = str(m.value).upper() == "NG"
			else:
				try:
					x = T.parse_angle(m.value) if r.custom_tolerance_type == T.ANGLE else float(m.value)
					bad = x < lo - 1e-9 or x > hi + 1e-9
				except (ValueError, T.ToleranceError):
					bad = True
			values.append({"n": m.sample_no, "value": m.value, "bad": bad})
		instruments = sorted({m.instrument for m in vals if m.instrument})
		rows.append({
			"balloon": r.custom_balloon_no,
			"type": r.custom_row_type,
			"specification": r.specification,
			"spec_text": r.custom_spec_text or "",
			"limits": _limit_text(r),
			"unit": r.custom_unit or "",
			"class": r.custom_class or "",
			"test_method": r.custom_test_method or "",
			"instruments": [
				{"name": a, "cal_due": calibration(a).get("due")} for a in instruments
			],
			"values": values,
			"n": len(values),
			"required": cint(r.custom_sample_count),
			"min": r.custom_obs_min if r.custom_row_type != "Visual" else None,
			"max": r.custom_obs_max if r.custom_row_type != "Visual" else None,
			"status": r.status,
		})
		src = tpl_rows.get(r.custom_balloon_no)
		if src and src.custom_position:
			try:
				pos = frappe.parse_json(src.custom_position)
			except Exception:
				pos = None
			if pos:
				boxes.setdefault(cint(pos.get("page") or 1), []).append({
					**pos, "balloon": r.custom_balloon_no,
					"state": "bad" if r.status == "Rejected" else "ok",
				})

	pages = [
		{"image": _data_uri(url), "boxes": boxes.get(i, [])}
		for i, url in enumerate(_pages(qi.quality_inspection_template), 1)
	]
	conditions = [c for c in qi.get("custom_conditions") or []]
	return {
		"name": qi.name,
		"form_no": RECORD_FORM_NO,
		"item_code": qi.item_code,
		"item_name": qi.item_name,
		"batch_no": qi.batch_no,
		"stage": qi.custom_stage,
		"report_date": qi.report_date,
		"lot_qty": qi.custom_lot_qty,
		"sample_size": qi.sample_size,
		"reference": f"{qi.reference_type} {qi.reference_name}",
		"work_order": qi.custom_work_order,
		"customer": qi.custom_customer,
		"drawing_no": qi.custom_drawing_no,
		"drawing_revision": qi.custom_drawing_revision,
		"template": qi.quality_inspection_template,
		"inspected_by": frappe.utils.get_fullname(qi.inspected_by) if qi.inspected_by else "",
		"verified_by": qi.verified_by or "",
		"status": qi.status,
		"docstatus": qi.docstatus,
		"disposition": qi.custom_disposition or qi.status,
		"concession_no": qi.custom_concession_no,
		"non_conformance": qi.custom_non_conformance,
		"work_instructions": [
			{"level": w.level, "doc": w.controlled_document, "revision": w.revision}
			for w in qi.get("custom_work_instructions") or []
		],
		"conditions": [
			{"row": c.row_key, "condition": c.condition, "set": c.set_value, "tol": c.tolerance,
			 "unit": c.unit, "actual": c.actual}
			for c in conditions
		],
		"rows": rows,
		"pages": [p for p in pages if p["image"]],
		"failed": [r for r in rows if r["status"] == "Rejected"],
	}


def dn_records(row) -> list[dict]:
	"""Records for one delivered row: its final (PDI) and despatch inspections
	that were made on a drawing template."""
	from iso_compliance.utils import coc_row_inspections

	chain = coc_row_inspections(row)
	names = [qi.name for qi in chain.get("incoming") or []] + [qi.name for qi in chain["pdi"]]
	if chain["outgoing"]:
		names.append(chain["outgoing"].name)
	out = []
	for name in dict.fromkeys(names):
		rec = qi_record(name)
		if rec:
			out.append(rec)
	return out


# ------------------------------------------------------------------ 3.1 MTC --


def _batches_of(doctype_row_bundle, batch_no=None) -> list[str]:
	out = [batch_no] if batch_no else []
	if doctype_row_bundle:
		out += frappe.get_all("Serial and Batch Entry", filters={"parent": doctype_row_bundle,
		                      "batch_no": ("is", "set")}, pluck="batch_no")
	return list(dict.fromkeys(b for b in out if b))


def _receipt_source(batch: str) -> dict | None:
	"""Where a bought-in batch came from: receipt, supplier, heat, certificate."""
	b = frappe.db.get_value("Batch", batch, ["item", "reference_doctype", "reference_name", "supplier",
	                                         "custom_heat_no"], as_dict=True)
	if not b or b.reference_doctype != "Purchase Receipt" or not b.reference_name:
		return None
	pr = frappe.db.get_value("Purchase Receipt", b.reference_name,
	                         ["name", "supplier", "supplier_name", "posting_date", "custom_material_test_certificate"],
	                         as_dict=True)
	if not pr:
		return None
	return {
		"batch": batch,
		"item": b.item,
		"item_name": frappe.db.get_value("Item", b.item, "item_name"),
		"heat_no": b.custom_heat_no,
		"receipt": pr.name,
		"receipt_date": pr.posting_date,
		"supplier": pr.supplier_name or pr.supplier,
		"certificate": pr.custom_material_test_certificate,
		"certificate_name": (pr.custom_material_test_certificate or "").rsplit("/", 1)[-1],
	}


def _consumed_batches(item_code: str, batch: str) -> list[str]:
	"""Raw-material batches the Manufacture entry that produced this batch consumed."""
	from iso_compliance.utils import _manufacture_entries

	out = []
	for entry in _manufacture_entries(item_code, [batch]):
		for d in frappe.get_all("Stock Entry Detail", filters={"parent": entry.name, "is_finished_item": 0,
		                        "s_warehouse": ("is", "set")},
		                        fields=["batch_no", "serial_and_batch_bundle"]):
			out += _batches_of(d.serial_and_batch_bundle, d.batch_no)
	return list(dict.fromkeys(out))


def _material_properties(qis) -> list[dict]:
	"""Material rows (supplier 3.1 values) and tests marked as material
	properties, with what was found."""
	props = []
	for qi in qis:
		data = measurements(qi.name)
		for r in drawing_rows(qi):
			material_test = r.custom_test_method and frappe.db.get_value("Test Method", r.custom_test_method,
			                                                               "material_property")
			if r.custom_row_type != "Material" and not material_test:
				continue
			vals = []
			for m in data.get(r.custom_balloon_no, []):
				try:
					vals.append(float(m.value))
				except (TypeError, ValueError):
					continue
			props.append({
				"property": r.specification,
				"method": r.custom_test_method or "",
				"limits": _limit_text(r),
				"unit": r.custom_unit or "",
				"result": (f"{min(vals):g}" if min(vals) == max(vals) else f"{min(vals):g} – {max(vals):g}") if vals else "",
				"n": len(vals),
				"ok": r.status != "Rejected",
				"source": _("supplier 3.1") if r.custom_row_type == "Material" else _("our test"),
				"inspection": qi.name,
			})
	return props


def mtc_row(row) -> dict | None:
	"""The 3.1 MTC for one delivered row, or None when its item group does not
	issue one. Bought-in batches trace to their receipt; made batches to the
	raw-material batches their Manufacture entry consumed."""
	if not _issue_mtc(row.item_code):
		return None
	from iso_compliance.utils import coc_row_inspections

	batches = _batches_of(row.get("serial_and_batch_bundle"), row.get("batch_no"))
	sources, gaps = [], []
	for b in batches:
		src = _receipt_source(b)
		if src:
			sources.append({**src, "role": _("supplied")})
			continue
		raw = _consumed_batches(row.item_code, b)
		traced = [s for s in (_receipt_source(r) for r in raw) if s]
		sources += [{**s, "role": _("raw material")} for s in traced]
		if not traced:
			ref = frappe.db.get_value("Batch", b, ["reference_doctype", "reference_name"], as_dict=True) or {}
			how = ref.get("reference_name") and frappe.db.get_value(ref.reference_doctype, ref.reference_name, "purpose") \
				if ref.get("reference_doctype") == "Stock Entry" else None
			gaps.append(
				_("batch {0} came in by {1} {2}{3}, so there is no supplier certificate to trace").format(
					b, ref.get("reference_doctype") or _("an unknown entry"), ref.get("reference_name") or "",
					f" ({how})" if how else "")
				if raw == [] else _("batch {0}: its raw-material batches have no receipt trace").format(b)
			)
	if not batches:
		gaps.append(_("no batch on the delivery row"))
	for s in sources:
		if not s["certificate"]:
			gaps.append(_("no supplier certificate on {0} ({1})").format(s["receipt"], s["item"]))

	chain = coc_row_inspections(row)
	qis = list(chain.get("incoming") or []) + list(chain["pdi"])
	# raw-material receipt inspections hold the supplier 3.1 values of made items
	receipts = {s["receipt"] for s in sources if s["role"] != _("supplied")}
	if receipts:
		qis += [frappe.get_doc("Quality Inspection", n) for n in frappe.get_all(
			"Quality Inspection", filters={"reference_type": "Purchase Receipt", "reference_name": ("in", list(receipts)),
			                               "custom_stage": "Incoming", "docstatus": 1}, pluck="name")]
	props = _material_properties(qis)
	if not props:
		gaps.append(_("no material properties recorded (Material rows or material-property tests)"))
	return {
		"item_code": row.item_code,
		"item_name": row.item_name,
		"qty": row.qty,
		"uom": row.uom,
		"batches": batches,
		"heat_nos": sorted({s["heat_no"] for s in sources if s.get("heat_no")}),
		"sources": sources,
		"properties": props,
		"gaps": gaps,
		"ready": not gaps,
	}


# ------------------------------------------------------------- readiness --


def _issue_mtc(item_code: str) -> bool:
	"""Item Group flag (Phase C2), inherited down the tree. False until the
	field exists."""
	if not frappe.get_meta("Item Group").has_field("custom_issue_mtc"):
		return False
	group = frappe.db.get_value("Item", item_code, "item_group")
	if not group:
		return False
	lft, rgt = frappe.db.get_value("Item Group", group, ["lft", "rgt"])
	return bool(frappe.db.exists("Item Group", {"lft": ("<=", lft), "rgt": (">=", rgt), "custom_issue_mtc": 1}))


@frappe.whitelist()
def certificate_readiness(delivery_note: str) -> dict:
	"""What the dispatch email can attach for this Delivery Note.

	{"coc": {...}, "record": {...}, "mtc": {...}}, each with `applicable`,
	`ready`, `reason` and `print_format`. Format names are stable: renaming
	one is an OVERLAPS.md change first.
	"""
	from iso_compliance.utils import coc_row_inspections

	dn = frappe.get_doc("Delivery Note", delivery_note)
	dn.check_permission("read")

	missing, drafts, rejected, concessions, records, no_record = [], [], [], [], 0, []
	mtc_items, mtc_gaps = [], []
	for row in dn.items:
		chain = coc_row_inspections(row)
		evidence = (list(chain.get("incoming") or []) + list(chain["pdi"])
		            + ([chain["outgoing"]] if chain["outgoing"] else []))
		if not evidence:
			missing.append(row.item_code)
		for q in evidence:
			if q.docstatus == 0:
				drafts.append(q.name)
			elif q.status == "Rejected":
				rejected.append(q.name)
			if q.get("custom_disposition") == "Accept under Concession":
				concessions.append(q.custom_concession_no or q.name)
		drawing = [q for q in evidence if is_drawing_template(q.quality_inspection_template)]
		records += len([q for q in drawing if q.docstatus == 1])
		if evidence and not drawing:
			no_record.append(row.item_code)
		m = mtc_row(row)
		if m:
			mtc_items.append(row.item_code)
			mtc_gaps += [f"{row.item_code}: {g}" for g in m["gaps"]]

	def why(*parts):
		return "; ".join(p for p in parts if p)

	coc_ready = dn.docstatus == 1 and not drafts and not rejected
	record_applicable = records > 0 or bool(drafts)
	return {
		"coc": {
			"applicable": True,
			"ready": coc_ready,
			"reason": why(
				dn.docstatus != 1 and _("Delivery Note not submitted"),
				drafts and _("inspections still in draft: {0}").format(", ".join(drafts)),
				rejected and _("rejected inspections: {0}").format(", ".join(rejected)),
				missing and _("no final inspection found for {0}").format(", ".join(missing)),
				concessions and _("includes concession {0}").format(", ".join(concessions)),
			),
			"print_format": COC_FORMAT,
		},
		"record": {
			"applicable": record_applicable,
			"ready": record_applicable and not drafts,
			"reason": why(
				not record_applicable and _("no drawing-based inspection behind these items"),
				drafts and _("inspections still in draft"),
				no_record and record_applicable and _("not for {0} (no drawing template)").format(", ".join(no_record)),
			),
			"print_format": RECORD_FORMAT,
		},
		# Gaps warn but never block: the sender decides (developer, 2026-10-13).
		"mtc": {
			"applicable": bool(mtc_items),
			"ready": bool(mtc_items) and not mtc_gaps and dn.docstatus == 1,
			"reason": _("not issued for these item groups") if not mtc_items else "; ".join(mtc_gaps),
			"print_format": MTC_FORMAT,
		},
	}
