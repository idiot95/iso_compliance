# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Drawing templates: validation, tagging to BOMs/Items, drawings, revisions.

A *drawing template* is a Quality Inspection Template with at least one row
whose `custom_row_type` is set. Every other template is a legacy template and
everything here leaves it alone (SPEC §4.0).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from iso_compliance.qi import tolerance as T
from iso_compliance.qi.api import require_quality_manager

ROWS = "item_quality_inspection_parameter"
STAGES = (
	"custom_stage_incoming",
	"custom_stage_in_process",
	"custom_stage_final",
	"custom_stage_fai",
	"custom_stage_type_test",
)
DRAWING_EXTENSIONS = ("pdf", "png", "jpg", "jpeg")


# ------------------------------------------------------------------ guard --


def is_drawing_template(template) -> bool:
	"""True for a template name or doc that has drawing rows."""
	if not template:
		return False
	if isinstance(template, str):
		return bool(
			frappe.db.exists(
				"Item Quality Inspection Parameter",
				{"parenttype": "Quality Inspection Template", "parent": template, "custom_row_type": ("is", "set")},
			)
		)
	return any(r.get("custom_row_type") for r in template.get(ROWS) or [])


# --------------------------------------------------------------- validate --


def validate(doc, method=None):
	"""doc_events: Quality Inspection Template.validate"""
	if not doc.get(ROWS) and not doc.custom_item:
		# the core rule (rows mandatory), kept for every template that is not a
		# drawing template in the making
		frappe.throw(_("Add at least one parameter."), frappe.MandatoryError)
	_link_drawing(doc)
	if not is_drawing_template(doc):
		return
	general = T.general_class(doc.custom_general_tolerance) if doc.custom_general_tolerance else None
	_assign_balloons(doc)
	errors = []
	for row in doc.get(ROWS):
		if not row.custom_row_type:
			errors.append(_("Row {0}: every row of a drawing template needs a row type").format(row.idx))
			continue
		try:
			_apply_row(row, general)
		except T.ToleranceError as e:
			errors.append(_("Balloon {0}: {1}").format(row.custom_balloon_no, e))
		_clean_instruments(row)
		if not any(cint(row.get(f)) for f in STAGES):
			errors.append(_("Balloon {0}: tick at least one stage").format(row.custom_balloon_no))
		if row.custom_row_type == "Material" and not cint(row.custom_stage_incoming):
			errors.append(_("Balloon {0}: a Material row is read off the supplier's certificate, so tick Incoming").format(row.custom_balloon_no))
		if row.custom_row_type == "Test" and not row.custom_test_method:
			errors.append(_("Balloon {0}: a Test row needs a Test Method").format(row.custom_balloon_no))
		if row.custom_frequency in ("Every N lots", "Every N months") and cint(row.custom_frequency_n) < 1:
			errors.append(_("Balloon {0}: enter N for '{1}'").format(row.custom_balloon_no, row.custom_frequency))
		if row.custom_sampling == "Fixed number" and cint(row.custom_fixed_count) < 1:
			errors.append(_("Balloon {0}: enter how many pieces").format(row.custom_balloon_no))
	if errors:
		frappe.throw("<br>".join(errors), title=_("Drawing template"))
	_check_lock(doc)


def _assign_balloons(doc):
	rows = doc.get(ROWS)
	seen = {}
	for row in rows:
		key = (row.custom_balloon_no or "").strip()
		if key:
			if key in seen:
				frappe.throw(_("Balloon {0} is used on rows {1} and {2}").format(key, seen[key], row.idx))
			seen[key] = row.idx
			row.custom_balloon_no = key
	numbers = [int(k) for k in seen if k.isdigit()]
	nxt = {"Dimension": max(numbers, default=0) + 1}
	for prefix in ("T", "V", "M"):
		n = [int(k[1:]) for k in seen if k[:1] == prefix and k[1:].isdigit()]
		nxt[prefix] = max(n, default=0) + 1
	for row in rows:
		if row.custom_balloon_no or not row.custom_row_type:
			continue
		if row.custom_row_type == "Dimension":
			row.custom_balloon_no = str(nxt["Dimension"])
			nxt["Dimension"] += 1
		else:
			p = {"Test": "T", "Visual": "V", "Material": "M"}.get(row.custom_row_type, "V")
			row.custom_balloon_no = f"{p}{nxt[p]}"
			nxt[p] += 1


