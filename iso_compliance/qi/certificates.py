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
TEST_REPORT_FORMAT = "Test Report 2.2"
COC_FORMAT = "Certificate of Conformity"
MTC_FORMAT = "Material Test Certificate 3.1"
#: Next free form number after FRM-037 (developer, 2026-10-13); REG-001 entry by iso's document set.
RECORD_FORM_NO = "HCCPL/QMS/FRM-038"


#: the drawing area of an A4 sheet at 12 mm margins, under the header strip and annex heading
SHEET_W_MM, SHEET_H_MM = 186, 212


def _sheet(file_url: str) -> dict | None:
	"""One drawing page for print: the image as a data URI and the width (in %
	of the text column) at which the whole page fits on one A4 sheet. A page
	taller than the sheet would split, and Chrome then paints the image on
	one sheet and the boxes on another."""
	if not file_url:
		return None
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return None
	content = frappe.get_doc("File", name).get_content()
	if isinstance(content, str):
		content = content.encode()
	width, ratio = 100.0, 1.0
	try:
		from io import BytesIO

		from PIL import Image

		w, h = Image.open(BytesIO(content)).size
		ratio = w / h
		width = round(min(SHEET_W_MM, SHEET_H_MM * ratio) / SHEET_W_MM * 100, 1)
	except Exception:
		pass
	mime = "image/png" if file_url.lower().endswith(".png") else "image/jpeg"
	return {"image": f"data:{mime};base64,{base64.b64encode(content).decode()}", "width": width, "ratio": ratio}


def _data_uri(file_url: str) -> str | None:
	sheet = _sheet(file_url)
	return sheet["image"] if sheet else None


def _decimals(*texts) -> int:
	out = 0
	for t in texts:
		t = str(t or "").strip()
		if "." in t and t.replace(".", "", 1).lstrip("-").isdigit():
			out = max(out, len(t.split(".")[1]))
	return out


def _dp(r, raw) -> int | None:
	"""Decimals a numeric row prints with: as many as its limits or readings
	carry, and at least two for millimetres (37.70 – 38.00)."""
	if r.custom_row_type == "Visual" or r.custom_tolerance_type == T.ANGLE:
		return None
	d = _decimals(T.display_limit(r.min_value), T.display_limit(r.max_value), *raw)
	return max(d, 2) if (r.custom_unit or "mm") == "mm" else d


def _fixed(x, dp):
	if dp is None or x is None or x == "":
		return x
	try:
		return f"{float(x):.{dp}f}"
	except (TypeError, ValueError):
		return x


def _pages(template: str) -> list[str]:
	from iso_compliance.qi.template import page_images

	try:
		return page_images(frappe.get_doc("Quality Inspection Template", template))
	except Exception:
		frappe.log_error(title=f"Drawing page images: {template}")
		raw = frappe.db.get_value("Quality Inspection Template", template, "custom_drawing_pages")
		try:
			return (frappe.parse_json(raw) or {}).get("pages") or []
		except Exception:
			return []


