# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Drawing-based Quality Inspections (SPEC §4.3–4.5).

Every hook starts with `applies()`: a draft inspection on a drawing template.
An item with no new-format plan is inspected on a one-off plan whose
characteristics the inspection adds (`one_off_plan`).
Old-format (legacy) templates are retired (2026-10-28): no new inspection loads
one (`use_new_plan`). The ~1,300 inspections already made on them, and drafts
begun before then, pass through untouched.

Measured values live in QI Measurement (one row per inspection × balloon ×
sample). The inspection's readings are a summary of them, rebuilt on every
save, and each drawing row is judged here rather than by ERPNext
(`reading.manual_inspection = 1`), because ERPNext's judge knows ten readings
and min/max only.
"""

import math
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate, now_datetime, nowdate

from iso_compliance.qi import tolerance as T
from iso_compliance.qi.template import ROWS, is_drawing_template

QI = "Quality Inspection"
STAGE_FIELD = {
	"Incoming": "custom_stage_incoming",
	"In Process": "custom_stage_in_process",
	"Final": "custom_stage_final",
	"FAI": "custom_stage_fai",
	"Type Test": "custom_stage_type_test",
}
STAGE_TYPE = {"Incoming": "Incoming", "In Process": "In Process", "Final": "Outgoing", "FAI": "Outgoing"}
TYPE_STAGE = {"Incoming": "Incoming", "In Process": "In Process", "Outgoing": "Final"}

#: template row field -> reading field
ROW_COPY = {
	"specification": "specification",
	"value": "value",
	"numeric": "numeric",
	"min_value": "min_value",
	"max_value": "max_value",
	"parameter_group": "parameter_group",
	"custom_row_type": "custom_row_type",
	"custom_balloon_no": "custom_balloon_no",
	"custom_class": "custom_class",
	"custom_spec_text": "custom_spec_text",
	"custom_tolerance_type": "custom_tolerance_type",
	"custom_unit": "custom_unit",
	"custom_test_method": "custom_test_method",
}
LIMIT_FIELDS = ("specification", "value", "numeric", "min_value", "max_value")


# ------------------------------------------------------------------ guard --


def applies(doc) -> bool:
	return doc.docstatus == 0 and is_drawing_template(doc.quality_inspection_template)


def _tagged_templates(item_code: str, bom_no: str | None = None) -> list[str]:
	"""Every plan tagged for an item, in the order an inspection looks: the
	BOM's, then the Item's, then its Item Group's default (up the tree)."""
	found = []
	if bom_no:
		found.append(frappe.db.get_value("BOM", bom_no, "quality_inspection_template"))
	if item_code:
		found.append(frappe.db.get_value("Item", item_code, "quality_inspection_template"))
		group = frappe.db.get_value("Item", item_code, "item_group")
		if group:
			lft, rgt = frappe.db.get_value("Item Group", group, ["lft", "rgt"])
			found += frappe.get_all(
				"Item Group",
				filters={"lft": ("<=", lft), "rgt": (">=", rgt), "custom_default_qi_template": ("is", "set")},
				pluck="custom_default_qi_template",
				order_by="lft desc",
			)
	return [t for t in found if t]


def resolve_template(item_code: str, bom_no: str | None = None, explicit: str | None = None) -> str | None:
	"""The new-format plan for an item: the first tagged one (BOM, Item, Item
	Group up the tree), else a new-format plan made for the item but not tagged.
	Old-format templates are retired and never returned: an item with only one
	of those has no plan (None), and is inspected on a one-off plan. An explicit
	plan wins if it is new-format."""
	if explicit and is_drawing_template(explicit):
		return explicit
	new = next((t for t in _tagged_templates(item_code, bom_no) if is_drawing_template(t)), None)
	if not new and item_code:
		# a new-format plan made for this item but not tagged on it yet: the
		# latest revision that is not superseded
		# (a one-off plan nobody saved stays with its own inspection)
		for t in frappe.get_all(
			"Quality Inspection Template",
			filters={"custom_item": item_code, "custom_superseded_by": ("is", "not set"), "custom_one_off": 0},
			pluck="name",
			order_by="modified desc",
		):
			if is_drawing_template(t):
				new = t
				break
	return new