def row_limits(row, general=None) -> dict | None:
	"""Limits for one template row from its tolerance inputs, or None when
	the row keeps its own min/max (a Test row without a tolerance type)."""
	ty = row.get("custom_tolerance_type")
	if not ty:
		return None
	kw = {}
	if ty in (T.SYMMETRIC, T.ANGLE):
		if not flt(row.get("custom_tol")):
			raise T.ToleranceError(_("enter the ± tolerance"))
		kw = {"nominal": flt(row.custom_nominal), "tol": flt(row.custom_tol)}
	elif ty == T.DEVIATIONS:
		kw = {"nominal": flt(row.custom_nominal), "upper_dev": flt(row.custom_upper_dev), "lower_dev": flt(row.custom_lower_dev)}
	elif ty == T.LIMITS:
		kw = {"lower": flt(row.min_value), "upper": flt(row.max_value)}
	elif ty == T.MAX_ONLY:
		kw = {"upper": flt(row.max_value)}
	elif ty == T.MIN_ONLY:
		kw = {"lower": flt(row.min_value)}
	elif ty == T.ISO_FIT:
		kw = {"nominal": flt(row.custom_nominal), "fit_class": row.custom_fit_class}
	elif ty == T.GENERAL:
		kw = {"nominal": flt(row.custom_nominal), "general": general}
	elif ty == T.GEOMETRIC:
		if not flt(row.get("custom_tol")):
			raise T.ToleranceError(_("enter the tolerance zone"))
		kw = {"zone": flt(row.custom_tol)}
	elif ty == T.REFERENCE:
		kw = {"nominal": flt(row.custom_nominal)}
	return T.limits(ty, **kw)


def _apply_row(row, general):
	if row.custom_row_type == "Visual":
		row.custom_tolerance_type = None
		row.numeric = 0
		row.value = "OK"
		row.min_value = row.max_value = 0
		row.formula_based_criteria = 0
		return
	if row.custom_row_type == "Dimension" and not row.custom_tolerance_type:
		raise T.ToleranceError(_("choose a tolerance type"))
	lim = row_limits(row, general)
	if lim is None:  # Test / Material row judged on its own min/max
		row.numeric = 1
		if flt(row.min_value) > flt(row.max_value):
			raise T.ToleranceError(_("Min Value is above Max Value"))
		return
	row.numeric = lim["numeric"]
	row.min_value = lim["min_value"]
	row.max_value = lim["max_value"]
	row.value = lim["value"]
	row.formula_based_criteria = 0


def _signature(doc) -> dict:
	sig = {"__drawing": doc.get("custom_drawing") or ""}
	for r in doc.get(ROWS) or []:
		if r.get("custom_row_type"):
			sig[r.custom_balloon_no] = (
				r.custom_row_type, r.specification, flt(r.min_value, 6), flt(r.max_value, 6),
				r.value or "", cint(r.numeric), tuple(cint(r.get(f)) for f in STAGES),
			)
	return sig


def _check_lock(doc):
	before = doc.get_doc_before_save()
	if not before or not cint(before.custom_locked):
		return
	if _signature(before) != _signature(doc):
		frappe.throw(
			_("This template is locked because inspections have been submitted against it. "
			  "Drawing, balloons, limits and stages can only change through New Revision."),
			title=_("Template locked"),
		)


# ---------------------------------------------------------------- tagging --


@frappe.whitelist()
def tagging_options(template: str) -> dict:
	doc = frappe.get_doc("Quality Inspection Template", template)
	doc.check_permission("read")
	item = doc.custom_item
	boms = []
	if item:
		boms = frappe.get_all(
			"BOM",
			filters={"item": item, "docstatus": 1, "is_active": 1},
			fields=["name", "is_default", "quality_inspection_template"],
			order_by="is_default desc, name",
		)
	return {
		"item": item,
		"item_template": item and frappe.db.get_value("Item", item, "quality_inspection_template"),
		"boms": boms,
	}


