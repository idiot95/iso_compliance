# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Material identification labels, printed eight to an A4 sheet.

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

Geometry is Avery L7165 and its many equivalents: 99.1 x 67.7 mm, two across and
four down, 13.1 mm top and bottom margins, 4.65 mm side margins, 2.5 mm between
the columns. Print the guides version on plain paper first and hold it against a
label sheet to check the printer is not scaling the page.
"""

from __future__ import annotations

import io

import frappe
from frappe import _
from frappe.utils import format_date

LOGO = "/assets/iso_compliance/images/hcc-mark.png"

#: Avery L7165 and equivalents, in millimetres.
SHEET = {
	"label_w": 99.1,
	"label_h": 67.7,
	"cols": 2,
	"rows": 4,
	"margin_top": 13.1,
	"margin_side": 4.65,
	"col_gap": 2.5,
}
PER_SHEET = SHEET["cols"] * SHEET["rows"]

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
	return svg[start:] if start != -1 else ""


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
def render_sheet(doctype: str, name: str, rows, guides: int | str = 0) -> str:
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
		context["barcode"] = code128_svg(row.get("batch_no"))
		html = _label_html(context, SUPPORTED[doctype])
		labels.extend([html] * count)

	if not labels:
		frappe.throw(_("Nothing to print: every line was set to zero labels."))

	return _wrap_sheets(labels, guides=guides, title=f"{doctype} {name}")


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
			else f'<div class="hcc-nobatch">{esc(_("No batch"))}</div>'
		)
	)

	if kind == "incoming":
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
    <div class="hcc-item" title="{esc(ctx.get('item_name'))}">{esc(ctx.get('item_name'))}</div>
  </div>
  {code_block}
  <table class="hcc-facts">{rows}</table>
  <div class="hcc-ref">{esc(ctx.get('reference'))}</div>
</div>"""


def _wrap_sheets(labels: list[str], guides: int = 0, title: str = "Labels") -> str:
	s = SHEET
	sheets = []
	for page_start in range(0, len(labels), PER_SHEET):
		page = labels[page_start : page_start + PER_SHEET]
		cells = "".join(page)
		# Pad the last sheet so the grid keeps its shape and nothing reflows.
		cells += '<div class="hcc-label hcc-blank"></div>' * (PER_SHEET - len(page))
		sheets.append(f'<div class="hcc-sheet">{cells}</div>')

	guide_css = (
		".hcc-label{outline:0.2mm dashed #bbb;outline-offset:-0.1mm}" if guides else ""
	)

	return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{frappe.utils.escape_html(title)}</title>
<style>
  @page {{ size: A4; margin: 0; }}
  html,body {{ margin:0; padding:0; background:#fff; }}
  body {{ font-family: Helvetica, Arial, sans-serif; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .hcc-sheet {{
    width: 210mm; height: 297mm; box-sizing: border-box;
    padding: {s["margin_top"]}mm {s["margin_side"]}mm;
    display: flex; flex-wrap: wrap;
    align-content: flex-start;
    column-gap: {s["col_gap"]}mm; row-gap: 0;
    page-break-after: always; break-after: page;
  }}
  .hcc-sheet:last-child {{ page-break-after: auto; break-after: auto; }}
  .hcc-label {{
    width: {s["label_w"]}mm; height: {s["label_h"]}mm; box-sizing: border-box;
    padding: 4mm 5mm; overflow: hidden;
    display: flex; flex-direction: column;
  }}
  .hcc-blank {{ visibility: hidden; }}
  .hcc-top {{ display:flex; align-items:center; gap:3mm; }}
  .hcc-logo {{ height: 8mm; width:auto; flex: none; }}
  .hcc-item {{
    font-size: 11pt; font-weight: 700; line-height: 1.15;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  }}
  .hcc-bc {{ margin: 1.5mm 0 0; height: 11mm; }}
  .hcc-bc svg {{ height: 11mm; width: auto; display:block; }}
  .hcc-batch {{ font-size: 12pt; font-weight: 700; letter-spacing: 0.4pt; margin-top: 0.5mm; }}
  .hcc-nobatch {{ font-size: 9pt; color:#888; margin: 2mm 0; font-style: italic; }}
  .hcc-facts {{ margin-top: auto; border-collapse: collapse; width:100%; font-size: 8.5pt; }}
  .hcc-facts th {{ text-align:left; font-weight:600; color:#555; padding:0 2mm 0 0; white-space:nowrap;
                   vertical-align:top; width: 22mm; }}
  .hcc-facts td {{ text-align:left; padding:0; }}
  .hcc-ref {{ font-size: 7pt; color:#999; margin-top: 1mm; }}
  {guide_css}
</style></head>
<body onload="window.print()">{"".join(sheets)}</body></html>"""