def legacy_template(item_code: str, bom_no: str | None = None) -> str | None:
	"""The retired old-format template the item used to load, if any: its
	parameter names are offered when characteristics are added."""
	return next((t for t in _tagged_templates(item_code, bom_no) if not is_drawing_template(t)), None)


def one_off_plan(item_code: str) -> str:
	"""A blank plan for an item with no new-format plan. The inspection adds its
	characteristics, no drawing needed (inspector.add_characteristic), and
	Quality can then save it against the item or its group
	(inspector.save_as_plan). Unsaved, it serves that one inspection only."""
	base = _("{0} (no drawing)").format(item_code)
	name, n = base, 1
	while frappe.db.exists("Quality Inspection Template", name):
		n += 1
		name = f"{base} {n}"
	return frappe.get_doc({
		"doctype": "Quality Inspection Template",
		"quality_inspection_template_name": name,
		"custom_item": item_code,
		"custom_drawing_source": "None",
		"custom_one_off": 1,
	}).insert(ignore_permissions=True).name


def plan_or_one_off(item_code: str, bom_no: str | None = None, explicit: str | None = None) -> str:
	"""The item's new-format plan, else a one-off plan to build in the inspection."""
	return resolve_template(item_code, bom_no, explicit) or one_off_plan(item_code)


def use_new_plan(doc):
	"""Old-format templates are retired: a new inspection that arrived with one,
	or with none (ERPNext's own buttons fill the Item's), takes the item's
	new-format plan, else a one-off plan, and its readings are rebuilt from it."""
	if not doc.is_new() or doc.docstatus != 0 or not doc.item_code:
		return
	if doc.quality_inspection_template and is_drawing_template(doc.quality_inspection_template):
		return
	doc.quality_inspection_template = plan_or_one_off(doc.item_code, doc.get("bom_no"))
	doc.set("readings", [])


# ------------------------------------------------------------------ hooks --


def before_validate(doc, method=None):
	use_new_plan(doc)
	if not applies(doc):
		return
	if not doc.custom_stage:
		doc.custom_stage = TYPE_STAGE.get(doc.inspection_type, "Final")
	if not doc.get("readings"):
		build_readings(doc)
	summarise(doc)
	judge(doc)
	apply_disposition(doc)


def validate(doc, method=None):
	if not applies(doc):
		return
	if doc.inspection_type == "In Process" and doc.reference_type == "Job Card":
		# ERPNext overwrote limits from the *Item's* template, matched by
		# parameter name (SPEC §2). Put the drawing template's back, by balloon.
		# It also reset every row to Accepted, so judge again.
		restore_limits(doc)
		summarise(doc)
		judge(doc)
		apply_disposition(doc)
	if not cint(doc.manual_inspection):
		doc.status = "Rejected" if any(r.status == "Rejected" for r in doc.readings) else "Accepted"
	if doc.custom_disposition == "Accepted" and any(r.status == "Rejected" for r in doc.readings):
		frappe.throw(
			_("Some readings are out of spec: choose Accept under Concession, Rework or Rejected."),
			title=_("Disposition"),
		)
	warn_conditions(doc)
	check_calibration(doc)


