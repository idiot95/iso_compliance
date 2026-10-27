# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Material identification labels: eight or forty to an A4 sheet, or one per
label on a thermal roll. Each carries the item code and name, the batch (as a
barcode), and for received material the supplier and date of receipt.

SOP-006 step 3 asks that accepted material be identified so that identity and
traceability hold through storage and into production. The label is how that
happens physically: it goes on the block or the package at goods-in, before the
inspection is finished, because material waiting to be inspected is exactly when
a mix-up happens. The outgoing label does the same job at dispatch.

**The barcode carries the batch number and nothing else.** ERPNext's own scanner
(`erpnext.stock.utils.scan_barcode`) resolves a scanned string by exact match
against Item Barcode, then Serial No, then Batch -- returning the batch and its
item. A barcode holding a blob of supplier and date text matches none of those
and the scan does nothing at all. Encoding the batch alone means the operator
scans into a Stock Entry and the row fills itself from live data, rather than
from whatever was true when the label was printed. It also keeps the payload at
eleven characters, which is what lets a Code128 scan off a small label.

Rendered as inline SVG by python-barcode, which is already in the bench venv.
No CDN and no JavaScript, so the sheet prints identically from the browser and
through wkhtmltopdf.

Sheet geometry is in SHEETS: Avery L7165 and its many equivalents (99.1 x 67.7
mm, two across and four down), and the 40-up sheet of 39 x 35 mm labels, five
across and eight down with no gaps, centred on the page. Print the guides
version on plain paper first and hold it against a label sheet to check the
printer is not scaling the page.

Thermal rolls print one label per page: the page is the label, so the printer
driver only needs the same size set as its paper. Three common roll sizes are
offered; LAYOUTS is the one place to add another.

