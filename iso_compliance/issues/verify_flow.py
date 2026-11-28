# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Walks every kind of Report Issue route on the site's own records and rolls
everything back:

    bench --site <site> execute iso_compliance.issues.verify_flow.run
"""

import json

import frappe
from frappe.utils import add_days, nowdate

from iso_compliance.issues import engine, routes

ROWS = [{"problem": "Retrain the night shift", "responsible": "Administrator", "completion_by": add_days(nowdate(), 7)}]
ANSWERS = {
	"email": {"custom_reply_to": "buyer@example.com", "custom_reply_message": "Logged."},
	"ncr": {"custom_how_checked": "Returned pieces inspected", "custom_justified": "Yes", "custom_findings": "18% low",
	        "custom_containment": "120 pcs on hold", "custom_disposition": "Scrap"},
	"reinspect": {"custom_reinspection": "Re-inspected & Cleared"},
	"resolve": {"custom_ca_needed": "No", "custom_ca_reason": "One-off"},
	"fix": {"custom_fix_cause": "Picked from the wrong bin", "custom_correction": "Balance sent",
	        "custom_ca_needed": "No", "custom_ca_reason": "One-off"},
	"assign": {"custom_action_owner": "Administrator"},
	"recheck": {"custom_past_results_rechecked": "Yes", "custom_recheck_findings": "All within limits"},
	"rca": {"custom_rca_method": "5 Why", "custom_target_date": add_days(nowdate(), 14),
	        "custom_root_cause_analysis": "Cycle cut short", "custom_actions": ROWS},
	"outcome": {"custom_outcome_message": "Cause found and corrected."},
	"close": {"custom_customer_confirmed_on": nowdate()},
	"check": {"custom_effectiveness_verified": "Yes", "custom_effectiveness_evidence": "No repeat in 30 days"},
	"dcr": {"custom_dcr_change_type": "Revision", "custom_dcr_proposed_change": "Replace the table in step 3"},
	"risk": {"custom_risk_severity": "3", "custom_risk_probability": "2"},
	"risk_plan": {"custom_risk_action": "Second source", "custom_risk_target_date": add_days(nowdate(), 30)},
	"risk_review": {"custom_risk_reviewed_on": nowdate()},
}


def _actions_done(name):
	for row in frappe.get_doc("Issue", name).custom_actions:
		if row.status != "Completed":
			engine.mark_action_done(name, row.idx)


def _walk(name, overrides=None, stop_at=None):
	"""File steps until Closed; returns the keys passed through."""
	seen = []
	for _ in range(30):
		doc = frappe.get_doc("Issue", name)
		current = engine._current(engine._steps(doc))
		if not current or current["key"] == stop_at:
			break
		key = current["key"]
		values = dict(ANSWERS.get(key, {}), **(overrides or {}).get(key, {}))
		if key in ("actions", "check") and values.get("custom_effectiveness_verified") != "No":
			_actions_done(name)
		engine.complete_step(name, key, json.dumps(values, default=str))
		seen.append(key)
	return seen


def _report(doctype, name, issue_type, **more):
	values = {"issue_type": issue_type, "custom_severity": "Major", "description": "Test issue\nsecond line"}
	values.update(more)
	return engine.report_issue(doctype, name, json.dumps(values, default=str))


def _expect(label, got, want):
	ok = got == want
	print(("OK  " if ok else "FAIL"), label, "" if ok else f"\n     got  {got}\n     want {want}")
	return ok


def run():
	frappe.set_user("Administrator")
	results = []
	try:
		dn = frappe.get_all("Delivery Note", filters={"docstatus": 1}, pluck="name", limit=1)[0]
		wo = frappe.get_all("Work Order", pluck="name", limit=1)[0]
		cd = frappe.get_all("Controlled Document", pluck="name", limit=1)[0]
		item = frappe.get_all("Delivery Note Item", filters={"parent": dn}, pluck="item_code", limit=1)[0]

		# 1. customer complaint about the product, justified: 8 steps
		a = _report("Delivery Note", dn, "Product / Material NC", custom_customer_complaint=1, custom_item=item)
		doc = frappe.get_doc("Issue", a)
		results.append(_expect("A: 8 steps", [s["key"] for s in engine._steps(doc)], routes.build_route("Product / Material NC", 1)))
		results.append(_expect("A: one open assignment after reporting",
			frappe.db.count("ToDo", {"reference_type": "Issue", "reference_name": a, "status": "Open"}), 1))
		results.append(_expect("A: assignment is the step owner",
			frappe.db.get_value("ToDo", {"reference_type": "Issue", "reference_name": a, "status": "Open"}, "allocated_to"),
			doc.custom_step_owner))
		seen = _walk(a)
		doc.reload()
		results.append(_expect("A: walked", seen, ["email", "ncr", "rca", "outcome", "close", "check"]))
		results.append(_expect("A: closed", (doc.status, doc.custom_step), ("Closed", "Closed")))
		results.append(_expect("A: NCR resolved, linked back", frappe.db.get_value(
			"Non Conformance", doc.custom_non_conformance, ["status", "custom_issue", "custom_source"]),
			("Resolved", a, "Customer Complaint")))
		results.append(_expect("A: corrective action verified", frappe.db.get_value(
			"Quality Action", doc.custom_quality_action, ["custom_effectiveness_verified", "custom_issue"]), ("Yes", a)))
		results.append(_expect("A: two emails on the Issue", frappe.db.count(
			"Communication", {"reference_doctype": "Issue", "reference_name": a, "sent_or_received": "Sent"}), 2))
		results.append(_expect("A: no open assignment once closed",
			frappe.db.count("ToDo", {"reference_type": "Issue", "reference_name": a, "status": "Open"}), 0))
		results.append(_expect("A: corrective action needed logged", (doc.custom_ca_needed, doc.custom_justified), ("Yes", "Yes")))

		rows = engine.get_report_context("Delivery Note", dn)["items"]
		m = _report("Delivery Note", dn, "Product / Material NC", custom_customer_complaint=1,
		            items=rows + [{"item_code": "NOT-ON-THE-NOTE", "batch": ""}])
		results.append(_expect("Ticked items: first one is the Item, strangers dropped",
			(frappe.db.get_value("Issue", m, "custom_item"), len((frappe.db.get_value("Issue", m, "custom_items_affected") or "").splitlines())),
			(rows[0]["item_code"], len(rows) if len(rows) > 1 else 0)))

		# 2. not justified: RCA and Check drop out, NCR is kept
		b = _report("Delivery Note", dn, "Product / Material NC", custom_customer_complaint=1, custom_item=item)
		seen = _walk(b, {"ncr": {"custom_justified": "No", "custom_containment": "", "custom_disposition": ""}})
		doc = frappe.get_doc("Issue", b)
		results.append(_expect("Not justified: 6 steps", seen, ["email", "ncr", "outcome", "close"]))
		results.append(_expect("Not justified: NCR kept, no corrective action",
			(bool(doc.custom_non_conformance), doc.custom_quality_action, doc.custom_ca_needed, doc.status), (True, None, "No", "Closed")))

		# 3. rework adds a re-inspection; Check = No goes back to RCA
		c = _report("Delivery Note", dn, "Product / Material NC", custom_customer_complaint=1, custom_item=item)
		seen = _walk(c, {"ncr": {"custom_disposition": "Rework"}}, stop_at="check")
		results.append(_expect("Rework: re-inspect added", seen, ["email", "ncr", "reinspect", "rca", "outcome", "close"]))
		engine.complete_step(c, "check", json.dumps({"custom_effectiveness_verified": "No",
			"custom_effectiveness_evidence": "Repeat complaint"}))
		doc = frappe.get_doc("Issue", c)
		results.append(_expect("Check = No: back at RCA, complaint stays closed with the customer",
			(doc.custom_step, doc.status), ("RCA and CAPA", "Resolved")))
		results.append(_expect("Check = No: then to Closed", _walk(c), ["rca", "check"]))

		# 4. internal, no inspection step: NCR then Resolve; Yes adds RCA and Check
		d = _report("Work Order", wo, "Quantity or Item Discrepancy", custom_qty_received=90)
		seen = _walk(d, {"resolve": {"custom_ca_needed": "Yes", "custom_ca_reason": "Second time"}})
		results.append(_expect("Internal with corrective action", seen, ["ncr", "resolve", "rca", "check"]))
		e = _report("Work Order", wo, "Packaging or Handling Damage")
		results.append(_expect("Internal without: 4 steps", _walk(e), ["ncr", "resolve"]))
		results.append(_expect("Internal: not a complaint, no customer",
			frappe.db.get_value("Issue", e, ["custom_customer_complaint", "customer"]), (0, None)))

		# 5. complaint fixed by a department
		f = _report("Delivery Note", dn, "Quantity or Item Discrepancy", custom_customer_complaint=1, custom_qty_received=90)
		results.append(_expect("Department fix: 6 steps", _walk(f), ["email", "fix", "outcome", "close"]))
		g = _report("Delivery Note", dn, "Service Complaint", custom_severity="Critical")
		results.append(_expect("Critical forces corrective action", _walk(g), ["email", "fix", "rca", "outcome", "close", "check"]))
		results.append(_expect("Service Complaint is always a complaint",
			frappe.db.get_value("Issue", g, "custom_customer_complaint"), 1))

		# 6. straight to corrective action
		h = _report("Work Order", wo, "Process Nonconformance")
		results.append(_expect("Process NC: 7 steps", _walk(h), ["assign", "rca", "actions", "complete", "check"]))
		i = _report("Work Order", wo, "Calibration Issue", custom_what_stopped="Vernier 12",
		            custom_last_good_calibration=add_days(nowdate(), -200))
		results.append(_expect("Calibration: 8 steps", _walk(i), ["assign", "recheck", "rca", "actions", "complete", "check"]))

		# 7. single sub-form routes
		j = _report("Controlled Document", cd, "Document Change Request", custom_controlled_document=cd)
		seen = _walk(j, stop_at="dcr_issue")
		doc = frappe.get_doc("Issue", j)
		results.append(_expect("Change request raised", (seen, bool(doc.custom_change_request)), (["dcr"], True)))
		try:
			engine.complete_step(j, "dcr_issue", "{}")
			results.append(_expect("Change request: blocked until implemented", "passed", "blocked"))
		except frappe.ValidationError:
			results.append(_expect("Change request: blocked until implemented", "blocked", "blocked"))
		k = _report("Work Order", wo, "Risk Identified")
		designation = frappe.get_all("Designation", pluck="name", limit=1)[0]
		seen = _walk(k, {"risk_plan": {"custom_risk_responsibility": designation}})
		doc = frappe.get_doc("Issue", k)
		results.append(_expect("Risk: 5 steps, register entry closed",
			(seen, frappe.db.get_value("Risk and Opportunity", doc.custom_risk, "status")),
			(["risk", "risk_plan", "risk_review"], "Closed")))

		# 8. guards
		try:
			_report("Work Order", wo, "Product / Material NC", custom_customer_complaint=1)
			results.append(_expect("Complaint needs a customer record", "passed", "blocked"))
		except frappe.ValidationError:
			results.append(_expect("Complaint needs a customer record", "blocked", "blocked"))
		plain = frappe.get_doc({"doctype": "Issue", "subject": "Typed in by hand"}).insert()
		results.append(_expect("An Issue typed in by hand has no steps", engine.get_state(plain.name), None))

		# 9. a filed step is closed to everyone but its owner on their turn
		n = _report("Delivery Note", dn, "Product / Material NC", custom_customer_complaint=1, custom_item=item)
		_walk(n, stop_at="rca")
		other = frappe.get_all("User", filters={"enabled": 1, "user_type": "System User",
			"name": ["not in", ["Administrator", "Guest"]]}, pluck="name")
		other = next((u for u in other if "System Manager" not in frappe.get_roles(u)
			and u not in engine.candidates("quality")), None)
		if other:
			frappe.set_user(other)
			try:
				doc = frappe.get_doc("Issue", n)
				doc.custom_findings = "Changed by someone else"
				doc.flags.ignore_permissions = True
				doc.save()
				results.append(_expect("Guard: a filed step cannot be changed by others", "saved", "blocked"))
			except frappe.PermissionError:
				results.append(_expect("Guard: a filed step cannot be changed by others", "blocked", "blocked"))
			frappe.set_user("Administrator")
		results.append(_expect("Email recorded on the Issue with no address asked up front",
			frappe.db.count("Communication", {"reference_doctype": "Issue", "reference_name": n}), 1))
	finally:
		frappe.db.rollback()
	print(f"\n{sum(results)} of {len(results)} checks passed. Everything was rolled back.")