def before_submit(doc, method=None):
	if not is_drawing_template(doc.quality_inspection_template):
		return
	if not drawing_rows(doc):
		frappe.throw(_("Add at least one characteristic before submitting."), title=_("Nothing inspected"))
	if not doc.custom_disposition:
		doc.custom_disposition = "Accepted" if doc.status == "Accepted" else "Rejected"
		apply_disposition(doc)
	short_ctq, short_other = [], []
	for r in drawing_rows(doc):
		need = cint(r.custom_sample_count)
		if need and cint(r.custom_n) < need:
			(short_ctq if r.custom_class == "CTQ" else short_other).append(
				f"{r.custom_balloon_no} {r.specification} ({cint(r.custom_n)}/{need})"
			)
	if doc.custom_stage == "In Process":
		# a check records what that Job Card did; the other rows may stay unmeasured,
		# CTQ included (developer, 2026-10-24)
		short = short_ctq + short_other
		if short:
			frappe.msgprint(_("Not measured at this check:") + "<br>" + "<br>".join(short),
			                indicator="blue", title=_("In-process check"))
		short_ctq, short_other = [], []
	if short_ctq:
		frappe.throw(
			_("Every sample must be measured on CTQ rows before submitting:") + "<br>" + "<br>".join(short_ctq),
			title=_("Measurements missing"),
		)
	if short_other:
		frappe.msgprint(
			_("Submitted with fewer samples than planned on:") + "<br>" + "<br>".join(short_other),
			indicator="orange",
			title=_("Short sample"),
		)
	if doc.custom_stage == "Incoming" and not doc.get("custom_supplier_cert"):
		from iso_compliance.qi.certificates import _issue_mtc

		if _issue_mtc(doc.item_code):
			# warn, never block (developer, 2026-10-13)
			frappe.msgprint(
				_("{0}'s item group issues a 3.1 MTC at dispatch, and this receipt has no supplier certificate. "
				  "Accepting anyway; attach it to the Purchase Receipt when it arrives.").format(doc.item_code),
				indicator="orange", title=_("Supplier certificate missing"),
			)
	if doc.custom_disposition == "Accept under Concession":
		failed = [f"{r.custom_balloon_no} {r.specification}" for r in drawing_rows(doc) if r.status == "Rejected"]
		msg = _("Accepted under concession with these rows out of spec:") + "<br>" + "<br>".join(failed or [_("none")])
		if not (doc.custom_concession_no or doc.custom_non_conformance):
			msg += "<br><br>" + _("No concession number or Non Conformance is recorded.")
		frappe.msgprint(msg, indicator="orange", title=_("Concession"))


def on_submit(doc, method=None):
	if not is_drawing_template(doc.quality_inspection_template):
		return
	frappe.db.set_value("Quality Inspection Template", doc.quality_inspection_template, "custom_locked", 1)
	if doc.custom_created_entry and frappe.db.get_value("Stock Entry", doc.custom_created_entry, "docstatus") == 0:
		se = frappe.get_doc("Stock Entry", doc.custom_created_entry)
		se.set_missing_values()
		se.calculate_rate_and_amount()
		se.save(ignore_permissions=True)
		frappe.msgprint(
			_("Inspection submitted. Stock Entry {0} is ready for Stores to submit.").format(
				frappe.utils.get_link_to_form("Stock Entry", se.name)
			),
			indicator="green",
		)


def on_cancel(doc, method=None):
	_drop_created_entry(doc)


def on_trash(doc, method=None):
	_drop_created_entry(doc)
	if doc.name and not doc.is_new():
		frappe.db.delete("QI Measurement", {"quality_inspection": doc.name})


def _drop_created_entry(doc):
	name = doc.get("custom_created_entry")
	if name and frappe.db.get_value("Stock Entry", name, "docstatus") == 0:
		frappe.db.set_value(QI, doc.name, "custom_created_entry", None, update_modified=False)
		frappe.delete_doc("Stock Entry", name, ignore_permissions=True, force=True)


# --------------------------------------------------------------- readings --


def drawing_rows(doc):
	return [r for r in doc.get("readings") or [] if r.get("custom_row_type")]


def template_rows(template: str) -> list:
	return frappe.get_doc("Quality Inspection Template", template).get(ROWS)


def required_samples(row, sample_size) -> int:
	if row.custom_row_type == "Material":
		return 1  # one value, read off the supplier's certificate
	if row.custom_sampling == "Fixed number":
		return cint(row.custom_fixed_count)
	return max(1, cint(math.ceil(flt(sample_size))))