Besides the receipt and delivery buttons, the Stock Labels page prints for the
stock already on the shelves (`stock_rows`, from the ledger) and answers "what
is this and where should it be" for a scanned label (`lookup`).
"""

from __future__ import annotations

import io
import re

import frappe
from frappe import _
from frappe.utils import format_date

LOGO = "/assets/iso_compliance/images/hcc-mark.png"

#: A4 label sheets, in millimetres.
SHEETS = {
	# Avery L7165 and equivalents
	"a4-8": {"label_w": 99.1, "label_h": 67.7, "cols": 2, "rows": 4, "margin_top": 13.1, "margin_side": 4.65, "col_gap": 2.5},
	# 40 to a sheet, 39 x 35 mm, no gaps: (210 - 5 x 39) / 2 and (297 - 8 x 35) / 2
	"a4-40": {"label_w": 39, "label_h": 35, "cols": 5, "rows": 8, "margin_top": 8.5, "margin_side": 7.5, "col_gap": 0},
}

#: What a label can be printed on. "sheet" layouts tile an A4 page; the others
#: are thermal rolls, one label per page of that size.
LAYOUTS = {
	"a4-8": {"label": "A4 sheet, 8 labels (99.1 × 67.7 mm)", "w": 99.1, "h": 67.7, "sheet": True},
	"a4-40": {"label": "A4 sheet, 40 labels (39 × 35 mm)", "w": 39, "h": 35, "sheet": True},
	"thermal-100x50": {"label": "Thermal roll, 100 × 50 mm", "w": 100, "h": 50},
	"thermal-75x50": {"label": "Thermal roll, 75 × 50 mm", "w": 75, "h": 50},
	"thermal-50x25": {"label": "Thermal roll, 50 × 25 mm (barcode and name only)", "w": 50, "h": 25},
}
DEFAULT_LAYOUT = "a4-8"

#: Printing more than this in one go is almost always a mistake -- a receipt line
#: can carry 14,000 blocks -- so the dialog asks for confirmation past it.
LABEL_WARN_THRESHOLD = 50

SUPPORTED = {"Purchase Receipt": "incoming", "Delivery Note": "outgoing"}


# ---------------------------------------------------------------------------
# Barcode
# ---------------------------------------------------------------------------


def code128_svg(value: str, module_width: float = 0.33, height: float = 11.0) -> str:
	"""An inline <svg> Code128 of `value`, or "" if it cannot be rendered.

	The built-in caption is switched off: the number is drawn in HTML instead, so
	it uses the label's own font rather than the barcode library's default.
	"""
	if not value:
		return ""
	try:
		import barcode
		from barcode.writer import SVGWriter

		buf = io.BytesIO()
		barcode.get("code128", str(value), writer=SVGWriter()).write(
			buf,
			options={
				"module_width": module_width,
				"module_height": height,
				"quiet_zone": 1.0,
				"write_text": False,
			},
		)
		svg = buf.getvalue().decode("utf-8")
	except Exception:
		# A label without a barcode is still a usable label; a traceback instead
		# of a print sheet is not.
		frappe.log_error(frappe.get_traceback(), "iso_compliance: barcode render failed")
		return ""

	# Strip the XML declaration and DOCTYPE so the fragment can sit inside HTML.
	start = svg.find("<svg")
	if start == -1:
		return ""
	svg = svg[start:]
	# A viewBox (in px, the unit its mm coordinates resolve to) lets the label's
	# CSS shrink the barcode to fit a small label instead of cutting it off.
	m = re.match(r'<svg[^>]*width="([\d.]+)mm" height="([\d.]+)mm"', svg)
	if m:
		w, h = (float(x) * 96 / 25.4 for x in m.groups())
		svg = svg.replace("<svg ", f'<svg viewBox="0 0 {w:.2f} {h:.2f}" preserveAspectRatio="none" ', 1)
	return svg


# ---------------------------------------------------------------------------
# Gathering the rows
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_label_rows(doctype: str, name: str) -> list[dict]:
	"""One row per batch on the document, for the quantity dialog.

	A line with no batch is still offered: item, supplier and date identify the
	material usefully even when nothing tracks it by batch. It simply gets no
	barcode, because there is no batch for a scan to resolve to.
	"""
	if doctype not in SUPPORTED:
		frappe.throw(_("{0} does not carry material labels.").format(doctype))
	frappe.has_permission(doctype, "read", doc=name, throw=True)

	child = "Purchase Receipt Item" if doctype == "Purchase Receipt" else "Delivery Note Item"
	lines = frappe.get_all(
		child,
		filters={"parent": name},
		fields=[
			"name",
			"idx",
			"item_code",
			"item_name",
			"qty",
			"batch_no",
			"serial_and_batch_bundle",
		],
		parent_doctype=doctype,
		order_by="idx",
	)

	bundled = _batches_by_bundle({ln.serial_and_batch_bundle for ln in lines if ln.serial_and_batch_bundle})

	rows = []
	for line in lines:
		batches = []
		if line.batch_no:
			batches.append((line.batch_no, line.qty))
		for batch_no, qty in bundled.get(line.serial_and_batch_bundle, []):
			if batch_no and batch_no not in {b for b, _ in batches}:
				batches.append((batch_no, qty))
		if not batches:
			batches = [(None, line.qty)]

		for batch_no, qty in batches:
			rows.append(
				{
					"idx": line.idx,
					"item_code": line.item_code,
					"item_name": line.item_name or line.item_code,
					"batch_no": batch_no,
					"qty": abs(qty or 0),
					# Never derived from the quantity: on this site a single receipt
					# line has reached 14,137 blocks, and labels go on packages.
					"labels": 1,
				}
			)
	return rows


def _batches_by_bundle(bundles: set[str]) -> dict[str, list[tuple[str, float]]]:
	if not bundles:
		return {}
	out: dict[str, list[tuple[str, float]]] = {}
	for entry in frappe.get_all(
		"Serial and Batch Entry",
		filters={"parent": ("in", bundles)},
		fields=["parent", "batch_no", "qty"],
		parent_doctype="Serial and Batch Bundle",
		limit_page_length=0,
	):
		out.setdefault(entry.parent, []).append((entry.batch_no, entry.qty))
	return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@frappe.whitelist()
def render_sheet(doctype: str, name: str, rows, guides: int | str = 0, layout: str = DEFAULT_LAYOUT) -> str:
	"""The full printable HTML: `rows` repeated by each row's label count."""
	if doctype not in SUPPORTED:
		frappe.throw(_("{0} does not carry material labels.").format(doctype))
	frappe.has_permission(doctype, "read", doc=name, throw=True)

	if isinstance(rows, str):
		rows = frappe.parse_json(rows)
	guides = frappe.utils.cint(guides)

	doc = frappe.get_doc(doctype, name)
	header = _incoming_header(doc) if SUPPORTED[doctype] == "incoming" else _outgoing_header(doc)
	so_by_idx = _sales_orders_by_idx(doc) if SUPPORTED[doctype] == "outgoing" else {}

	labels = []
	for row in rows or []:
		count = frappe.utils.cint(row.get("labels"))
		if count < 1:
			continue
		context = dict(header)
		context.update(
			{
				"item_name": row.get("item_name") or row.get("item_code"),
				"item_code": row.get("item_code"),
				"batch_no": row.get("batch_no"),
			}
		)
		if so_by_idx:
			context["sales_order"] = so_by_idx.get(frappe.utils.cint(row.get("idx"))) or ""
		# The barcode is identical for every copy of a batch, so render it once.
		# Without a batch it carries the item code, which every such item holds as
		# an Item Barcode (SOP-006 setup), so the scan still resolves.
		context["barcode"] = code128_svg(row.get("batch_no") or row.get("item_code"))
		html = _label_html(context, SUPPORTED[doctype])
		labels.extend([html] * count)

	if not labels:
		frappe.throw(_("Nothing to print: every line was set to zero labels."))

	return _wrap(labels, layout=layout, guides=guides, title=f"{doctype} {name}")


