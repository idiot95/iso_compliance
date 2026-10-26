# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Server side of the inspector screen (page `inspect`, SPEC §4.5).

Each value the inspector enters is one upsert into QI Measurement; the
inspection itself is saved only when the inspector finishes. Two tablets can
work the same lot: the unique key (inspection, balloon, sample) makes the last
write per sample win, never a conflict on the whole inspection.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from iso_compliance.qi import tolerance as T
from iso_compliance.qi.api import require_quality_manager
from iso_compliance.qi.inspection import QI, calibration, default_sample, drawing_rows, row_summary
from iso_compliance.qi.template import ROWS, instrument_list, is_drawing_template, measuring_instruments


def _load(qi: str, ptype="read"):
	doc = frappe.get_doc(QI, qi)
	doc.check_permission(ptype)
	return doc


def _instruments(src, row, cache, stage=None):
	"""The instruments the template allows for this row at this stage; failing
	that, those of its Test Method's instrument items; failing that, every
	measuring instrument."""
	names = instrument_list(src.custom_instruments, stage) if src else []
	if not names and row.custom_test_method:
		items = frappe.get_all("Test Method Instrument", filters={"parent": row.custom_test_method}, pluck="instrument_item")
		names = [a.name for a in cache["all"] if a.item_code in items]
	pool = {a.name: a for a in cache["all"]}
	chosen = [pool[n] for n in names if n in pool] or cache["all"]
	out = []
	for a in chosen:
		if a.name not in cache["cal"]:
			cache["cal"][a.name] = calibration(a.name)
		out.append({**a, **cache["cal"][a.name]})
	return out


@frappe.whitelist()
def get_inspection(qi: str) -> dict:
	doc = _load(qi)
	tpl = frappe.get_doc("Quality Inspection Template", doc.quality_inspection_template)
	tpl_rows = {r.custom_balloon_no: r for r in tpl.get(ROWS) if r.custom_row_type}
	data = {}
	for m in frappe.get_all(
		"QI Measurement",
		filters={"quality_inspection": qi},
		fields=["row_key", "sample_no", "value", "instrument", "entered_by", "modified"],
		order_by="sample_no asc",
	):
		data.setdefault(m.row_key, []).append(m)

	one_off = bool(cint(tpl.custom_one_off))
	can_write = doc.docstatus == 0 and frappe.has_permission(QI, "write", doc)
	can_add = one_off and can_write and not cint(tpl.custom_locked)
	cache, rows = {"all": measuring_instruments(), "cal": {}}, []
	for r in drawing_rows(doc):
		src = tpl_rows.get(r.custom_balloon_no)
		instruments = _instruments(src, r, cache, doc.custom_stage) if r.custom_row_type != "Visual" else []
		rows.append({
			"name": r.name,
			"balloon": r.custom_balloon_no,
			"row_type": r.custom_row_type,
			"specification": r.specification,
			"spec_text": r.custom_spec_text,
			"class": r.custom_class,
			"unit": r.custom_unit,
			"tolerance_type": r.custom_tolerance_type,
			"min": r.min_value,
			"max": r.max_value,
			"min_display": T.display_limit(r.min_value) if r.custom_row_type != "Visual" else "",
			"max_display": T.display_limit(r.max_value) if r.custom_row_type != "Visual" else "",
			"test_method": r.custom_test_method,
			# the row's work instruction, else its Test Method's
			"procedure": (src and src.get("custom_work_instruction"))
			or (r.custom_test_method and frappe.db.get_value("Test Method", r.custom_test_method, "procedure")),
			"required": cint(r.custom_sample_count),
			"position": src.custom_position if src else None,
			"instruments": instruments,
			"values": data.get(r.custom_balloon_no, []),
			"status": r.status,
			"removable": can_add and not data.get(r.custom_balloon_no),
		})
	return {
		"name": doc.name,
		"docstatus": doc.docstatus,
		"item_code": doc.item_code,
		"item_name": doc.item_name,
		"stage": doc.custom_stage,
		"check_point": doc.get("custom_check_point"),
		"supplier_cert": doc.get("custom_supplier_cert"),
		"lot_qty": doc.custom_lot_qty,
		"sample_size": doc.sample_size,
		"default_sample": default_sample(doc.custom_lot_qty) if doc.custom_lot_qty else None,
		"reference_type": doc.reference_type,
		"reference_name": doc.reference_name,
		"work_order": doc.custom_work_order,
		"customer": doc.custom_customer,
		"template": doc.quality_inspection_template,
		"superseded_by": tpl.custom_superseded_by,
		"drawing": doc.custom_drawing,
		"drawing_no": doc.custom_drawing_no,
		"drawing_revision": doc.custom_drawing_revision,
		"disposition": doc.custom_disposition,
		"concession_no": doc.custom_concession_no,
		"non_conformance": doc.custom_non_conformance,
		"status": doc.status,
		"conditions": [c.as_dict() for c in doc.custom_conditions],
		"work_instructions": [w.as_dict() for w in doc.custom_work_instructions],
		"rows": rows,
		"can_write": can_write,
		"can_submit": doc.docstatus == 0 and frappe.has_permission(QI, "submit", doc),
		# no plan existed: characteristics are added here, then saved as a plan
		"one_off": one_off,
		"can_add": can_add,
		"can_save_plan": one_off and bool({"Quality Manager", "System Manager"} & set(frappe.get_roles())),
		"plan_groups": _item_groups(doc.item_code) if one_off else [],
	}