def build_readings(doc):
	stage_field = STAGE_FIELD.get(doc.custom_stage)
	tpl = frappe.get_doc("Quality Inspection Template", doc.quality_inspection_template)
	due = [
		r
		for r in tpl.get(ROWS)
		if r.custom_row_type
		and stage_field
		and cint(r.get(stage_field))
		and r.custom_tolerance_type != T.REFERENCE
		and at_check_point(r, doc)
		and is_due(r, doc)
	]
	if not due:
		# a one-off plan starts empty; a plan with nothing due at this stage is
		# added to in the inspection (inspector.add_characteristic copies it)
		_snapshot(doc, tpl, [])
		return
	for r in due:
		reading = doc.append("readings", {})
		for src, dst in ROW_COPY.items():
			reading.set(dst, r.get(src))
		reading.formula_based_criteria = 0
		reading.manual_inspection = 1
		reading.status = "Accepted"
		reading.custom_sample_count = required_samples(r, doc.sample_size)
	_snapshot(doc, tpl, due)


def _snapshot(doc, tpl, rows):
	doc.custom_drawing_no = tpl.custom_drawing_no
	doc.custom_drawing_revision = tpl.custom_drawing_revision
	doc.custom_drawing = tpl.custom_drawing
	doc.set("custom_work_instructions", [])
	settings = frappe.get_cached_doc("Inspection Settings")
	wis = [("Stage", w.controlled_document) for w in settings.stage_wi if w.stage == doc.custom_stage]
	if tpl.custom_product_wi:
		wis.append(("Product", tpl.custom_product_wi))
	for method in {r.custom_test_method for r in rows if r.custom_test_method}:
		proc = frappe.db.get_value("Test Method", method, "procedure")
		if proc:
			wis.append(("Test", proc))
	seen = set()
	for level, wi in wis:
		if wi in seen or not frappe.db.exists("Controlled Document", wi):
			continue
		seen.add(wi)
		doc.append("custom_work_instructions", {
			"level": level,
			"controlled_document": wi,
			"revision": frappe.db.get_value("Controlled Document", wi, "revision_number"),
		})
	doc.set("custom_conditions", [])
	add_conditions(doc, rows)


def add_conditions(doc, rows):
	"""The set conditions of the Test rows' methods, for the inspector to confirm."""
	for r in rows:
		if r.custom_row_type != "Test" or not r.custom_test_method:
			continue
		overrides = {}
		if r.custom_conditions:
			try:
				overrides = frappe.parse_json(r.custom_conditions) or {}
			except Exception:
				overrides = {}
		for c in frappe.get_doc("Test Method", r.custom_test_method).conditions:
			doc.append("custom_conditions", {
				"row_key": r.custom_balloon_no,
				"condition": c.condition,
				"set_value": flt(overrides.get(c.condition, c.set_value)),
				"tolerance": c.tolerance,
				"unit": c.unit,
			})


def at_check_point(row, doc) -> bool:
	"""In-process rows can be limited to the First Check (and Last Check)."""
	if doc.custom_stage != "In Process":
		return True
	at = row.get("custom_in_process_at") or "Every check"
	point = doc.get("custom_check_point") or "Random Check"
	if at == "First Check only":
		return point == "First Check"
	if at == "First and Last Check":
		return point in ("First Check", "Last Check")
	return True


def default_check_point(work_order) -> str:
	"""First Check until the Work Order has a submitted First Check, then Random Check."""
	if work_order and frappe.db.exists(QI, {"custom_work_order": work_order, "custom_stage": "In Process",
	                                         "custom_check_point": "First Check", "docstatus": 1}):
		return "Random Check"
	return "First Check"