def _incoming_header(doc) -> dict:
	return {
		"supplier": doc.get("supplier_name") or doc.get("supplier") or "",
		"date": format_date(doc.get("posting_date")),
		"reference": doc.name,
		"challan": doc.get("supplier_delivery_note") or "",
	}


def _outgoing_header(doc) -> dict:
	return {
		"customer": doc.get("customer_name") or doc.get("customer") or "",
		"date": format_date(doc.get("posting_date")),
		"reference": doc.name,
		# po_no is a Small Text and people paste more than a number into it.
		"po_no": (doc.get("po_no") or "").strip().splitlines()[0] if doc.get("po_no") else "",
	}


def _sales_orders_by_idx(doc) -> dict[int, str]:
	return {row.idx: (row.get("against_sales_order") or "") for row in doc.get("items") or []}


def _label_html(ctx: dict, kind: str) -> str:
	esc = frappe.utils.escape_html
	batch = ctx.get("batch_no")
	barcode = ctx.get("barcode") or ""

	code_block = (
		f'<div class="hcc-bc">{barcode}</div><div class="hcc-batch">{esc(batch)}</div>'
		if batch and barcode
		else (
			f'<div class="hcc-batch">{esc(batch)}</div>'
			if batch
			else f'<div class="hcc-bc">{barcode}</div><div class="hcc-batch">{esc(ctx.get("item_code"))}</div>'
			if barcode
			else f'<div class="hcc-nobatch">{esc(_("No batch"))}</div>'
		)
	)

	if kind == "stock":
		facts = [
			(_("Supplier"), ctx.get("supplier")),
			(_("Received"), ctx.get("date")),
			(_("Store"), ctx.get("warehouse")),
		]
	elif kind == "incoming":
		facts = [
			(_("Supplier"), ctx.get("supplier")),
			(_("Received"), ctx.get("date")),
		]
	else:
		facts = [
			(_("Customer"), ctx.get("customer")),
			(_("Customer PO"), ctx.get("po_no")),
			(_("Sales Order"), ctx.get("sales_order")),
		]

	rows = "".join(
		f'<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>' for label, value in facts if value
	)

	return f"""<div class="hcc-label">
  <div class="hcc-top">
    <img class="hcc-logo" src="{LOGO}">
    <div class="hcc-id">
      <div class="hcc-code">{esc(ctx.get('item_code'))}</div>
      <div class="hcc-item" title="{esc(ctx.get('item_name'))}">{esc(ctx.get('item_name') if ctx.get('item_name') != ctx.get('item_code') else '')}</div>
    </div>
  </div>
  {code_block}
  <table class="hcc-facts">{rows}</table>
  <div class="hcc-ref">{esc(ctx.get('reference'))}</div>
</div>"""


