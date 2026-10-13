# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Process capability per characteristic, from every sample measured on
submitted drawing inspections (QI SPEC v2, Phase G). Each inspection is a
lot; the chart shows the lot means against 3-sigma limits."""

from collections import defaultdict

import frappe
from frappe import _

from iso_compliance.qi import spc
from iso_compliance.qi import tolerance as T


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.item_code:
		return columns(), [], _("Choose an item."), None
	rows, lots_by_key, order = collect(filters)
	# balloon order: 1, 2, … 10, then T1…, M1…
	order.sort(key=lambda k: (k[0] or "", not (k[1] or "").isdigit(), int(k[1]) if (k[1] or "").isdigit() else 0, k[1] or ""))
	data = []
	for key in order:
		meta = rows[key]
		lots = lots_by_key[key]
		cap = spc.capability(lots, meta["min"], meta["max"], one_sided_max=meta["max_only"])
		recent = sum(1 for lot in lots[-spc.REDUCE_MIN_LOTS:] for x in lot
		             if (cap["lsl"] is not None and x < cap["lsl"]) or (cap["usl"] is not None and x > cap["usl"]))
		data.append({
			**meta,
			"lots": cap["lots"],
			"n": cap["n"],
			"mean": cap["mean"],
			"sigma_within": cap["sigma_within"],
			"cp": cap["cp"],
			"cpk": cap["cpk"],
			"pp": cap["pp"],
			"ppk": cap["ppk"],
			"pct_out": cap["pct_out"],
			"suggestion": spc.suggestion(cap, recent),
		})
	chart = make_chart(filters, data, lots_by_key)
	message = None if data else _("No submitted drawing inspections with measurements for these filters.")
	return columns(), data, message, chart


def collect(filters):
	conditions = {"item_code": filters.item_code, "docstatus": 1, "custom_stage": ("is", "set")}
	if filters.template:
		conditions["quality_inspection_template"] = filters.template
	if filters.stage:
		conditions["custom_stage"] = filters.stage
	if filters.from_date and filters.to_date:
		conditions["report_date"] = ("between", [filters.from_date, filters.to_date])
	qis = frappe.get_all("Quality Inspection", filters=conditions, fields=["name", "report_date", "quality_inspection_template"],
	                     order_by="report_date asc, creation asc")
	rows, lots, order = {}, defaultdict(list), []
	if not qis:
		return rows, lots, order
	names = [q.name for q in qis]
	readings = frappe.get_all(
		"Quality Inspection Reading",
		filters={"parent": ("in", names), "custom_row_type": ("in", ["Dimension", "Test", "Material"])},
		fields=["parent", "custom_balloon_no", "specification", "custom_class", "min_value", "max_value",
		        "custom_tolerance_type", "custom_unit", "custom_spec_text"],
	)
	meas = defaultdict(list)
	for m in frappe.get_all("QI Measurement", filters={"quality_inspection": ("in", names)},
	                        fields=["quality_inspection", "row_key", "value"], order_by="sample_no asc"):
		try:
			meas[(m.quality_inspection, m.row_key)].append(float(m.value))
		except (TypeError, ValueError):
			continue
	by_qi = defaultdict(list)
	for r in readings:
		by_qi[r.parent].append(r)
	for q in qis:
		for r in by_qi[q.name]:
			if filters.ctq_only and r.custom_class != "CTQ":
				continue
			key = (q.quality_inspection_template, r.custom_balloon_no)
			values = meas.get((q.name, r.custom_balloon_no))
			if not values:
				continue
			if key not in rows:
				order.append(key)
			# latest limits win (a new revision may tighten them)
			rows[key] = {
				"template": q.quality_inspection_template,
				"balloon": r.custom_balloon_no,
				"specification": r.specification,
				"class": r.custom_class,
				"limits": _limits(r),
				"min": r.min_value,
				"max": r.max_value,
				"max_only": r.custom_tolerance_type == T.MAX_ONLY,
				"unit": r.custom_unit,
			}
			lots[key].append(values)
	return rows, lots, order


def _limits(r):
	lo, hi = T.display_limit(r.min_value), T.display_limit(r.max_value)
	if r.custom_tolerance_type == T.MAX_ONLY:
		return f"≤ {hi}"
	if hi == "—":
		return f"≥ {lo}"
	return f"{lo} – {hi}"


def make_chart(filters, data, lots_by_key):
	if not data:
		return None
	pick = None
	if filters.chart_balloon:
		pick = next((d for d in data if d["balloon"] == filters.chart_balloon.strip()), None)
	pick = pick or next((d for d in data if d["class"] == "CTQ"), None) or data[0]
	points = spc.xbar_chart(lots_by_key[(pick["template"], pick["balloon"])], pick["sigma_within"])
	if not points:
		return None
	labels = [str(p["lot"]) for p in points]
	datasets = [{"name": _("Lot mean"), "values": [round(p["mean"], 6) for p in points]},
	            {"name": _("Centre"), "values": [round(p["center"], 6) for p in points]}]
	if points[0]["ucl"] is not None:
		datasets += [{"name": _("UCL"), "values": [round(p["ucl"], 6) for p in points]},
		             {"name": _("LCL"), "values": [round(p["lcl"], 6) for p in points]}]
	return {
		"data": {"labels": labels, "datasets": datasets},
		"type": "line",
		"title": _("X̄ chart · balloon {0} {1} ({2} lots, {3} beyond limits)").format(
			pick["balloon"], pick["specification"], len(points), sum(1 for p in points if p["beyond"])),
		"colors": ["#2d95f0", "#999999", "#e24c4c", "#e24c4c"],
		"lineOptions": {"dotSize": 4},
	}


def columns():
	f = lambda label, name, ftype="Data", width=100, **kw: {"label": label, "fieldname": name, "fieldtype": ftype, "width": width, **kw}
	return [
		f(_("#"), "balloon", width=50),
		f(_("Characteristic"), "specification", width=150),
		f(_("Class"), "class", width=60),
		f(_("Limits"), "limits", width=120),
		f(_("Unit"), "unit", width=60),
		f(_("Lots"), "lots", "Int", 60),
		f(_("Values"), "n", "Int", 70),
		f(_("Mean"), "mean", "Float", 90, precision=4),
		f(_("σ within"), "sigma_within", "Float", 90, precision=5),
		f(_("Cp"), "cp", "Float", 70, precision=2),
		f(_("Cpk"), "cpk", "Float", 70, precision=2),
		f(_("Pp"), "pp", "Float", 70, precision=2),
		f(_("Ppk"), "ppk", "Float", 70, precision=2),
		f(_("% out"), "pct_out", "Percent", 70),
		f(_("Suggestion"), "suggestion", width=260),
		f(_("Template"), "template", "Link", 180, options="Quality Inspection Template"),
	]