@frappe.whitelist(methods=["POST"])
def save_measurement(qi: str, row_key: str, sample_no: int, value: str | None = None, instrument: str | None = None) -> dict:
	"""Upsert one value. Empty value deletes it. Returns the row's summary."""
	if frappe.db.get_value(QI, qi, "docstatus") != 0:
		frappe.throw(_("This inspection is already submitted."))
	if not frappe.has_permission(QI, "write", qi):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	sample_no = cint(sample_no)
	reading = frappe.db.get_value(
		"Quality Inspection Reading",
		{"parent": qi, "parenttype": QI, "custom_balloon_no": row_key},
		["name", "custom_row_type", "custom_tolerance_type", "custom_test_method", "min_value", "max_value", "custom_sample_count"],
		as_dict=True,
	)
	if not reading:
		frappe.throw(_("No. {0} is not on this inspection").format(row_key))
	if sample_no < 1:
		frappe.throw(_("Sample number must be 1 or more"))
	value = (value or "").strip()
	if value:
		if reading.custom_row_type == "Visual":
			value = value.upper()
			if value not in ("OK", "NG"):
				frappe.throw(_("Enter OK or NG"))
		else:
			try:
				if reading.custom_tolerance_type == T.ANGLE:
					value = str(T.parse_angle(value))
				else:
					value = str(float(value.replace(",", ".")))
			except (ValueError, T.ToleranceError):
				frappe.throw(_("'{0}' is not a number").format(value))

	key = {"quality_inspection": qi, "row_key": row_key, "sample_no": sample_no}
	existing = frappe.db.get_value("QI Measurement", key)
	if not value:
		if existing:
			frappe.db.delete("QI Measurement", {"name": existing})
	elif existing:
		frappe.db.set_value("QI Measurement", existing, {
			"value": value, "instrument": instrument, "entered_by": frappe.session.user, "entered_at": now_datetime(),
		})
	else:
		try:
			frappe.get_doc({"doctype": "QI Measurement", **key, "value": value, "instrument": instrument,
			                "entered_by": frappe.session.user, "entered_at": now_datetime()}).insert(ignore_permissions=True)
		except frappe.UniqueValidationError:
			# the other tablet got there first: last write wins
			frappe.db.set_value("QI Measurement", frappe.db.get_value("QI Measurement", key), "value", value)

	values = frappe.get_all("QI Measurement", filters={"quality_inspection": qi, "row_key": row_key}, pluck="value")
	s = row_summary(frappe._dict(reading), [v for v in values if v not in (None, "")])
	return {"value": value, "n": s["n"], "out": s["out"], "status": s["status"],
	        "min": s.get("min"), "max": s.get("max"), "mean": s.get("mean")}


@frappe.whitelist(methods=["POST"])
def save_condition(qi: str, row: str, actual=None):
	if frappe.db.get_value(QI, qi, "docstatus") != 0 or not frappe.has_permission(QI, "write", qi):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if frappe.db.get_value("QI Condition", row, "parent") != qi:
		frappe.throw(_("Condition row not on this inspection"))
	frappe.db.set_value("QI Condition", row, "actual", None if actual in (None, "") else flt(actual))


def _draft_for_writing(qi: str):
	if frappe.db.get_value(QI, qi, "docstatus") != 0:
		frappe.throw(_("This inspection is already submitted."))
	if not frappe.has_permission(QI, "write", qi):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def set_sample_size(qi: str, sample_size: int):
	"""The inspector picks the sample. Rows on the lot sample follow it; rows
	with a fixed number of pieces, and values read off a 3.1, keep theirs."""
	from iso_compliance.qi.inspection import required_samples

	_draft_for_writing(qi)
	n = cint(sample_size)
	lot = flt(frappe.db.get_value(QI, qi, "custom_lot_qty"))
	if n < 1:
		frappe.throw(_("The sample must be at least 1 piece."))
	if lot and n > lot:
		frappe.throw(_("The sample can't be larger than the lot ({0}).").format(frappe.format(lot)))
	template = frappe.db.get_value(QI, qi, "quality_inspection_template")
	plan = {r.custom_balloon_no: r for r in frappe.get_doc("Quality Inspection Template", template).get(ROWS) if r.custom_row_type}
	frappe.db.set_value(QI, qi, "sample_size", n)
	for r in frappe.get_all("Quality Inspection Reading", filters={"parent": qi, "parenttype": QI},
	                        fields=["name", "custom_balloon_no", "custom_row_type"]):
		src = plan.get(r.custom_balloon_no)
		if src:
			frappe.db.set_value("Quality Inspection Reading", r.name, "custom_sample_count", required_samples(src, n))