def _wrap(labels: list[str], layout: str = DEFAULT_LAYOUT, guides: int = 0, title: str = "Labels") -> str:
	lay = LAYOUTS.get(layout) or LAYOUTS[DEFAULT_LAYOUT]
	w, h = lay["w"], lay["h"]
	if lay.get("sheet"):
		s = SHEETS[layout if layout in SHEETS else DEFAULT_LAYOUT]
		per_sheet = s["cols"] * s["rows"]
		small = h < 40
		pages = []
		for page_start in range(0, len(labels), per_sheet):
			page = labels[page_start : page_start + per_sheet]
			cells = "".join(page)
			# Pad the last sheet so the grid keeps its shape and nothing reflows.
			cells += '<div class="hcc-label hcc-blank"></div>' * (per_sheet - len(page))
			pages.append(f'<div class="hcc-sheet">{cells}</div>')
		body = "".join(pages)
		page_css = f"""
  @page {{ size: A4; margin: 0; }}
  .hcc-sheet {{
    width: 210mm; height: 297mm; box-sizing: border-box;
    padding: {s["margin_top"]}mm {s["margin_side"]}mm;
    display: flex; flex-wrap: wrap;
    align-content: flex-start;
    column-gap: {s["col_gap"]}mm; row-gap: 0;
    page-break-after: always; break-after: page;
  }}
  .hcc-sheet:last-child {{ page-break-after: auto; break-after: auto; }}
  .hcc-label {{ padding: 4mm 5mm; }}"""
		if small:
			# 39 x 35 mm: no logo, everything a size down, barcode across the label
			page_css += """
  .hcc-label { padding: 1.5mm 1.5mm 1mm; }
  .hcc-logo { display: none; }
  .hcc-code { font-size: 7.5pt; }
  .hcc-item { font-size: 6pt; line-height: 1.1; }
  .hcc-bc, .hcc-bc svg { height: 7mm; width: 100%; }
  .hcc-bc { margin-top: 1mm; }
  .hcc-batch { font-size: 7pt; letter-spacing: 0; }
  .hcc-nobatch { font-size: 6pt; margin: 1mm 0; }
  .hcc-facts { font-size: 5.5pt; line-height: 1.15; }
  .hcc-facts th { width: 9mm; padding-right: 1mm; }
  .hcc-facts td { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
  .hcc-ref { display: none; }"""
	else:
		# a roll: every label is its own page of exactly the label's size
		body = "".join(labels)
		small = h < 35
		page_css = f"""
  @page {{ size: {w}mm {h}mm; margin: 0; }}
  .hcc-label {{ padding: {1.5 if small else 2.5}mm {2 if small else 3.5}mm; page-break-after: always; break-after: page; }}
  .hcc-label:last-child {{ page-break-after: auto; break-after: auto; }}
  .hcc-logo {{ height: 6mm; {"display:none;" if small else ""} }}
  .hcc-code {{ font-size: {8 if small else 10}pt; }}
  .hcc-item {{ font-size: {6.5 if small else 8.5}pt; -webkit-line-clamp: {1 if small else 2}; }}
  .hcc-bc, .hcc-bc svg {{ height: {8 if small else 10}mm; }}
  .hcc-batch {{ font-size: {8 if small else 11}pt; }}
  .hcc-facts {{ font-size: 7.5pt; {"display:none;" if small else ""} }}
  .hcc-facts th {{ width: 16mm; }}
  .hcc-ref {{ {"display:none;" if small else ""} }}"""

	guide_css = (
		".hcc-label{outline:0.2mm dashed #bbb;outline-offset:-0.1mm}" if guides else ""
	)

	return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{frappe.utils.escape_html(title)}</title>