@frappe.whitelist()
def tag_template(template: str, boms=None, item: str | None = None, overwrite=0) -> dict:
	"""Point BOMs (and, when safe, the Item) at this template.

	Nothing is written while any target holds a *different* template, unless
	`overwrite` is set: the caller shows the conflicts and asks first. The Item
	is tagged only when every active BOM of it ends up on this template (or it
	has none), so an item group's default survives on items with several
	drawings.
	"""
	require_quality_manager()
	if not is_drawing_template(template):
		frappe.throw(_("Add drawing rows to the template before tagging it."))
	boms = frappe.parse_json(boms) if isinstance(boms, str) else (boms or [])
	targets = [("BOM", b) for b in boms]

	skipped_item = None
	if item:
		active = frappe.get_all("BOM", filters={"item": item, "docstatus": 1, "is_active": 1}, fields=["name", "quality_inspection_template"])
		after = {b.name: (template if b.name in boms else b.quality_inspection_template) for b in active}
		if all(t == template for t in after.values()):
			targets.append(("Item", item))
		else:
			skipped_item = item

	conflicts = []
	for dt, name in targets:
		current = frappe.db.get_value(dt, name, "quality_inspection_template")
		if current and current != template:
			conflicts.append({"doctype": dt, "name": name, "current": current})
	if conflicts and not cint(overwrite):
		return {"conflicts": conflicts, "skipped_item": skipped_item}

	tagged = []
	for dt, name in targets:
		current = frappe.db.get_value(dt, name, "quality_inspection_template")
		if current == template:
			continue
		frappe.db.set_value(dt, name, "quality_inspection_template", template)
		frappe.get_doc(dt, name).add_comment(
			"Info", _("Inspection template: {0} → {1}").format(current or _("none"), template)
		)
		tagged.append({"doctype": dt, "name": name, "previous": current})
	return {"tagged": tagged, "skipped_item": skipped_item}


@frappe.whitelist()
def untag(template: str, doctype: str, name: str):
	require_quality_manager()
	if doctype not in ("BOM", "Item"):
		frappe.throw(_("Only BOMs and Items are tagged"))
	if frappe.db.get_value(doctype, name, "quality_inspection_template") != template:
		return
	frappe.db.set_value(doctype, name, "quality_inspection_template", None)
	frappe.get_doc(doctype, name).add_comment("Info", _("Inspection template {0} removed").format(template))


@frappe.whitelist()
def used_by(template: str) -> dict:
	return {
		"boms": frappe.get_all("BOM", filters={"quality_inspection_template": template, "docstatus": ("<", 2)},
		                       fields=["name", "item", "is_active", "is_default"], order_by="name"),
		"items": frappe.get_all("Item", filters={"quality_inspection_template": template},
		                        fields=["name", "item_name"], order_by="name"),
		"groups": frappe.get_all("Item Group", filters={"custom_default_qi_template": template}, pluck="name"),
	}


# --------------------------------------------------------------- drawings --


@frappe.whitelist()
def drawing_options(item: str) -> list[dict]:
	"""Drawings attached to the item's submitted BOMs and to the Item."""
	boms = frappe.get_all("BOM", filters={"item": item, "docstatus": 1}, fields=["name", "is_active", "is_default"])
	bom_info = {b.name: b for b in boms}
	files = frappe.get_all(
		"File",
		filters=[["attached_to_doctype", "=", "BOM"], ["attached_to_name", "in", list(bom_info) or [""]]],
		or_filters=None,
		fields=["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name", "is_private", "creation"],
	) + frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Item", "attached_to_name": item},
		fields=["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name", "is_private", "creation"],
	)
	out = []
	for f in files:
		if (f.file_name or "").rsplit(".", 1)[-1].lower() not in DRAWING_EXTENSIONS:
			continue
		b = bom_info.get(f.attached_to_name)
		f["bom_active"] = b and b.is_active
		f["bom_default"] = b and b.is_default
		out.append(f)
	out.sort(key=lambda f: (not f.get("bom_default"), not f.get("bom_active"), f.file_name or ""))
	return out


def _link_drawing(doc):
	"""The drawing follows "Drawing on the BOM" as part of the save itself, so a
	later save from an open form can't blank it again."""
	file = doc.get("custom_drawing_file")
	if not file or (doc.custom_drawing and not doc.has_value_changed("custom_drawing_file")):
		return  # unchanged: a drawing uploaded straight into Drawing stays
	src = frappe.db.get_value("File", file, ["file_url", "content_hash"], as_dict=True)
	if not src or src.file_url == doc.custom_drawing:
		return
	if cint(doc.custom_locked):
		frappe.throw(_("The template is locked; use New Revision to change the drawing."))
	frappe.has_permission("File", "read", file, throw=True)
	doc.custom_drawing = src.file_url
	doc.custom_drawing_hash = src.content_hash or src.file_url


