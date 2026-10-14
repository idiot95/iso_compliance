# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Jinja helpers for the Certificate of Conformity.

The certificate is issued against the Delivery Note, but the evidence is born
earlier: at despatch (the row's own Outgoing inspection), at completion (the
PDI on the Manufacture entry) and during production (the Job Card
inspections). The resolver walks the trace the batches already carry --
delivered batch, the Manufacture entry that produced it, its Work Order, that
order's Job Cards -- and returns every inspection on the chain, staged.
"""

import frappe


def _row_batches(row) -> list[str]:
	batches = []
	if row.get("batch_no"):
		batches.append(row.batch_no)
	if row.get("serial_and_batch_bundle"):
		batches += frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": row.serial_and_batch_bundle, "batch_no": ("is", "set")},
			pluck="batch_no",
		)
	return list(dict.fromkeys(batches))


def _manufacture_entries(item_code: str, batches: list[str]) -> list:
	if not batches:
		return []
	entries = set(
		frappe.get_all(
			"Stock Entry Detail",
			filters={
				"batch_no": ("in", batches),
				"is_finished_item": 1,
				"docstatus": 1,
				"item_code": item_code,
			},
			pluck="parent",
		)
	)
	# v16 keeps batch identity in bundles on the finished row
	bundles = frappe.get_all(
		"Serial and Batch Entry", filters={"batch_no": ("in", batches)}, pluck="parent"
	)
	if bundles:
		entries |= set(
			frappe.get_all(
				"Serial and Batch Bundle",
				filters={
					"name": ("in", bundles),
					"voucher_type": "Stock Entry",
					"item_code": item_code,
				},
				pluck="voucher_no",
			)
		)
	if not entries:
		return []
	return frappe.get_all(
		"Stock Entry",
		filters={"name": ("in", list(entries)), "purpose": "Manufacture", "docstatus": 1},
		fields=["name", "work_order"],
	)


def _receipt_inspections(item_code: str, batches: list[str]) -> list:
	"""Drawing-based incoming inspections of the receipts these batches came
	from -- for traded items, the receipt inspection is the final one (QI
	SPEC v2, Phase E). Legacy incoming inspections are left out so existing
	certificates read exactly as before."""
	if not batches:
		return []
	receipts = set(
		frappe.get_all("Batch", filters={"name": ("in", batches), "reference_doctype": "Purchase Receipt"},
		               pluck="reference_name")
	)
	bundles = frappe.get_all("Serial and Batch Entry", filters={"batch_no": ("in", batches)}, pluck="parent")
	if bundles:
		receipts |= set(
			frappe.get_all(
				"Serial and Batch Bundle",
				filters={"name": ("in", bundles), "voucher_type": "Purchase Receipt", "item_code": item_code,
				         "docstatus": 1},
				pluck="voucher_no",
			)
		)
	if not receipts:
		return []
	return [
		frappe.get_doc("Quality Inspection", name)
		for name in frappe.get_all(
			"Quality Inspection",
			filters={"reference_type": "Purchase Receipt", "reference_name": ("in", list(receipts)),
			         "item_code": item_code, "custom_stage": "Incoming", "docstatus": ("<", 2)},
			order_by="report_date asc, name asc",
			pluck="name",
		)
	]


def coc_row_inspections(row) -> dict:
	"""Every inspection behind one delivered row, staged for the certificate."""
	out = {"outgoing": None, "pdi": [], "in_process": [], "work_orders": [], "incoming": []}

	if row.get("quality_inspection"):
		out["outgoing"] = frappe.get_doc("Quality Inspection", row.quality_inspection)

	for entry in _manufacture_entries(row.item_code, _row_batches(row)):
		for name in frappe.get_all(
			"Quality Inspection",
			filters={
				"reference_type": "Stock Entry",
				"reference_name": entry.name,
				"item_code": row.item_code,
				"docstatus": ("<", 2),
			},
			pluck="name",
		):
			out["pdi"].append(frappe.get_doc("Quality Inspection", name))
		if entry.work_order and entry.work_order not in out["work_orders"]:
			out["work_orders"].append(entry.work_order)

	out["incoming"] = _receipt_inspections(row.item_code, _row_batches(row))

	if out["work_orders"]:
		job_cards = frappe.get_all(
			"Job Card", filters={"work_order": ("in", out["work_orders"])}, pluck="name"
		)
		if job_cards:
			for name in frappe.get_all(
				"Quality Inspection",
				filters={"reference_type": "Job Card", "reference_name": ("in", job_cards), "docstatus": ("<", 2)},
				order_by="report_date asc, name asc",
				pluck="name",
			):
				out["in_process"].append(frappe.get_doc("Quality Inspection", name))
	return out


def coc_row_aggregate(row) -> dict:
	"""The certificate view: every parameter ever measured for this delivered
	row, one line each, with the observed range across all inspections and all
	sample readings. The n column is the sampling story -- how many measured
	values stand behind the range.

	Drawing inspections (QI SPEC v2) can carry one parameter at several
	balloons, so lines are keyed by (parameter, balloon) -- legacy readings have
	no balloon and group exactly as before -- and their values come from QI
	Measurement, which holds every sample, not just the first ten."""
	from iso_compliance.qi.certificates import _limit_text as limit_text
	from iso_compliance.qi.inspection import measurements

	chain = coc_row_inspections(row)
	parameters: dict[tuple, dict] = {}
	concessions: list[str] = []

	def absorb(qi, stage):
		drawing = any(r.get("custom_row_type") for r in qi.readings)
		meas = measurements(qi.name) if drawing else {}
		concession = qi.get("custom_disposition") == "Accept under Concession"
		if concession:
			concessions.append(qi.get("custom_concession_no") or qi.name)
		for r in qi.readings:
			balloon = r.get("custom_balloon_no") or ""
			p = parameters.setdefault(
				(r.specification, balloon),
				{
					"specification": r.specification,
					"balloon": balloon,
					"class": r.get("custom_class") or "",
					"spec": (r.get("custom_spec_text") or "")
					if r.get("custom_row_type")
					else (r.value or (r.acceptance_formula if r.formula_based_criteria else "") or ""),
					"min_spec": r.min_value,
					"max_spec": r.max_value,
					"numeric": r.numeric,
					"n": 0,
					"obs_min": None,
					"obs_max": None,
					"values": [],
					"ok": True,
					"stages": [],
					"concession": False,
					# drawing rows print their limits as read ("≤ 35", "OK / NG")
					"limits": limit_text(r) if r.get("custom_row_type") else None,
					"unit": r.get("custom_unit") or r.get("custom_uom") or "",
				},
			)
			if stage not in p["stages"]:
				p["stages"].append(stage)
			if r.status and r.status != "Accepted":
				p["ok"] = False
				p["concession"] = p["concession"] or concession
			if drawing and r.get("custom_row_type"):
				for m in meas.get(balloon, []):
					if r.get("custom_row_type") == "Visual":
						p["n"] += 1
						if m.value not in p["values"]:
							p["values"].append(m.value)
						continue
					try:
						value = float(m.value)
					except (TypeError, ValueError):
						continue
					p["n"] += 1
					p["obs_min"] = value if p["obs_min"] is None else min(p["obs_min"], value)
					p["obs_max"] = value if p["obs_max"] is None else max(p["obs_max"], value)
				continue
			if r.numeric:
				for i in range(1, 11):
					raw = r.get(f"reading_{i}")
					if raw in (None, ""):
						continue
					try:
						value = float(raw)
					except (TypeError, ValueError):
						continue
					p["n"] += 1
					p["obs_min"] = value if p["obs_min"] is None else min(p["obs_min"], value)
					p["obs_max"] = value if p["obs_max"] is None else max(p["obs_max"], value)
			elif r.reading_value:
				p["n"] += 1
				if r.reading_value not in p["values"]:
					p["values"].append(r.reading_value)

	for qi in chain.get("incoming") or []:
		absorb(qi, "Incoming")
	for qi in chain["in_process"]:
		absorb(qi, "In-Process")
	for qi in chain["pdi"]:
		absorb(qi, "Final PDI")
	if chain["outgoing"]:
		absorb(chain["outgoing"], "Despatch")

	return {
		"parameters": list(parameters.values()),
		"work_orders": chain["work_orders"],
		"outgoing": chain["outgoing"].name if chain["outgoing"] else None,
		"pdi": [qi.name for qi in chain["pdi"]],
		"incoming": [qi.name for qi in chain.get("incoming") or []],
		"in_process_count": len(chain["in_process"]),
		"all_accepted": all(p["ok"] for p in parameters.values()) if parameters else False,
		"has_balloons": any(p["balloon"] for p in parameters.values()),
		"concessions": list(dict.fromkeys(concessions)),
	}