@frappe.whitelist(methods=["POST"])
def add_sample(qi: str, row_key: str) -> int:
	"""One more reading on one characteristic, beyond what the plan asks."""
	_draft_for_writing(qi)
	name, count = frappe.db.get_value("Quality Inspection Reading", {"parent": qi, "parenttype": QI, "custom_balloon_no": row_key},
	                                  ["name", "custom_sample_count"]) or (None, 0)
	if not name:
		frappe.throw(_("No. {0} is not on this inspection").format(row_key))
	frappe.db.set_value("Quality Inspection Reading", name, "custom_sample_count", cint(count) + 1)
	return cint(count) + 1


@frappe.whitelist(methods=["POST"])
def remove_sample(qi: str, row_key: str) -> int:
	"""One reading fewer on one characteristic: the last slot, once it is empty."""
	_draft_for_writing(qi)
	name, count = frappe.db.get_value("Quality Inspection Reading", {"parent": qi, "parenttype": QI, "custom_balloon_no": row_key},
	                                  ["name", "custom_sample_count"]) or (None, 0)
	if not name:
		frappe.throw(_("No. {0} is not on this inspection").format(row_key))
	count = cint(count)
	if count <= 1:
		frappe.throw(_("At least one reading is needed."))
	if frappe.db.exists("QI Measurement", {"quality_inspection": qi, "row_key": row_key, "sample_no": count}):
		frappe.throw(_("Clear reading {0} of No. {1} first.").format(count, row_key))
	frappe.db.set_value("Quality Inspection Reading", name, "custom_sample_count", count - 1)
	return count - 1


@frappe.whitelist(methods=["POST"])
def finish(qi: str, disposition: str | None = None, concession_no: str | None = None,
           non_conformance: str | None = None, submit=0) -> dict:
	"""Save the inspection (summarising every measurement), then submit if asked."""
	doc = _load(qi, "write")
	doc.custom_disposition = disposition or None
	doc.custom_concession_no = concession_no or None
	doc.custom_non_conformance = non_conformance or None
	doc.save()
	if cint(submit):
		doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus, "status": doc.status}


@frappe.whitelist()
def summary(qi: str) -> dict:
	"""Recompute without saving: what Finish would show."""
	doc = _load(qi)
	doc.run_method("before_validate")
	return {
		"status": "Rejected" if any(r.status == "Rejected" for r in drawing_rows(doc)) else "Accepted",
		"rows": [
			{"balloon": r.custom_balloon_no, "specification": r.specification, "class": r.custom_class,
			 "n": r.custom_n, "required": r.custom_sample_count, "out": r.custom_out_of_spec, "status": r.status,
			 "obs_min": r.custom_obs_min, "obs_max": r.custom_obs_max}
			for r in drawing_rows(doc)
		],
	}


# ------------------------------------------------- one-off plan (no plan) --
# An item with no plan is inspected on a one-off plan (inspection.one_off_plan):
# the inspector adds each characteristic here, no drawing needed, and Quality
# saves the result as the plan of the item or its item group.

#: what the add-characteristic dialog may set on a plan row
CHARACTERISTIC_FIELDS = {
	"row_type": "custom_row_type", "spec_text": "custom_spec_text", "class": "custom_class", "unit": "custom_unit",
	"tolerance_type": "custom_tolerance_type", "nominal": "custom_nominal", "tol": "custom_tol",
	"upper_dev": "custom_upper_dev", "lower_dev": "custom_lower_dev", "fit_class": "custom_fit_class",
	"min": "min_value", "max": "max_value", "test_method": "custom_test_method",
}


def _one_off(doc):
	"""The inspection's one-off plan, still open to new characteristics."""
	tpl = frappe.get_doc("Quality Inspection Template", doc.quality_inspection_template)
	if not cint(tpl.custom_one_off):
		frappe.throw(_("This inspection follows the plan {0}. Change its characteristics there.").format(tpl.name))
	if cint(tpl.custom_locked):
		frappe.throw(_("The plan {0} is locked by a submitted inspection.").format(tpl.name))
	return tpl