def _history(doc, balloon):
	"""Submitted inspections of this item on this template and stage, newest
	first, each flagged with whether it measured this balloon."""
	rows = frappe.db.sql(
		"""
		select qi.name, qi.report_date,
			exists(select 1 from `tabQuality Inspection Reading` r
				where r.parent = qi.name and r.custom_balloon_no = %(balloon)s) as had
		from `tabQuality Inspection` qi
		where qi.docstatus = 1 and qi.item_code = %(item)s
			and qi.quality_inspection_template = %(template)s
			and ifnull(qi.custom_stage, '') = %(stage)s and qi.name != %(name)s
		order by qi.report_date desc, qi.creation desc
		""",
		{"balloon": balloon, "item": doc.item_code, "template": doc.quality_inspection_template,
		 "stage": doc.custom_stage or "", "name": doc.name or ""},
		as_dict=True,
	)
	return rows


def is_due(row, doc) -> bool:
	freq = row.custom_frequency or "Every lot"
	if freq == "Every lot":
		return True
	history = _history(doc, row.custom_balloon_no)
	measured = [h for h in history if h.had]
	if freq == "First article only":
		return not measured
	if not measured:
		return True
	n = max(1, cint(row.custom_frequency_n))
	if freq == "Every N lots":
		lots_since = next(i for i, h in enumerate(history) if h.had)
		return lots_since + 1 >= n
	if freq == "Every N months":
		return getdate(add_months(measured[0].report_date, n)) <= getdate(doc.report_date or nowdate())
	return True


def restore_limits(doc):
	by_balloon = {r.custom_balloon_no: r for r in template_rows(doc.quality_inspection_template) if r.custom_row_type}
	for reading in drawing_rows(doc):
		src = by_balloon.get(reading.custom_balloon_no)
		if src:
			for f in LIMIT_FIELDS:
				reading.set(f, src.get(f))


# ----------------------------------------------------------- measurements --


def measurements(qi_name) -> dict[str, list]:
	out = defaultdict(list)
	if not qi_name:
		return out
	for m in frappe.get_all(
		"QI Measurement",
		filters={"quality_inspection": qi_name},
		fields=["row_key", "sample_no", "value", "instrument", "entered_by", "entered_at"],
		order_by="sample_no asc",
	):
		if m.value not in (None, ""):
			out[m.row_key].append(m)
	return out


def _number(reading, value):
	if reading.custom_tolerance_type == T.ANGLE:
		return T.parse_angle(value)
	return flt(value)


def row_summary(reading, values) -> dict:
	"""n / min / max / mean / out-of-spec and the verdict for one row."""
	if reading.custom_row_type == "Visual":
		ng = sum(1 for v in values if str(v).strip().upper() == "NG")
		return {"n": len(values), "out": ng, "status": "Rejected" if ng else "Accepted",
		        "reading_value": ("NG" if ng else "OK") if values else ""}
	nums = []
	for v in values:
		try:
			nums.append(_number(reading, v))
		except (ValueError, T.ToleranceError):
			continue
	lo, hi = flt(reading.min_value), flt(reading.max_value)
	out = sum(1 for x in nums if x < lo - 1e-9 or x > hi + 1e-9)
	mean = sum(nums) / len(nums) if nums else None
	status = "Accepted"
	if nums:
		rule = reading.custom_test_method and frappe.db.get_value("Test Method", reading.custom_test_method, "result_rule")
		if rule == "Mean must pass":
			status = "Accepted" if lo - 1e-9 <= mean <= hi + 1e-9 else "Rejected"
		else:
			status = "Rejected" if out else "Accepted"
	return {"n": len(nums), "out": out, "status": status, "min": min(nums) if nums else None,
	        "max": max(nums) if nums else None, "mean": mean, "values": nums}


def summarise(doc):
	data = measurements(doc.name if not doc.is_new() else None)
	for r in drawing_rows(doc):
		rows = data.get(r.custom_balloon_no, [])
		s = row_summary(r, [m.value for m in rows])
		r.custom_n = s["n"]
		r.custom_out_of_spec = s["out"]
		r.status = s["status"]
		if r.custom_row_type == "Visual":
			r.reading_value = s["reading_value"]
		else:
			r.custom_obs_min = s["min"]
			r.custom_obs_max = s["max"]
			r.custom_mean = s["mean"]
			raw = [m.value for m in rows][:10]
			for i in range(1, 11):
				r.set(f"reading_{i}", raw[i - 1] if i <= len(raw) else None)
		instruments = [m.instrument for m in rows if m.instrument]
		if instruments:
			r.custom_instrument = instruments[-1]
			r.custom_cal_due = calibration(r.custom_instrument).get("due")