def on_update(doc, method=None):
	"""doc_events: Quality Inspection Template.on_update. The template's own File
	record pointing at the same stored file (no copy), so deleting the BOM's File
	record leaves the drawing in place -- Frappe removes a stored file only when
	no File record points at it any more."""
	url = doc.get("custom_drawing")
	if not url or frappe.db.exists("File", {"file_url": url, "attached_to_doctype": doc.doctype,
	                                         "attached_to_name": doc.name}):
		return
	src = frappe.db.get_value("File", {"file_url": url}, ["file_name", "is_private"], as_dict=True)
	if not src:
		return
	frappe.get_doc({
		"doctype": "File",
		"file_url": url,
		"file_name": src.file_name,
		"is_private": src.is_private,
		"attached_to_doctype": doc.doctype,
		"attached_to_name": doc.name,
		"attached_to_field": "custom_drawing",
	}).insert(ignore_permissions=True)


# ------------------------------------------------------------ instruments --

#: The Asset Category the measuring instruments are kept under.
INSTRUMENT_CATEGORY = "Measuring Instruments"


@frappe.whitelist()
def measuring_instruments() -> list[dict]:
	"""Every measuring instrument Asset, grouped client side by its item."""
	return frappe.db.sql(
		"""select a.name, a.asset_name, a.item_code, i.item_name, a.location
		from `tabAsset` a join `tabItem` i on i.name = a.item_code
		where a.asset_category = %s and a.docstatus < 2
		order by i.item_name, a.name""",
		INSTRUMENT_CATEGORY,
		as_dict=True,
	)


def instrument_list(text) -> list[str]:
	return [x.strip() for x in (text or "").splitlines() if x.strip()]


def _clean_instruments(row):
	names = list(dict.fromkeys(instrument_list(row.get("custom_instruments"))))
	known = set(frappe.get_all("Asset", filters={"name": ("in", names or [""])}, pluck="name"))
	row.custom_instruments = "\n".join(n for n in names if n in known) or None


@frappe.whitelist()
def save_page_images(template: str, drawing_hash: str, pages) -> list[str]:
	"""Store the page images (JPEG) the builder rendered (data URLs), replacing the
	previous set. Called only when the drawing's hash changed."""
	require_quality_manager()
	import base64

	pages = frappe.parse_json(pages) if isinstance(pages, str) else pages
	doc = frappe.get_doc("Quality Inspection Template", template)
	for old in frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Quality Inspection Template", "attached_to_name": template,
		         "attached_to_field": "custom_drawing_pages"},
		pluck="name",
	):
		frappe.delete_doc("File", old, ignore_permissions=True)
	urls = []
	for i, data_url in enumerate(pages, 1):
		content = base64.b64decode(data_url.split(",", 1)[1])
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{frappe.scrub(template)[:60]}-page-{i}.jpg",
				"is_private": 0,  # files on this site are public (developer, 2026-10-13)
				"content": content,
				"attached_to_doctype": "Quality Inspection Template",
				"attached_to_name": template,
				"attached_to_field": "custom_drawing_pages",
			}
		).insert(ignore_permissions=True)
		urls.append(f.file_url)
	# not a change the user made: leave `modified` alone, or the open form's next save is refused
	doc.db_set("custom_drawing_pages", frappe.as_json({"hash": drawing_hash, "pages": urls}), update_modified=False)
	return urls


# -------------------------------------------------------------- revisions --


def suggested_name(drawing_no, revision, item) -> str:
	item_name = frappe.db.get_value("Item", item, "item_name") if item else ""
	parts = [p for p in (drawing_no, revision and f"Rev {revision}", item_name or item) if p]
	return " · ".join(parts)[:140]


@frappe.whitelist()
def new_revision(template: str, revision: str) -> str:
	"""Copy the template as the next drawing revision. The drawing is cleared
	(the new revision's drawing is picked afresh); balloon positions are kept
	for checking against it."""
	require_quality_manager()
	old = frappe.get_doc("Quality Inspection Template", template)
	new = frappe.copy_doc(old)
	new.custom_drawing_revision = revision
	for f in ("custom_drawing", "custom_drawing_hash", "custom_drawing_pages", "custom_superseded_by"):
		new.set(f, None)
	new.custom_locked = 0
	new.quality_inspection_template_name = suggested_name(old.custom_drawing_no, revision, old.custom_item)
	if frappe.db.exists("Quality Inspection Template", new.quality_inspection_template_name):
		frappe.throw(_("{0} already exists").format(new.quality_inspection_template_name))
	new.insert()
	return new.name