def _item_groups(item_code: str) -> list[str]:
	"""The item's group and those above it: where a plan saved for a group
	still reaches this item (inspection.resolve_template climbs the tree)."""
	group = frappe.db.get_value("Item", item_code, "item_group")
	if not group:
		return []
	lft, rgt = frappe.db.get_value("Item Group", group, ["lft", "rgt"])
	return frappe.get_all("Item Group", filters={"lft": ("<=", lft), "rgt": (">=", rgt)}, pluck="name", order_by="lft desc")


@frappe.whitelist(methods=["POST"])
def add_characteristic(qi: str, characteristic) -> str:
	"""One characteristic onto the one-off plan and this inspection, checked at
	this inspection's stage. The plan's own validation computes its limits."""
	from iso_compliance.qi.inspection import STAGE_FIELD, add_conditions, required_samples, ROW_COPY

	_draft_for_writing(qi)
	doc = _load(qi, "write")
	tpl = _one_off(doc)
	c = frappe.parse_json(characteristic) or {}
	name = (c.get("specification") or "").strip()
	if not name:
		frappe.throw(_("Name the characteristic."))
	if c.get("row_type") not in ("Dimension", "Visual", "Test", "Material"):
		frappe.throw(_("Choose what kind of characteristic it is."))
	if c.get("tolerance_type") == T.REFERENCE:
		frappe.throw(_("A reference dimension is not inspected."))
	if not frappe.db.exists("Quality Inspection Parameter", name):
		frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": name}).insert(ignore_permissions=True)
	row = tpl.append(ROWS, {
		"specification": name,
		**{field: c.get(key) for key, field in CHARACTERISTIC_FIELDS.items() if c.get(key) not in (None, "")},
		STAGE_FIELD.get(doc.custom_stage, "custom_stage_final"): 1,
		"custom_frequency": "Every lot", "custom_sampling": "Lot sample", "custom_in_process_at": "Every check",
	})
	tpl.flags.ignore_permissions = True
	tpl.save()

	reading = doc.append("readings", {})
	for src, dst in ROW_COPY.items():
		reading.set(dst, row.get(src))
	reading.formula_based_criteria = 0
	reading.manual_inspection = 1
	reading.status = "Accepted"
	reading.custom_sample_count = required_samples(row, doc.sample_size)
	add_conditions(doc, [row])
	doc.save()
	return row.custom_balloon_no


@frappe.whitelist(methods=["POST"])
def remove_characteristic(qi: str, row_key: str):
	"""Take back a characteristic added by mistake, before anything is measured on it."""
	_draft_for_writing(qi)
	doc = _load(qi, "write")
	tpl = _one_off(doc)
	if frappe.db.exists("QI Measurement", {"quality_inspection": qi, "row_key": row_key}):
		frappe.throw(_("No. {0} has readings. Clear them first.").format(row_key))
	for r in [r for r in tpl.get(ROWS) if r.custom_balloon_no == row_key]:
		tpl.remove(r)
	for r in [r for r in doc.readings if r.custom_balloon_no == row_key]:
		doc.remove(r)
	for c in [c for c in doc.custom_conditions if c.row_key == row_key]:
		doc.remove(c)
	tpl.flags.ignore_permissions = True
	tpl.save()
	doc.save()


@frappe.whitelist(methods=["POST"])
def save_as_plan(qi: str, target: str, item_group: str | None = None) -> str:
	"""Keep the one-off plan as the inspection plan of the item, or of an item
	group the item sits in, so later inspections load it. Draft or submitted."""
	require_quality_manager()
	doc = _load(qi)
	tpl = frappe.get_doc("Quality Inspection Template", doc.quality_inspection_template)
	if not cint(tpl.custom_one_off):
		frappe.throw(_("{0} is already a saved plan.").format(tpl.name))
	if not any(r.custom_row_type for r in tpl.get(ROWS)):
		frappe.throw(_("Add at least one characteristic first."))
	if target == "Item":
		holder, field, name = "Item", "quality_inspection_template", doc.item_code
	elif target == "Item Group":
		if item_group not in _item_groups(doc.item_code):
			frappe.throw(_("Choose {0}'s item group or one above it.").format(doc.item_code))
		holder, field, name = "Item Group", "custom_default_qi_template", item_group
	else:
		frappe.throw(_("Save the plan against the Item or an Item Group."))
	current = frappe.db.get_value(holder, name, field)
	if current and current != tpl.name and is_drawing_template(current):
		frappe.throw(_("{0} {1} already has the plan {2}.").format(_(holder), name, current), title=_("Plan exists"))
	frappe.db.set_value(holder, name, field, tpl.name)
	frappe.db.set_value("Quality Inspection Template", tpl.name, "custom_one_off", 0)
	frappe.get_doc(holder, name).add_comment(
		"Info", _("Inspection plan: {0} → {1} (built in {2})").format(current or _("none"), tpl.name, doc.name))
	return name