def judge(doc):
	"""Our verdict on drawing rows; ERPNext skips rows marked manual."""
	for r in drawing_rows(doc):
		r.manual_inspection = 1
		r.formula_based_criteria = 0


def apply_disposition(doc):
	d = doc.custom_disposition
	if d == "Accept under Concession":
		doc.manual_inspection = 1
		doc.status = "Accepted"
	elif d in ("Rework", "Rejected"):
		doc.manual_inspection = 1
		doc.status = "Rejected"
	else:
		doc.manual_inspection = 0


# --------------------------------------------------- conditions / instruments --


def warn_conditions(doc):
	off = []
	for c in doc.get("custom_conditions") or []:
		if c.actual in (None, "") or not flt(c.tolerance):
			continue
		if abs(flt(c.actual) - flt(c.set_value)) > flt(c.tolerance) + 1e-9:
			off.append(f"{c.row_key} {c.condition}: {c.actual} {c.unit or ''} ({c.set_value} ± {c.tolerance})")
	if off:
		frappe.msgprint(_("Test conditions outside tolerance:") + "<br>" + "<br>".join(off), indicator="orange")


def calibration(asset: str) -> dict:
	"""Latest Calibration task of the asset: {'due', 'last', 'state'}.
	state: ok / overdue / none."""
	if not asset:
		return {"state": "none"}
	tasks = frappe.db.sql(
		"""
		select t.next_due_date, t.last_completion_date
		from `tabAsset Maintenance Task` t join `tabAsset Maintenance` m on m.name = t.parent
		where m.asset_name = %s and t.maintenance_type = 'Calibration'
		order by t.next_due_date desc limit 1
		""",
		asset,
		as_dict=True,
	)
	if not tasks:
		return {"state": "none"}
	due = tasks[0].next_due_date
	return {"due": due, "last": tasks[0].last_completion_date,
	        "state": "overdue" if due and getdate(due) < getdate(nowdate()) else "ok"}


def check_calibration(doc):
	overdue = []
	for r in drawing_rows(doc):
		if r.custom_instrument and calibration(r.custom_instrument)["state"] == "overdue":
			overdue.append(f"{r.custom_balloon_no}: {r.custom_instrument}")
	if not overdue:
		return
	msg = _("Instrument calibration overdue:") + "<br>" + "<br>".join(overdue)
	if frappe.db.get_single_value("Inspection Settings", "calibration_overdue_policy") == "Block":
		frappe.throw(msg, title=_("Calibration"))
	frappe.msgprint(msg, indicator="orange", title=_("Calibration"))


# ------------------------------------------------------------ entry points --


def _check_can_inspect():
	if not frappe.has_permission(QI, "create"):
		frappe.throw(_("You are not allowed to record inspections."), frappe.PermissionError)


def default_sample(lot) -> int:
	pct = flt(frappe.db.get_single_value("Inspection Settings", "default_sample_percent")) or 5
	return int(min(max(1, math.ceil(flt(lot) * pct / 100)), max(1, flt(lot))))


@frappe.whitelist()
def final_inspection_info(work_order: str) -> dict:
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	existing = frappe.get_all(
		QI,
		filters={"custom_work_order": work_order, "docstatus": ("<", 2)},
		fields=["name", "docstatus", "status", "custom_lot_qty", "sample_size", "custom_disposition", "report_date"],
		order_by="creation desc",
	)
	open_qty = sum(flt(q.custom_lot_qty) for q in existing if q.docstatus == 0)
	lot = max(0, flt(wo.qty) - flt(wo.produced_qty) - open_qty)
	template = resolve_template(wo.production_item, wo.bom_no)
	return {
		"existing": existing,
		"lot_qty": lot,
		"sample_size": default_sample(lot) if lot else 0,
		"template": template,
		"drawing": is_drawing_template(template),
	}