def _limit_text(r, dp=None) -> str:
	if r.custom_row_type == "Visual":
		return "OK / NG"
	lo, hi = T.display_limit(r.min_value), T.display_limit(r.max_value)
	if dp is not None:
		lo, hi = (x if x == "—" else _fixed(x, dp) for x in (lo, hi))
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
		dp = _dp(r, [m.value for m in vals])
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
			values.append({"n": m.sample_no, "value": _fixed(m.value, dp), "bad": bad})
		instruments = sorted({m.instrument for m in vals if m.instrument})
		rows.append({
			"balloon": r.custom_balloon_no,
			"type": r.custom_row_type,
			"specification": r.specification,
			"spec_text": r.custom_spec_text or "",
			"limits": _limit_text(r, dp),
			"unit": r.custom_unit or "",
			"class": r.custom_class or "",
			"test_method": r.custom_test_method or "",
			"instruments": [
				{"name": a, "label": frappe.db.get_value("Asset", a, "asset_name") or a, "cal_due": calibration(a).get("due")}
				for a in instruments
			],
			"values": values,
			"n": len(values),
			"required": cint(r.custom_sample_count),
			"min": _fixed(r.custom_obs_min, dp) if r.custom_row_type != "Visual" else None,
			"max": _fixed(r.custom_obs_max, dp) if r.custom_row_type != "Visual" else None,
			"status": r.status,
			# from the values themselves: the row's status is refreshed only when the inspection is saved
			"bad": r.status == "Rejected" or any(v["bad"] for v in values),
		})
		src = tpl_rows.get(r.custom_balloon_no)
		if src and src.custom_position:
			try:
				pos = frappe.parse_json(src.custom_position)
			except Exception:
				pos = None
			if pos:
				# red: out of spec; green: every planned sample measured and in spec; grey: not finished
				state = "bad" if rows[-1]["bad"] else ("ok" if values and len(values) >= cint(r.custom_sample_count) else "todo")
				boxes.setdefault(cint(pos.get("page") or 1), []).append({**pos, "balloon": r.custom_balloon_no, "state": state})

	# the sheets that carry numbers, or every sheet when the inspection asks for it
	urls = _pages(qi.quality_inspection_template)
	every = cint(qi.get("custom_print_all_sheets"))
	keep = [i for i in range(1, len(urls) + 1) if every or i in boxes] or ([1] if urls else [])
	pages = [{"no": i, **(_sheet(urls[i - 1]) or {"image": None}), "boxes": boxes.get(i, [])} for i in keep]
	conditions = [c for c in qi.get("custom_conditions") or []]
	return {
		"name": qi.name,
		"form_no": RECORD_FORM_NO,
		"item_code": qi.item_code,
		"item_name": qi.item_name,
		"batch_no": qi.batch_no,
		"stage": qi.custom_stage,
		"check_point": qi.get("custom_check_point"),
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
		# the unit most measured rows share: Annex A states it once ("values in mm unless stated")
		"main_unit": max(units, key=units.count) if (units := [r["unit"] for r in rows if r["type"] != "Visual" and r["unit"]]) else "",
		"pages": [p for p in pages if p["image"]],
		"failed": [r for r in rows if r["bad"]],
		"sheets": len(urls),
		"counts": {
			"conform": sum(1 for r in rows if not r["bad"] and r["n"] and r["n"] >= r["required"]),
			"failed": sum(1 for r in rows if r["bad"]),
			"open": sum(1 for r in rows if not r["bad"] and (not r["n"] or r["n"] < r["required"])),
		},
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


# --------------------------------------------------------------- EN 10204 --
# One shape for the three inspection documents of EN 10204:2004.
#   2.1 Declaration of compliance with the order: the statement, no results.
#   2.2 Test report: the statement with results of non-specific inspection
#       (the same product and process; not necessarily the lot delivered).
#   3.1 Inspection certificate: results of specific inspection of the lot
#       delivered, validated by an inspection representative independent of
#       manufacturing; material groups add the supplier trace (mtc_row).
# Form numbers: next free after FRM-039 (to be entered in REG-001).

# Titles as HCC issues them (developer, 2026-10-14); the type number keeps each
# one tied to its EN 10204 definition.
#: One delivery certificate at three EN 10204:2004 levels. 2.1 is the
#: Certificate of Conformity (FRM-030), which replaced the separate 2.1
#: declaration (FRM-040, retired 2026-10-25).
EN10204 = {
	"2.1": {"title": "Certificate of Conformity", "form_no": "HCCPL/QMS/FRM-030", "issue": "Issue 01 / Rev 01"},
	"2.2": {"title": "Test Report", "form_no": "HCCPL/QMS/FRM-041", "issue": "Issue 01 / Rev 00"},
	"3.1": {"title": "Inspection Certificate", "form_no": "HCCPL/QMS/FRM-039", "issue": "Issue 01 / Rev 00"},
}


def _num(x) -> str:
	return f"{round(flt(x), 4):g}"


def _result(p) -> str:
	if p.get("values"):
		return ", ".join(str(v) for v in p["values"])
	if p.get("obs_min") is None:
		return ""
	lo, hi = _num(p["obs_min"]), _num(p["obs_max"])
	return lo if lo == hi else f"{lo} – {hi}"


def _requirement(p) -> str:
	if p.get("limits"):
		return p["limits"]
	if p.get("numeric"):
		return f"{_num(p['min_spec'])} – {_num(p['max_spec'])}"
	return p.get("spec") or ""


def _results(params) -> list[dict]:
	out = []
	for p in params:
		res = _result(p)
		if not res:
			continue
		out.append({"characteristic": p["specification"], "requirement": _requirement(p), "result": res,
		            "unit": p.get("unit") or "", "ok": p.get("ok", True), "n": p.get("n") or ""})
	return out


def _latest_results(item_code: str):
	"""Non-specific results for 2.2: the newest accepted inspection of the
	same product. (qi, results) or (None, [])."""
	from iso_compliance.qi.inspection import measurements

	name = frappe.db.get_value(
		"Quality Inspection", {"item_code": item_code, "docstatus": 1, "status": "Accepted"}, "name",
		order_by="report_date desc, creation desc")
	if not name:
		return None, []
	qi = frappe.get_doc("Quality Inspection", name)
	meas = measurements(qi.name) if any(r.get("custom_row_type") for r in qi.readings) else {}
	params = []
	for r in qi.readings:
		p = {"specification": r.specification, "limits": _limit_text(r) if r.get("custom_row_type") else None,
		     "numeric": r.numeric, "min_spec": r.min_value, "max_spec": r.max_value, "spec": r.value,
		     "unit": r.get("custom_unit") or r.get("custom_uom") or "", "values": [], "obs_min": None, "obs_max": None}
		raw = [m.value for m in meas.get(r.get("custom_balloon_no") or "", [])] if r.get("custom_row_type") else \
			[r.get(f"reading_{i}") for i in range(1, 11)] if r.numeric else [r.reading_value]
		for v in raw:
			if v in (None, ""):
				continue
			if r.get("custom_row_type") == "Visual" or not (r.numeric or r.get("custom_row_type")):
				if v not in p["values"]:
					p["values"].append(v)
				continue
			try:
				x = float(v)
			except (TypeError, ValueError):
				continue
			p["obs_min"] = x if p["obs_min"] is None else min(p["obs_min"], x)
			p["obs_max"] = x if p["obs_max"] is None else max(p["obs_max"], x)
		params.append(p)
	return qi, _results(params)


def _drawing_ref(item_code: str) -> str:
	from iso_compliance.qi.inspection import resolve_template

	t = resolve_template(item_code)
	if not t or not is_drawing_template(t):
		return ""
	no, rev = frappe.db.get_value("Quality Inspection Template", t, ["custom_drawing_no", "custom_drawing_revision"])
	return " Rev ".join(x for x in (no, rev) if x)


def _reports_of(row) -> list[str]:
	"""The inspection reports that stand behind one delivered row: its despatch
	and final inspections, else its receipt inspections (for a traded item the
	receipt inspection is the final one, QI SPEC v2 Phase E)."""
	from iso_compliance.utils import coc_row_inspections

	chain = coc_row_inspections(row)
	names = [qi.name for qi in chain["pdi"]] + ([chain["outgoing"].name] if chain["outgoing"] else [])
	return list(dict.fromkeys(names)) or [qi.name for qi in chain.get("incoming") or []]


def _place(address: str | None) -> str:
	"""City and country of an address, the way a certificate names a customer."""
	if not address:
		return ""
	a = frappe.db.get_value("Address", address, ["city", "country"], as_dict=True) or {}
	return ", ".join(x for x in (a.get("city"), a.get("country")) if x)


_FONTS: str | None = None


def report_fonts() -> str:
	"""@font-face rules embedding Arimo (Apache 2.0, metrically Arial) as data
	URIs: the PDF server has only DejaVu, which sets wider than the reports
	were designed in."""
	global _FONTS
	if _FONTS is None:
		css = []
		for weight in (400, 700):
			path = frappe.get_app_path("iso_compliance", "public", "fonts", f"arimo-latin-{weight}-normal.woff2")
			with open(path, "rb") as f:
				data = base64.b64encode(f.read()).decode()
			css.append(f"@font-face {{ font-family: 'Arimo'; font-weight: {weight}; font-style: normal; "
			           f"src: url(data:font/woff2;base64,{data}) format('woff2'); }}")
		_FONTS = "\n".join(css)
	return _FONTS


def letterhead(company: str) -> dict:
	"""The company block every report prints at the top: name, logo, address
	and whatever contact details the Company record holds."""
	c = frappe.db.get_value("Company", company, ["company_name", "company_logo", "phone_no", "email", "website", "tax_id"],
	                        as_dict=True) or frappe._dict()
	contact = [x for x in (c.phone_no and f"Tel {c.phone_no}", c.email, c.website) if x]
	logo = _sheet(c.company_logo) if c.company_logo else None
	return {
		"name": c.company_name or company,
		"logo": logo["image"] if logo else None,
		# printed 30 pt high; the width keeps the logo's proportions (an auto width collapses in a table cell)
		"logo_width": round(30 * logo["ratio"], 1) if logo else None,
		"address": _company_address(company),
		"contact": " · ".join(contact),
		"gstin": c.tax_id,
	}


def _company_address(company: str) -> str:
	"""One line identifying the manufacturer: its primary company address."""
	names = frappe.get_all("Dynamic Link", filters={"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
	                       pluck="parent")
	rows = frappe.get_all("Address", filters={"name": ("in", names or [""]), "disabled": 0},
	                      fields=["address_line1", "address_line2", "city", "pincode", "country", "is_primary_address"],
	                      order_by="is_primary_address desc, creation asc", limit=1)
	if not rows:
		return ""
	a = rows[0]
	city = " ".join(x for x in (a.city, a.pincode) if x)
	return ", ".join(x for x in (a.address_line1, a.address_line2, city, a.country) if x)


def _cert_row(row, doc_type: str, concessions: list) -> dict:
	"""One goods line of a certificate, with its results (2.2 / 3.1) and
	material trace (3.1). `row` is a Delivery Note Item or a stand-in for one."""
	from iso_compliance.utils import coc_row_aggregate

	r = {"item_code": row.item_code, "item_name": row.item_name, "qty": row.qty, "uom": row.uom,
	     "batches": _batches_of(row.get("serial_and_batch_bundle"), row.get("batch_no")),
	     "drawing": _drawing_ref(row.item_code), "results": [], "basis": "", "mtc": None,
	     "reports": _reports_of(row)}
	if doc_type in ("2.2", "3.1"):
		agg = coc_row_aggregate(row)
		concessions += agg["concessions"]
		r["results"] = _results(agg["parameters"])
		if r["results"]:
			r["basis"] = _("specific inspection of the batches supplied")
		elif doc_type == "2.2":
			qi, res = _latest_results(row.item_code)
			if qi:
				r["results"], r["basis"] = res, _("non-specific inspection, production of {0}").format(
					frappe.utils.formatdate(qi.report_date))
		if doc_type == "3.1":
			r["mtc"] = mtc_row(row)
	return r


def en10204(delivery_note, doc_type: str, only_rows: list[str] | None = None) -> dict:
	"""Everything an EN 10204 2.1 / 2.2 / 3.1 document prints for one Delivery
	Note; `only_rows` (Delivery Note Item names) narrows it to those lines."""
	dn = delivery_note if not isinstance(delivery_note, str) else frappe.get_doc("Delivery Note", delivery_note)
	spec = EN10204[doc_type]
	items = [row for row in dn.items if not only_rows or row.name in only_rows]
	orders = sorted({r.against_sales_order for r in items if r.get("against_sales_order")})
	po = [frappe.db.get_value("Sales Order", so, ["po_no", "po_date"], as_dict=True) for so in orders]
	po = [p for p in po if p and p.po_no] or ([frappe._dict(po_no=dn.po_no, po_date=dn.po_date)] if dn.get("po_no") else [])
	logo = frappe.db.get_value("Company", dn.company, "company_logo")
	concessions = []
	rows = [_cert_row(row, doc_type, concessions) for row in items]
	return {
		"type": doc_type,
		"title": spec["title"],
		"form_no": spec["form_no"],
		"issue": spec["issue"],
		"number": f"{dn.name}/{doc_type}",
		"ref": dn.name,
		"issued": dn.posting_date,
		"company": dn.company,
		"address": _company_address(dn.company),
		"logo": _data_uri(logo) if logo else None,
		"customer": dn.customer_name or dn.customer,
		"customer_place": _place(dn.get("shipping_address_name") or dn.get("customer_address")),
		"lr_no": dn.get("lr_no"),
		"lr_date": dn.get("lr_date"),
		"po": [{"no": p.po_no, "date": p.po_date} for p in po],
		"delivery_note": dn.name,
		"delivery_date": dn.posting_date,
		"rows": rows,
		"show_drawing": any(r["drawing"] for r in rows),
		"concessions": list(dict.fromkeys(concessions)),
		"draft": dn.docstatus != 1,
	}


def _qi_delivery(qi) -> tuple[str | None, list[str]]:
	"""The Delivery Note an inspection is connected to, and its lines for the
	inspected item: the despatch inspection on the note or a line, else a line
	that delivered the inspected batch. (None, []) when nothing is connected."""
	lines = lambda dn: frappe.get_all("Delivery Note Item", filters={"parent": dn, "item_code": qi.item_code}, pluck="name")
	if qi.reference_type == "Delivery Note" and frappe.db.get_value("Delivery Note", qi.reference_name, "docstatus") != 2:
		return qi.reference_name, lines(qi.reference_name)
	hit = frappe.get_all("Delivery Note Item", filters={"quality_inspection": qi.name, "docstatus": ("<", 2)},
	                     fields=["name", "parent"], order_by="creation desc", limit=1)
	if hit:
		return hit[0].parent, [hit[0].name]
	if qi.batch_no:
		hit = frappe.get_all("Delivery Note Item", filters={"item_code": qi.item_code, "batch_no": qi.batch_no,
		                     "docstatus": ("<", 2)}, fields=["name", "parent"], order_by="creation desc", limit=1)
		if hit:
			return hit[0].parent, [r for r in lines(hit[0].parent) if r == hit[0].name]
		bundle = frappe.db.sql("""select b.voucher_no, b.voucher_detail_no from `tabSerial and Batch Bundle` b
			join `tabSerial and Batch Entry` e on e.parent = b.name
			where b.voucher_type = 'Delivery Note' and b.item_code = %s and e.batch_no = %s and b.docstatus < 2
			order by b.creation desc limit 1""", (qi.item_code, qi.batch_no), as_dict=True)
		if bundle:
			return bundle[0].voucher_no, [bundle[0].voucher_detail_no]
	return None, []


def qi_en10204(name: str, doc_type: str) -> dict:
	"""The EN 10204 document printed from a Quality Inspection: the connected
	Delivery Note's certificate for the inspected item, else one line from the
	inspection itself with the delivery fields left blank to fill by hand."""
	from iso_compliance.utils import coc_row_inspections

	qi = frappe.get_doc("Quality Inspection", name)
	dn, only = _qi_delivery(qi)
	if dn:
		return en10204(dn, doc_type, only or None)

	stock_uom = frappe.db.get_value("Item", qi.item_code, "stock_uom")
	row = frappe._dict(name=None, item_code=qi.item_code, item_name=qi.item_name, qty=qi.get("custom_lot_qty") or qi.sample_size,
	                   uom=stock_uom, batch_no=qi.batch_no, serial_and_batch_bundle=None, quality_inspection=None)
	chain = coc_row_inspections(row)
	known = [q.name for q in (chain.get("incoming") or []) + chain["pdi"] + chain["in_process"]]
	if qi.name not in known:
		row.quality_inspection = qi.name  # absorbed as the despatch inspection
	concessions = []
	r = _cert_row(row, doc_type, concessions)
	if qi.name not in r["reports"]:
		r["reports"].insert(0, qi.name)
	spec = EN10204[doc_type]
	return {
		"type": doc_type,
		"title": spec["title"],
		"form_no": spec["form_no"],
		"issue": spec["issue"],
		"number": f"{qi.name}/{doc_type}",
		"ref": qi.name,
		"issued": qi.report_date,
		"company": qi.company,
		"address": _company_address(qi.company),
		"logo": None,
		"customer": qi.get("custom_customer") or "",
		"customer_place": "",
		"lr_no": None,
		"lr_date": None,
		"po": [],
		"delivery_note": None,
		"delivery_date": None,
		"rows": [r],
		"show_drawing": bool(r["drawing"]),
		"concessions": list(dict.fromkeys(concessions)),
		"draft": qi.docstatus != 1,
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

	from iso_compliance.utils import coc_row_aggregate

	missing, drafts, rejected, concessions, records, no_record = [], [], [], [], 0, []
	mtc_items, mtc_gaps = [], []
	no_results, no_specific = [], []
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
		# 3.1 needs results of the delivered batches; 2.2 accepts the product's latest
		specific = bool(_results(coc_row_aggregate(row)["parameters"])) if evidence else False
		if not specific and not m:
			no_specific.append(row.item_code)
			if not _latest_results(row.item_code)[0]:
				no_results.append(row.item_code)

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
		# EN 10204 documents; "default" says whether the email ticks it unasked.
		"d21": {
			"applicable": True,
			"ready": coc_ready,
			"reason": why(
				dn.docstatus != 1 and _("Delivery Note not submitted"),
				drafts and _("inspections still in draft"),
				rejected and _("rejected inspections: {0}").format(", ".join(rejected)),
				concessions and _("includes concession {0}").format(", ".join(concessions)),
			),
			"print_format": COC_FORMAT,  # 2.1 is the Certificate of Conformity
			"default": False,
		},
		"d22": {
			"applicable": True,
			"ready": coc_ready and not no_results,
			"reason": why(
				dn.docstatus != 1 and _("Delivery Note not submitted"),
				drafts and _("inspections still in draft"),
				no_results and _("no test results for {0}").format(", ".join(no_results)),
				concessions and _("includes concession {0}").format(", ".join(concessions)),
			),
			"print_format": TEST_REPORT_FORMAT,
			"default": False,
		},
		# Gaps warn but never block: the sender decides (developer, 2026-10-13).
		# Any delivery may carry a 3.1; it is ticked unasked only for item groups that issue one.
		"mtc": {
			"applicable": True,
			"ready": coc_ready and not no_specific and not mtc_gaps,
			"reason": why(
				dn.docstatus != 1 and _("Delivery Note not submitted"),
				no_specific and _("no inspection of the delivered batches for {0}").format(", ".join(no_specific)),
				"; ".join(mtc_gaps),
			),
			"print_format": MTC_FORMAT,
			"default": bool(mtc_items),
		},
	}