<style>
  html,body {{ margin:0; padding:0; background:#fff; }}
  body {{ font-family: Helvetica, Arial, sans-serif; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .hcc-label {{
    width: {w}mm; height: {h}mm; box-sizing: border-box;
    overflow: hidden; display: flex; flex-direction: column;
  }}
  .hcc-blank {{ visibility: hidden; }}
  .hcc-top {{ display:flex; align-items:center; gap:3mm; }}
  .hcc-logo {{ height: 8mm; width:auto; flex: none; }}
  .hcc-id {{ min-width: 0; }}
  .hcc-code {{ font-size: 11pt; font-weight: 700; line-height: 1.15; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
  .hcc-item {{
    font-size: 9pt; line-height: 1.15;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  }}
  .hcc-bc {{ margin: 1.5mm 0 0; height: 11mm; }}
  .hcc-bc svg {{ height: 11mm; width: auto; max-width: 100%; display:block; }}
  .hcc-batch {{ font-size: 12pt; font-weight: 700; letter-spacing: 0.4pt; margin-top: 0.5mm; }}
  .hcc-nobatch {{ font-size: 9pt; color:#888; margin: 2mm 0; font-style: italic; }}
  .hcc-facts {{ margin-top: auto; border-collapse: collapse; width:100%; font-size: 8.5pt; }}
  .hcc-facts th {{ text-align:left; font-weight:600; color:#555; padding:0 2mm 0 0; white-space:nowrap;
                   vertical-align:top; width: 22mm; }}
  .hcc-facts td {{ text-align:left; padding:0; }}
  .hcc-ref {{ font-size: 7pt; color:#999; margin-top: 1mm; }}
  {page_css}
  {guide_css}
</style></head>
<body onload="window.print()">{body}</body></html>"""


# ---------------------------------------------------------------------------
# Stock on the shelves
# ---------------------------------------------------------------------------


@frappe.whitelist()
def layouts() -> list[dict]:
	return [{"value": k, "label": _(v["label"]),
	         "per_sheet": SHEETS[k]["cols"] * SHEETS[k]["rows"] if v.get("sheet") else 0}
	        for k, v in LAYOUTS.items()]


def _batch_balances(warehouse=None, item_code=None, batch_no=None) -> list[dict]:
	"""Batch-wise balance per warehouse from the ledger: bundles for current
	entries, the SLE's own batch_no for entries made before bundles existed."""
	cond, args = ["sle.is_cancelled = 0"], {}
	for field, value in (("warehouse", warehouse), ("item_code", item_code)):
		if value:
			cond.append(f"sle.{field} = %({field})s")
			args[field] = value
	where = " and ".join(cond)
	bcond = " and sbe.batch_no = %(batch_no)s" if batch_no else ""
	lcond = " and sle.batch_no = %(batch_no)s" if batch_no else ""
	args["batch_no"] = batch_no
	return frappe.db.sql(
		f"""select item_code, warehouse, batch_no, sum(qty) as qty from (
			select sle.item_code, sle.warehouse, sbe.batch_no, sbe.qty
			from `tabStock Ledger Entry` sle
			join `tabSerial and Batch Entry` sbe on sbe.parent = sle.serial_and_batch_bundle
			where {where} and ifnull(sbe.batch_no, '') != ''{bcond}
			union all
			select sle.item_code, sle.warehouse, sle.batch_no, sle.actual_qty
			from `tabStock Ledger Entry` sle
			where {where} and ifnull(sle.serial_and_batch_bundle, '') = '' and ifnull(sle.batch_no, '') != ''{lcond}
		) t group by item_code, warehouse, batch_no having abs(sum(qty)) > 0.0001""",
		args,
		as_dict=True,
	)


@frappe.whitelist()
def stock_rows(warehouse: str | None = None, item_group: str | None = None, item_code: str | None = None) -> list[dict]:
	"""One row per item (and batch) in stock, for labelling what is already on the
	shelves. One label each by default; the count is the operator's."""
	frappe.has_permission("Bin", "read", throw=True)
	items = {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters={"is_stock_item": 1, "disabled": 0, **({"name": item_code} if item_code else {}),
			         **({"item_group": ("descendants of (inclusive)", item_group)} if item_group else {})},
			fields=["name", "item_name", "has_batch_no", "stock_uom", "item_group"],
			limit_page_length=0,
		)
	}
	if not items:
		return []
	rows = []
	bins = frappe.get_all(
		"Bin",
		filters={"actual_qty": (">", 0), "item_code": ("in", list(items)), **({"warehouse": warehouse} if warehouse else {})},
		fields=["item_code", "warehouse", "actual_qty"],
		limit_page_length=0,
	)
	batched = set()
	for b in bins:
		item = items[b.item_code]
		if item.has_batch_no:
			batched.add((b.item_code, b.warehouse))
			continue
		rows.append({"item_code": b.item_code, "item_name": item.item_name, "batch_no": None, "warehouse": b.warehouse,
		             "qty": b.actual_qty, "uom": item.stock_uom, "labels": 1})
	if batched:
		for r in _batch_balances(warehouse=warehouse, item_code=item_code):
			if (r.item_code, r.warehouse) in batched and r.qty > 0:
				item = items[r.item_code]
				rows.append({"item_code": r.item_code, "item_name": item.item_name, "batch_no": r.batch_no,
				             "warehouse": r.warehouse, "qty": r.qty, "uom": item.stock_uom, "labels": 1})
	rows.sort(key=lambda r: (r["warehouse"], r["item_code"], r["batch_no"] or ""))
	return rows


@frappe.whitelist()
def render_stock(rows, layout: str = DEFAULT_LAYOUT, guides: int | str = 0) -> str:
	"""Labels for stock already on the shelves: rows of item, batch, warehouse, count."""
	frappe.has_permission("Bin", "read", throw=True)
	if isinstance(rows, str):
		rows = frappe.parse_json(rows)
	batches = {
		b.name: b
		for b in frappe.get_all(
			"Batch",
			filters={"name": ("in", [r.get("batch_no") for r in rows if r.get("batch_no")] or [""])},
			fields=["name", "supplier", "manufacturing_date", "creation", "reference_doctype", "reference_name"],
		)
	}
	receipts = _receipts({b.reference_name for b in batches.values() if b.reference_doctype == "Purchase Receipt"})
	suppliers = {}
	labels = []
	for row in rows or []:
		count = frappe.utils.cint(row.get("labels"))
		if count < 1 or not row.get("item_code"):
			continue
		batch = batches.get(row.get("batch_no"))
		receipt = receipts.get(batch.reference_name) if batch and batch.reference_doctype == "Purchase Receipt" else None
		supplier = (receipt and receipt.supplier) or (batch and batch.supplier)
		if supplier and supplier not in suppliers:
			suppliers[supplier] = frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier
		context = {
			"item_name": row.get("item_name") or frappe.db.get_value("Item", row["item_code"], "item_name"),
			"item_code": row["item_code"],
			"batch_no": row.get("batch_no"),
			"supplier": suppliers.get(supplier, ""),
			# the date of receipt for a bought-in batch, else when the batch was made
			"date": format_date(receipt.posting_date if receipt else (batch.manufacturing_date or batch.creation)) if batch else "",
			"warehouse": row.get("warehouse") or "",
			"reference": row["item_code"] if row.get("batch_no") else "",
			"barcode": code128_svg(row.get("batch_no") or row["item_code"]),
		}
		labels.extend([_label_html(context, "stock")] * count)
	if not labels:
		frappe.throw(_("Nothing to print: every line was set to zero labels."))
	return _wrap(labels, layout=layout, guides=guides, title=_("Stock labels"))


def _receipts(names: set[str]) -> dict:
	"""Posting date and supplier of the receipts batches came in on."""
	if not names:
		return {}
	return {
		r.name: r
		for r in frappe.get_all("Purchase Receipt", filters={"name": ("in", list(names))},
		                        fields=["name", "supplier", "posting_date"])
	}


# ---------------------------------------------------------------------------
# Scan: what is this, where is it, where should it be
# ---------------------------------------------------------------------------


@frappe.whitelist()
def lookup(code: str) -> dict:
	"""Everything Stores needs from one scanned label."""
	from erpnext.stock.utils import scan_barcode

	frappe.has_permission("Bin", "read", throw=True)
	code = (code or "").strip()
	if not code:
		return {}
	hit = scan_barcode(code) or {}
	item_code, batch_no = hit.get("item_code"), hit.get("batch_no")
	if not item_code and frappe.db.exists("Item", code):
		item_code = code
	if not item_code:
		return {"found": False, "code": code}

	item = frappe.db.get_value("Item", item_code, ["item_name", "item_group", "stock_uom", "has_batch_no", "image"], as_dict=True)
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	# where it lives: the item's default warehouse, else its group's, else the site's
	home = frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")
	if not home:
		home = frappe.db.get_value("Item Default", {"parent": item.item_group, "parenttype": "Item Group", "company": company},
		                           "default_warehouse")
	if not home:
		home = frappe.db.get_single_value("Stock Settings", "default_warehouse")

	if batch_no:
		where = [{"warehouse": r.warehouse, "qty": r.qty} for r in _batch_balances(item_code=item_code, batch_no=batch_no)]
	else:
		where = [{"warehouse": b.warehouse, "qty": b.actual_qty}
		         for b in frappe.get_all("Bin", filters={"item_code": item_code, "actual_qty": ("!=", 0)},
		                                 fields=["warehouse", "actual_qty"], order_by="actual_qty desc")]

	# stock waiting in Inspection Required belongs where its inspection sends it
	from iso_compliance.overrides.inspection_flow import _is_inspection_warehouse

	inspection = []
	if any(_is_inspection_warehouse(w["warehouse"]) for w in where):
		inspection = _waiting_lots(item_code, batch_no)
	batch = frappe.db.get_value("Batch", batch_no, ["supplier", "manufacturing_date", "expiry_date", "reference_doctype",
	                                                  "reference_name"], as_dict=True) if batch_no else None
	return {
		"found": True,
		"code": code,
		"item_code": item_code,
		"item_name": item.item_name,
		"item_group": item.item_group,
		"uom": item.stock_uom,
		"batch_no": batch_no,
		"batch": batch,
		"home": home,
		"where": where,
		"inspection": inspection,
	}


def _waiting_lots(item_code, batch_no) -> list[dict]:
	"""Receipts and Manufacture entries holding this item in Inspection Required,
	with where each lot goes and how far it has got: not inspected, inspection
	started, or inspected with its transfer drafted but not yet posted."""
	from iso_compliance.overrides.inspection_flow import _is_inspection_warehouse, _row_batch, waiting

	parents = set()
	for dt, child, field in (("Purchase Receipt", "Purchase Receipt Item", "warehouse"),
	                         ("Stock Entry", "Stock Entry Detail", "t_warehouse")):
		for r in frappe.get_all(child, filters={"item_code": item_code, "docstatus": 1, field: ("like", "Inspection Required%")},
		                        fields=["parent", field], order_by="creation desc", limit=50):
			if _is_inspection_warehouse(r.get(field)):
				parents.add((dt, child, r.parent))
	out = []
	for dt, child, name in sorted(parents):
		for r in waiting(dt, name):
			if r["item_code"] != item_code:
				continue
			if batch_no:
				src = frappe.db.get_value(child, r["row"], ["batch_no", "serial_and_batch_bundle"], as_dict=True)
				if _row_batch(src) != batch_no:
					continue
			transfer = r["inspection"] and frappe.db.get_value("Quality Inspection", r["inspection"], "custom_transfer_entry")
			if r["state"] == "done" and (not transfer or frappe.db.get_value("Stock Entry", transfer, "docstatus") == 1):
				continue  # released and moved
			out.append(dict(r, reference_type=dt, reference_name=name, transfer=transfer))
	return out