@frappe.whitelist()
def start_final_inspection(work_order: str, lot_qty: float, sample_size: float) -> str:
	"""Draft Manufacture entry for the lot + the inspection that owns it."""
	_check_can_inspect()
	from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

	lot_qty, sample_size = flt(lot_qty), flt(sample_size)
	if lot_qty <= 0 or sample_size <= 0:
		frappe.throw(_("Lot quantity and sample size must be more than zero."))
	if sample_size > lot_qty:
		frappe.throw(_("The sample can't be larger than the lot."))
	wo = frappe.get_doc("Work Order", work_order)

	se = frappe.get_doc(make_stock_entry(work_order, "Manufacture", lot_qty))
	template = plan_or_one_off(wo.production_item, wo.bom_no)
	# Stock carries no value on this site (accounting is in Tally; every
	# valuation rate is zero), so the entry must allow zero rates or ERPNext
	# refuses it. A row that does have a rate still uses it.
	for row in se.items:
		row.allow_zero_valuation_rate = 1
	try:
		se.insert()
	except frappe.ValidationError as e:
		# ERPNext refuses the lot's finished-goods entry (operations not
		# complete, missing valuation, …). The inspection belongs to that
		# entry, so say why rather than half-starting.
		frappe.clear_messages()
		frappe.throw(
			_("The finished-goods entry for this lot can't be prepared yet, so the final inspection can't start:")
			+ "<br><br>" + str(e),
			title=_("Lot not ready"),
		)
	qi = frappe.get_doc({
		"doctype": QI,
		"inspection_type": "Outgoing",
		"reference_type": "Stock Entry",
		"reference_name": se.name,
		"item_code": wo.production_item,
		"bom_no": wo.bom_no,
		"sample_size": sample_size,
		"report_date": nowdate(),
		"inspected_by": frappe.session.user,
		"quality_inspection_template": template,
		"custom_stage": "Final",
		"custom_lot_qty": lot_qty,
		"custom_work_order": wo.name,
		"custom_customer": wo.sales_order and frappe.db.get_value("Sales Order", wo.sales_order, "customer"),
		"custom_created_entry": se.name,
	})
	qi.insert()
	return qi.name


@frappe.whitelist()
def start_receipt_inspection(purchase_receipt: str, row: str, sample_size: int | None = None) -> str:
	_check_can_inspect()
	pr = frappe.get_doc("Purchase Receipt", purchase_receipt)
	item = next((i for i in pr.items if i.name == row), None)
	if not item:
		frappe.throw(_("Row not found on {0}").format(purchase_receipt))
	row_filter = {"reference_type": "Purchase Receipt", "reference_name": pr.name,
	              "child_row_reference": item.name, "docstatus": ("<", 2)}
	existing = frappe.db.get_value(QI, {**row_filter, "custom_stage": "Incoming"})
	if existing:
		return existing
	legacy = frappe.db.get_value(QI, row_filter)
	if legacy:
		frappe.throw(
			_("Row {0} of this receipt was already inspected in {1}.").format(
				item.idx, frappe.utils.get_link_to_form(QI, legacy)),
			title=_("Already inspected"),
		)
	lot = flt(item.received_qty) or flt(item.qty)
	if sample_size is not None and not 1 <= cint(sample_size) <= max(1, lot):
		frappe.throw(_("The sample must be between 1 and the lot ({0}).").format(frappe.format(lot)))
	template = plan_or_one_off(item.item_code)
	qi = frappe.get_doc({
		"doctype": QI,
		"inspection_type": "Incoming",
		"reference_type": "Purchase Receipt",
		"reference_name": pr.name,
		"child_row_reference": item.name,
		"item_code": item.item_code,
		"batch_no": item.get("batch_no"),
		"sample_size": cint(sample_size) or default_sample(lot),
		"report_date": nowdate(),
		"inspected_by": frappe.session.user,
		"quality_inspection_template": template,
		"custom_stage": "Incoming",
		"custom_lot_qty": lot,
		# SOP-006: the supplier's MTC arrives on the receipt; Material rows are read off it
		"custom_supplier_cert": pr.get("custom_material_test_certificate"),
	})
	qi.insert()
	return qi.name