@frappe.whitelist()
def earlier_revisions(template: str) -> list[dict]:
	"""Other, not yet superseded templates of the same drawing and item that
	still have BOMs or Items on them: what a new revision can take over."""
	doc = frappe.get_doc("Quality Inspection Template", template)
	if not (doc.custom_drawing_no and doc.custom_item):
		return []
	out = []
	for name in frappe.get_all(
		"Quality Inspection Template",
		filters={"custom_drawing_no": doc.custom_drawing_no, "custom_item": doc.custom_item,
		         "name": ("!=", template), "custom_superseded_by": ("is", "not set")},
		pluck="name",
	):
		users = used_by(name)
		if users["boms"] or users["items"]:
			out.append({"name": name, **users})
	return out


@frappe.whitelist()
def supersede(old: str, new: str, boms=None, item: str | None = None) -> dict:
	"""Move the chosen BOMs/Item from the old revision to the new one and
	mark the old one superseded."""
	require_quality_manager()
	result = tag_template(new, boms=boms, item=item, overwrite=1)
	frappe.db.set_value("Quality Inspection Template", old, "custom_superseded_by", new)
	return result


# ------------------------------------------- starting from a BOM or Item --


@frappe.whitelist()
def start_options(item: str, bom: str | None = None) -> dict:
	"""For the BOM / Item "Inspection template" button: the drawing template
	already in use (to open it), else the drawings to start one from."""
	frappe.has_permission("Item", "read", item, throw=True)
	current = frappe.db.get_value("BOM", bom, "quality_inspection_template") if bom else None
	if not current:
		current = frappe.db.get_value("Item", item, "quality_inspection_template")
	boms = frappe.get_all("BOM", filters={"item": item, "docstatus": 1}, fields=["name", "is_default", "is_active"],
	                      order_by="is_default desc, is_active desc, name")
	drawings = drawing_options(item)
	if bom:
		drawings.sort(key=lambda f: f.get("attached_to_name") != bom)
	return {
		"item": item,
		"item_name": frappe.db.get_value("Item", item, "item_name"),
		"current": current if is_drawing_template(current) else None,
		"legacy": current if current and not is_drawing_template(current) else None,
		"boms": boms,
		"drawings": drawings,
	}


@frappe.whitelist()
def start_template(item: str, drawing_no: str | None = None, revision: str | None = None, file: str | None = None) -> str:
	"""Create the template for an item, with its drawing attached, and return
	its name: the builder then opens on the drawing."""
	require_quality_manager()
	name = suggested_name(drawing_no, revision, item) or item
	if frappe.db.exists("Quality Inspection Template", name):
		frappe.throw(
			_("{0} already exists.").format(frappe.utils.get_link_to_form("Quality Inspection Template", name)),
			title=_("Template exists"),
		)
	doc = frappe.get_doc({
		"doctype": "Quality Inspection Template",
		"quality_inspection_template_name": name,
		"custom_item": item,
		"custom_drawing_no": drawing_no,
		"custom_drawing_revision": revision,
		"custom_drawing_file": file,
	}).insert()
	return doc.name


@frappe.whitelist()
def plan_summary(template: str) -> dict:
	"""The template as the BOM / Item "Inspection Plan" shows it: every row
	with its tolerance, drawing or not."""
	from iso_compliance.qi.certificates import _limit_text

	doc = frappe.get_doc("Quality Inspection Template", template)
	doc.check_permission("read")
	stage_labels = {"custom_stage_incoming": "Incoming", "custom_stage_in_process": "In process",
	                "custom_stage_final": "Final", "custom_stage_fai": "FAI", "custom_stage_type_test": "Type test"}
	rows = []
	for r in doc.get(ROWS):
		if r.custom_row_type:
			limits = _limit_text(r) if r.custom_tolerance_type != "Reference / basic" else _("reference")
		elif cint(r.numeric):
			limits = f"{flt(r.min_value):g} – {flt(r.max_value):g}" if (flt(r.min_value) or flt(r.max_value)) else "—"
		else:
			limits = r.value or (r.acceptance_formula if r.formula_based_criteria else "") or ""
		rows.append({
			"balloon": r.custom_balloon_no or "",
			"type": r.custom_row_type or "",
			"specification": r.specification,
			"spec_text": r.custom_spec_text or "",
			"limits": limits,
			"unit": r.custom_unit or "",
			"class": r.custom_class or "",
			"stages": ", ".join(label for f, label in stage_labels.items() if cint(r.get(f))),
		})
	return {
		"name": doc.name,
		"drawing": is_drawing_template(doc),
		"drawing_no": doc.custom_drawing_no,
		"revision": doc.custom_drawing_revision,
		"locked": cint(doc.custom_locked),
		"superseded_by": doc.custom_superseded_by,
		"rows": rows,
	}