@frappe.whitelist()
def job_card_check_points(job_card: str) -> dict:
	jc = frappe.get_doc("Job Card", job_card)
	jc.check_permission("read")
	return {
		"default": default_check_point(jc.work_order),
		"existing": frappe.get_all(
			QI,
			filters={"reference_type": "Job Card", "reference_name": job_card, "docstatus": ("<", 2)},
			fields=["name", "custom_check_point", "docstatus", "status", "custom_disposition", "report_date"],
			order_by="creation asc",
		),
	}


@frappe.whitelist()
def start_job_card_inspection(job_card: str, check_point: str | None = None) -> str:
	"""An in-process inspection at a check point. A draft at the same check
	point is reopened; Random Checks can be repeated through the run."""
	_check_can_inspect()
	jc = frappe.get_doc("Job Card", job_card)
	check_point = check_point or default_check_point(jc.work_order)
	if check_point not in ("First Check", "Random Check", "Last Check"):
		frappe.throw(_("Unknown check point {0}").format(check_point))
	existing = frappe.db.get_value(QI, {"reference_type": "Job Card", "reference_name": jc.name,
	                                    "custom_check_point": check_point, "docstatus": 0})
	if existing:
		return existing
	template = plan_or_one_off(jc.production_item, jc.bom_no, explicit=jc.quality_inspection_template)
	lot = flt(jc.for_quantity)
	qi = frappe.get_doc({
		"doctype": QI,
		"inspection_type": "In Process",
		"reference_type": "Job Card",
		"reference_name": jc.name,
		"item_code": jc.production_item,
		"bom_no": jc.bom_no,
		"sample_size": 1 if check_point in ("First Check", "Last Check") else default_sample(lot),
		"report_date": nowdate(),
		"inspected_by": frappe.session.user,
		"quality_inspection_template": template,
		"custom_stage": "In Process",
		"custom_check_point": check_point,
		"custom_lot_qty": lot,
		"custom_work_order": jc.work_order,
	})
	qi.insert()
	return qi.name


@frappe.whitelist()
def drawing_template_for(item_code: str, bom_no: str | None = None, explicit: str | None = None) -> str | None:
	"""For the Inspect buttons: the drawing template that would load, if any."""
	t = resolve_template(item_code, bom_no, explicit)
	return t if is_drawing_template(t) else None


@frappe.whitelist()
def plan_preview(item_code: str, bom_no: str | None = None, stage: str | None = None, explicit: str | None = None) -> dict:
	"""For the new-inspection start dialog: the plan that would load, its
	drawing, and how many of its characteristics are checked at this stage."""
	frappe.has_permission("Item", "read", item_code, throw=True)
	template = resolve_template(item_code, bom_no, explicit)
	if not template:
		return {"template": None}
	tpl = frappe.get_doc("Quality Inspection Template", template)
	rows = [r for r in tpl.get(ROWS) if r.custom_row_type]
	field = STAGE_FIELD.get(stage)
	return {
		"template": template,
		"new_format": bool(rows),
		"drawing": tpl.custom_drawing,
		"drawing_no": tpl.custom_drawing_no,
		"revision": tpl.custom_drawing_revision,
		"superseded_by": tpl.custom_superseded_by,
		"rows": len(rows) or len(tpl.get(ROWS) or []),
		"due": sum(1 for r in rows if field and cint(r.get(field)) and r.custom_tolerance_type != T.REFERENCE),
		"positions": [r.custom_position for r in rows if r.custom_position and field and cint(r.get(field))],
	}
