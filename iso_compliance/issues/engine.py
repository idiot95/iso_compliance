# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Report Issue: one Issue is the parent of everything raised about a problem.

    report_issue()   the small form on any record creates the Issue
    get_state()      what the Issue form draws: steps, fields, whose turn
    complete_step()  the current step's owner files their part and hands over

The steps an Issue goes through are kept on the Issue itself (custom_steps, a
JSON list) because answers change them: a complaint judged not justified loses
its root cause step, a rework gains a re-inspection. routes.py holds the rules;
this file applies them and writes the NCR, the Corrective Action and the other
records the steps fill.

Only Issues created through Report Issue carry custom_steps. Every function
that hooks into Issue returns at once for the others, so an Issue typed in by
hand or received by email behaves exactly as before.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate, strip_html

from iso_compliance.issues import mail, routes

SUB = {
	"ncr": ("Non Conformance", "custom_non_conformance"),
	"ca": ("Quality Action", "custom_quality_action"),
	"dcr": ("Document Change Request", "custom_change_request"),
	"risk": ("Risk and Opportunity", "custom_risk"),
}

LINKS = (
	("NCR", "Non Conformance", "custom_non_conformance"),
	("Corrective Action", "Quality Action", "custom_quality_action"),
	("Quality Inspection", "Quality Inspection", "custom_quality_inspection"),
	("Change Request", "Document Change Request", "custom_change_request"),
	("Risk Register", "Risk and Opportunity", "custom_risk"),
	("Supplier Evaluation", "Supplier Evaluation", "custom_supplier_evaluation"),
	("Asset Repair", "Asset Repair", "custom_asset_repair"),
	("New BOM", "BOM", "custom_new_bom"),
	("Training Event", "Training Event", "custom_training_event"),
)

NCR_SOURCE = {
	"Purchase Receipt": "Incoming",
	"Purchase Invoice": "Incoming",
	"Stock Entry": "In-Process",
	"Job Card": "In-Process",
	"Work Order": "In-Process",
	"Delivery Note": "Final Inspection",
}


# ---------------------------------------------------------------- the small form


@frappe.whitelist()
def get_report_context(doctype, name):
	"""What the small form already knows from the record it was opened on."""
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	customer = doc.get("customer") or (doc.get("party_name") if doc.get("quotation_to") == "Customer" else None)
	if doctype == "Customer":
		customer = name
	items = []
	for row in doc.get("items") or []:
		if row.get("item_code"):
			items.append({
				"item_code": row.item_code,
				"item_name": row.get("item_name"),
				"batch": row.get("batch_no") or "",
				"qty": row.get("qty") or row.get("stock_qty") or 0,
			})
	if not items:
		item = doc.get("production_item") or doc.get("item_code") or (name if doctype == "Item" else None)
		if item:
			items.append({"item_code": item, "item_name": doc.get("item_name"), "batch": doc.get("batch_no") or "",
			              "qty": doc.get("qty") or doc.get("for_quantity") or 0})
	prefill = {
		"custom_supplier": doc.get("supplier") or (name if doctype == "Supplier" else None),
		"custom_asset": name if doctype == "Asset" else doc.get("asset"),
		"custom_sales_invoice": name if doctype == "Sales Invoice" else None,
		"custom_controlled_document": name if doctype == "Controlled Document" else None,
		"custom_employee": name if doctype == "Employee" else None,
		"custom_promised_date": doc.get("delivery_date") if doctype == "Sales Order" else None,
		"custom_qty_on_document": items[0]["qty"] if len(items) == 1 else None,
	}
	return {
		"area": routes.AREA_BY_DOCTYPE.get(doctype, ""),
		"areas": routes.AREAS,
		"severities": routes.SEVERITIES,
		"complaint": 1 if (doctype in routes.CUSTOMER_DOCTYPES and customer) else 0,
		"customer": customer,
		"items": items,
		"types": [{"name": t, "area": a, "raised_by": who, "description": d}
		          for t, (a, who, d) in routes.ISSUE_TYPES.items()],
		"extra_fields": routes.EXTRA_FIELDS,
		"product_types": routes.PRODUCT_TYPES,
		"prefill": {k: v for k, v in prefill.items() if v},
	}


@frappe.whitelist()
def report_issue(doctype, name, values):
	"""Create the Issue for a problem reported on `doctype` `name`."""
	values = frappe._dict(frappe.parse_json(values))
	ref = frappe.get_doc(doctype, name)
	ref.check_permission("read")
	issue_type = values.issue_type
	if issue_type not in routes.ISSUE_TYPES:
		frappe.throw(_("Pick an Issue Type."))
	if values.custom_severity not in routes.SEVERITIES:
		frappe.throw(_("Pick a Severity."))
	description = (values.description or "").strip()
	if not description:
		frappe.throw(_("Describe the issue."))
	complaint = routes.is_complaint(issue_type, values.custom_customer_complaint)
	extras = routes.EXTRA_FIELDS.get(issue_type, [])
	_check_mandatory(extras, values, in_dialog=True)

	ctx = get_report_context(doctype, name)
	customer = ctx["customer"] if (complaint or doctype in routes.CUSTOMER_DOCTYPES) else None
	if complaint and not customer:
		frappe.throw(_("A customer complaint must be reported on a customer's record: "
		               "a Delivery Note, Sales Order, Sales Invoice, Quotation or the Customer."))
	# the items ticked in the small form, checked against the record's own rows
	known = {(i["item_code"], i["batch"]) for i in ctx["items"]}
	picked = [i for i in (values.get("items") or []) if (i.get("item_code"), i.get("batch") or "") in known]
	if picked:
		values.custom_item = picked[0]["item_code"]
		if len(picked) == 1 and not values.custom_batch:
			values.custom_batch = picked[0].get("batch")
	items_text = "\n".join(
		" · ".join(str(p) for p in (i["item_code"], i.get("item_name"), i.get("batch") and f"Batch {i['batch']}",
		                           i.get("qty") and f"Qty {frappe.utils.flt(i['qty']):g}") if p)
		for i in picked
	)
	first_line = description.splitlines()[0]
	if len(first_line) > 70:
		first_line = first_line[:70].rsplit(" ", 1)[0]
	issue = frappe.new_doc("Issue")
	issue.update({
		"subject": _("{0} on {1}").format(first_line, name)[:140],
		"issue_type": issue_type,
		"description": frappe.utils.escape_html(description).replace("\n", "<br>"),
		"customer": customer,
		"custom_reported_doctype": doctype,
		"custom_reported_name": name,
		"custom_customer_complaint": complaint,
		"custom_area": routes.ISSUE_TYPES[issue_type][0],
		"custom_severity": values.custom_severity,
		"custom_item": values.custom_item,
		"custom_items_affected": items_text if len(picked) > 1 else None,
		"custom_batch": values.custom_batch,
		"custom_qty_affected": values.custom_qty_affected,
		"custom_sales_order": _sales_order(ref),
	})
	if values.custom_item:
		issue.custom_item_group = frappe.db.get_value("Item", values.custom_item, "item_group")
	for field in extras:
		issue.set(field["fieldname"], values.get(field["fieldname"]))

	keys = routes.build_route(
		issue_type, complaint,
		has_asset=bool(issue.get("custom_asset")),
		production_affected=issue.get("custom_production_affected") == "Yes",
	)
	steps = [{"key": k, "status": "pending"} for k in keys]
	steps[0].update(status="done", by=frappe.session.user, on=str(now_datetime())[:19])
	issue.custom_steps = json.dumps(steps)
	_start_next(issue, steps)
	issue.flags.ignore_permissions = True
	issue.insert()

	for url in values.get("attachments") or ([values.attachment] if values.get("attachment") else []):
		_attach(url, "Issue", issue.name)
	if not frappe.has_permission("Issue", "read", issue.name):
		frappe.share.add("Issue", issue.name, frappe.session.user, read=1, write=0, notify=0,
		                 flags={"ignore_share_permission": True})
	return issue.name


def _sales_order(ref):
	if ref.doctype == "Sales Order":
		return ref.name
	for row in ref.get("items") or []:
		so = row.get("against_sales_order") or row.get("sales_order")
		if so:
			return so
	return ref.get("sales_order")


def _attach(url, doctype, name):
	if not url:
		return None
	file_name = frappe.db.get_value("File", {"file_url": url}, "name", order_by="creation desc")
	if not file_name:
		return None
	file = frappe.get_doc("File", file_name)
	if file.attached_to_name and (file.attached_to_doctype, file.attached_to_name) != (doctype, name):
		copy = frappe.get_doc({"doctype": "File", "file_url": url, "file_name": file.file_name,
		                       "attached_to_doctype": doctype, "attached_to_name": name,
		                       "is_private": file.is_private})
		copy.flags.ignore_permissions = True
		copy.insert()
		return copy.name
	file.db_set({"attached_to_doctype": doctype, "attached_to_name": name})
	return file.name


# ---------------------------------------------------------------- steps on the Issue


def _steps(issue):
	return json.loads(issue.custom_steps) if issue.get("custom_steps") else []


def _current(steps):
	return next((s for s in steps if s["status"] == "current"), None)


def _set_keys(steps, keys):
	"""Re-shape the route to `keys`, keeping what is already recorded."""
	old = {s["key"]: s for s in steps}
	return [old.get(k) or {"key": k, "status": "pending"} for k in keys]


def _start_next(issue, steps):
	"""Make the first pending step current and write the summary fields."""
	for s in steps:
		if s["status"] == "current":
			s["status"] = "pending"
	nxt = next((s for s in steps if s["status"] == "pending"), None)
	if not nxt or nxt["key"] == "closed":
		if nxt:
			nxt.update(status="done", on=str(now_datetime())[:19])
		issue.custom_step, issue.custom_step_owner, issue.custom_step_due = "Closed", None, None
		issue.status = "Closed"
	else:
		nxt["status"] = "current"
		days = routes.due_days(nxt["key"], issue.custom_severity)
		nxt["due"] = str(add_days(nowdate(), days)) if days is not None else None
		nxt["owners"] = _owners(issue, nxt["key"], steps)
		done = {s["key"] for s in steps if s["status"] == "done"}
		issue.custom_step = routes.STEPS[nxt["key"]]["label"]
		issue.custom_step_owner = nxt["owners"][0] if nxt["owners"] else None
		issue.custom_step_due = nxt["due"]
		issue.status = "Resolved" if "close" in done else "Replied" if "email" in done else "Open"
	issue.custom_steps = json.dumps(steps)


def _owner_kind(issue, key):
	kind = routes.STEPS[key]["owner"]
	if kind == "fix":
		kind = routes.FIX_OWNER.get(issue.issue_type, "quality")
	if key == "rca" and issue.get("custom_action_owner"):
		kind = "action_owner"
	return kind


def candidates(kind):
	"""Everyone who holds this kind of step: by designation, else by role."""
	designations, roles = routes.OWNERS.get(kind, ((), ()))
	users = []
	for row in frappe.get_all("Employee", filters={"designation": ["in", designations], "status": "Active"},
	                          fields=["user_id"], order_by="name"):
		if row.user_id and row.user_id not in users and frappe.db.get_value("User", row.user_id, "enabled"):
			users.append(row.user_id)
	if not users and roles:
		for user in frappe.get_all("Has Role", filters={"role": ["in", roles], "parenttype": "User"},
		                           pluck="parent", order_by="parent"):
			if user not in users and user not in ("Administrator", "Guest") \
					and frappe.db.get_value("User", user, "enabled"):
				users.append(user)
	return users


def _owners(issue, key, steps):
	kind = _owner_kind(issue, key)
	if kind == "reporter":
		return [issue.owner or frappe.session.user]
	if kind == "action_owner":
		return [issue.custom_action_owner] if issue.get("custom_action_owner") else _pick(issue, "quality", steps)
	if kind == "action_people":
		people = []
		for row in issue.get("custom_actions") or []:
			if row.status != "Completed" and row.responsible and row.responsible not in people:
				people.append(row.responsible)
		return people or _owners(issue, "rca", steps)
	return _pick(issue, kind, steps)


def _pick(issue, kind, steps):
	"""One person for the step: whoever already handled this Issue in the same
	role, else the reporter if they hold it, else whoever has the fewest open."""
	users = candidates(kind)
	if not users:
		return ["Administrator"]
	for s in reversed(steps):
		if s["status"] == "done" and s.get("by") in users and s["key"] != "log" \
				and _owner_kind(issue, s["key"]) == kind:
			return [s["by"]]
	reporter = issue.owner or frappe.session.user
	if reporter in users:
		return [reporter]
	load = {u: frappe.db.count("ToDo", {"allocated_to": u, "status": "Open", "reference_type": "Issue"})
	        for u in users}
	return [min(users, key=lambda u: load[u])]


def _privileged(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def can_act(issue, step, user=None):
	user = user or frappe.session.user
	if _privileged(user) or user in (step.get("owners") or []):
		return True
	kind = _owner_kind(issue, step["key"])
	return kind in routes.OWNERS and user in candidates(kind)


def require_turn(issue, key):
	"""Stop unless `key` is the Issue's current step and the user may file it."""
	current = _current(_steps(issue))
	if not current or current["key"] != key:
		frappe.throw(_("This Issue has moved on. Reload the page."))
	if not can_act(issue, current):
		frappe.throw(_("This step is with {0}.").format(", ".join(current.get("owners") or [])), frappe.PermissionError)
	return current


def _empty(value):
	return value is None or value == "" or value == [] or (isinstance(value, str) and not strip_html(value).strip())


def _check_mandatory(fields, doc, in_dialog=False):
	missing = []
	for f in fields:
		must = routes.MUST.get(f["fieldname"])
		if in_dialog:
			needed = f.get("reqd") or _js_eval(f.get("mandatory_depends_on"), doc)
		else:
			needed = f.get("reqd") or bool(must and must(doc))
		if needed and _empty(doc.get(f["fieldname"])):
			missing.append(f["label"])
	if missing:
		frappe.throw(_("Fill in: {0}").format(", ".join(missing)), title=_("Missing"))


def _js_eval(expr, values):
	"""A small form's depends_on expression, checked on the server too."""
	if not expr:
		return False
	code = expr[5:] if expr.startswith("eval:") else expr
	code = code.replace("===", "==").replace("!==", "!=").replace("&&", " and ").replace("||", " or ")
	code = code.replace("!doc.", "not doc.")
	try:
		return bool(frappe.safe_eval(code, None, {"doc": frappe._dict(values)}))
	except Exception:
		return False


def _sub(issue, kind, create=None):
	"""The sub-record of this Issue, created on first use."""
	doctype, field = SUB[kind]
	if issue.get(field):
		return frappe.get_doc(doctype, issue.get(field))
	if create is None:
		return None
	doc = frappe.new_doc(doctype)
	doc.update(create)
	return doc


def _save_sub(issue, kind, doc):
	doc.flags.ignore_permissions = True
	doc.save()
	issue.set(SUB[kind][1], doc.name)
	return doc


def _plain(html):
	return strip_html((html or "").replace("<br>", "\n")).strip()


def _ncr_defaults(issue):
	ref_dt, ref = issue.custom_reported_doctype, issue.custom_reported_name
	out = {
		"subject": issue.subject,
		"status": "Open",
		"custom_issue": issue.name,
		"custom_source": "Customer Complaint" if issue.custom_customer_complaint else NCR_SOURCE.get(ref_dt, "Production"),
		"custom_item": issue.custom_item,
		"custom_batch_wo": issue.custom_batch,
		"custom_qty": issue.custom_qty_affected,
		"custom_supplier": issue.get("custom_supplier"),
		"custom_quality_inspection": issue.get("custom_quality_inspection"),
		"details": issue.description,
	}
	link = {"Delivery Note": "custom_delivery_note", "Purchase Receipt": "custom_purchase_receipt",
	        "Work Order": "custom_work_order"}.get(ref_dt)
	if link:
		out[link] = ref
	return out


def _ca_defaults(issue):
	return {
		"corrective_preventive": "Corrective",
		"custom_issue": issue.name,
		"custom_source": "Customer Complaint" if issue.custom_customer_complaint else "Product Non Conformance"
		if issue.get("custom_non_conformance") else "Process Analysis",
		"custom_non_conformance": issue.get("custom_non_conformance"),
		"custom_supplier": issue.get("custom_supplier"),
		"custom_related_reference": issue.name,
	}


def _write(issue, key):
	"""Copy a step's answers from the Issue to the record that keeps them: the
	NCR and the Corrective Action stay complete registers on their own."""
	touched = {}
	for f in routes.step_fields(key):
		on = f.get("on")
		if not on:
			continue
		if on not in touched:
			touched[on] = _sub(issue, on, _ncr_defaults(issue) if on == "ncr" else _ca_defaults(issue))
		doc, target, value = touched[on], f.get("to") or f["fieldname"], issue.get(f["fieldname"])
		if f["fieldtype"] == "Table":
			notes = [r.get("resolution") for r in doc.get(target)]
			doc.set(target, [])
			for i, row in enumerate(value or []):
				data = {c: row.get(c) for c in routes.ACTION_COLUMNS}
				data["status"] = data["status"] or "Open"
				data["resolution"] = row.get("resolution") or (notes[i] if i < len(notes) else None)
				doc.append(target, data)
		elif value is not None or f["fieldtype"] != "Link":
			# the register form holds plain text where the Issue has a rich editor
			doc.set(target, _plain(value) if f.get("plain") else value)
	for on, doc in touched.items():
		_save_sub(issue, on, doc)
	return touched


def _open_actions(issue):
	return len([r for r in issue.get("custom_actions") or [] if r.status != "Completed"])


def ca_forced(issue):
	"""Rules that answer Corrective Action Needed without asking."""
	if issue.custom_severity == "Critical":
		return _("Severity is Critical.")
	filters = {"issue_type": issue.issue_type, "opening_date": [">=", add_days(nowdate(), -90)]}
	if issue.customer:
		filters["customer"] = issue.customer
	if frappe.db.count("Issue", filters) >= 3:
		return _("Third issue of this type in 90 days.")
	return None


# one function per step that does more than store its answers --------------------


def _do_email(issue, steps):
	sent = mail.send(issue, issue.custom_reply_message, to=issue.custom_reply_to, cc=issue.custom_reply_cc,
	                 attachment=issue.custom_reply_attachment)
	return steps, {"mail": sent}


def _do_inspection(issue, steps):
	qi = frappe.db.get_value("Quality Inspection", issue.custom_quality_inspection, ["docstatus", "status"], as_dict=1)
	if not qi or qi.docstatus != 1:
		frappe.throw(_("Submit the Quality Inspection first."))
	if qi.status == "Accepted" and "ncr" in [s["key"] for s in steps]:
		# the inspection passed: nothing is nonconforming, so nothing more to do
		steps = _set_keys(steps, ["log", "inspection", "closed"])
	return steps, None


def _do_ncr(issue, steps):
	ncr = frappe.get_doc("Non Conformance", issue.custom_non_conformance)
	keys = [s["key"] for s in steps]
	justified = issue.custom_justified if issue.custom_customer_complaint else "Yes"
	if issue.custom_customer_complaint:
		if justified == "No":
			keys = routes.drop_corrective(keys)
			issue.custom_ca_needed, issue.custom_ca_reason = "No", _("Complaint judged not justified.")
		elif "rca" in keys:
			issue.custom_ca_needed, issue.custom_ca_reason = "Yes", _("Justified customer complaint about the product.")
	rework = justified == "Yes" and ncr.custom_disposition in ("Rework", "Repair")
	if rework:
		keys = routes.add_reinspect(keys)
	ncr.custom_reinspection = "Pending" if rework else "Not Required"
	ncr.custom_approved_by = frappe.session.user
	ncr.flags.ignore_permissions = True
	ncr.save()
	return _set_keys(steps, keys), None


def _do_reinspect(issue, steps):
	if issue.custom_reinspection != "Re-inspected & Cleared":
		frappe.throw(_("The Issue stays at this step until the re-inspection is cleared."))
	return steps, None


def _apply_ca_needed(issue, steps, after):
	if issue.custom_ca_needed == "Yes":
		return _set_keys(steps, routes.add_corrective([s["key"] for s in steps], after))
	return steps


def _do_resolve(issue, steps):
	_close_ncr(issue)
	return _apply_ca_needed(issue, steps, "resolve"), None


def _do_fix(issue, steps):
	issue.custom_root_cause = issue.custom_fix_cause
	return _apply_ca_needed(issue, steps, "fix"), None


def _do_rca(issue, steps):
	ca = frappe.get_doc("Quality Action", issue.custom_quality_action)
	ca.db_set({"custom_effectiveness_verified": "Pending", "custom_completion_date": None})
	return steps, None


def _do_actions(issue, steps):
	left = _open_actions(issue)
	if left:
		frappe.throw(_("{0} action(s) are still open. Mark each one Completed first.").format(left))
	return steps, None


def _do_complete(issue, steps):
	if _open_actions(issue):
		frappe.throw(_("Every action must be Completed first."))
	if issue.get("custom_quality_action"):
		frappe.db.set_value("Quality Action", issue.custom_quality_action, "custom_completion_date", nowdate())
	return steps, None


def _do_check(issue, steps):
	ca = frappe.get_doc("Quality Action", issue.custom_quality_action)
	if issue.custom_effectiveness_verified == "No":
		# not effective: back to the root cause, and everything after it again
		at = [s["key"] for s in steps].index("rca")
		for s in steps[at:]:
			if s["key"] not in ("outcome", "close"):
				s["status"] = "pending"
		return steps, {"back": 1}
	if _open_actions(issue):
		frappe.throw(_("Every action must be Completed before the check can pass."))
	ca.db_set({"custom_verified_by": frappe.session.user, "custom_verification_date": nowdate(),
	           "custom_completion_date": ca.custom_completion_date or nowdate()})
	return steps, None


def _do_outcome(issue, steps):
	pdfs = []
	if issue.get("custom_quality_action") and mail.status()["connected"]:
		pdf = frappe.get_print("Quality Action", issue.custom_quality_action, as_pdf=True)
		pdfs.append((_("RCA and CAPA {0}.pdf").format(issue.custom_quality_action), pdf))
	sent = mail.send(issue, issue.custom_outcome_message, cc=issue.custom_outcome_cc,
	                 attachment=issue.custom_outcome_attachment, pdfs=pdfs)
	issue.resolution_details = issue.custom_outcome_message
	return steps, {"mail": sent}


def _close_ncr(issue):
	if not issue.get("custom_non_conformance"):
		return
	ncr = frappe.get_doc("Non Conformance", issue.custom_non_conformance)
	if ncr.custom_reinspection == "Pending":
		frappe.throw(_("NCR {0} is still waiting for its re-inspection.").format(ncr.name))
	ncr.status = "Resolved"
	ncr.custom_closure_date = ncr.custom_closure_date or nowdate()
	ncr.flags.ignore_permissions = True
	ncr.save()


def _do_close(issue, steps):
	_close_ncr(issue)
	return steps, None


def _do_supplier_eval(issue, steps):
	supplier = frappe.db.get_value("Supplier Evaluation", issue.custom_supplier_evaluation, "supplier")
	if issue.get("custom_supplier") and supplier != issue.custom_supplier:
		frappe.throw(_("That evaluation is for {0}, not {1}.").format(supplier, issue.custom_supplier))
	return steps, None


def _do_supplier_decide(issue, steps):
	if frappe.db.get_value("Supplier Evaluation", issue.custom_supplier_evaluation, "docstatus") != 1:
		frappe.throw(_("Submit Supplier Evaluation {0} with its decision first.").format(issue.custom_supplier_evaluation))
	return steps, None


def _do_back_in_service(issue, steps):
	if frappe.db.get_value("Asset Repair", issue.custom_asset_repair, "repair_status") != "Completed":
		frappe.throw(_("Mark Asset Repair {0} Completed first.").format(issue.custom_asset_repair))
	return steps, None


def _do_dcr(issue, steps):
	dcr = frappe.new_doc("Document Change Request")
	dcr.update({
		"controlled_document": issue.custom_controlled_document,
		"change_type": issue.custom_dcr_change_type,
		"request_date": nowdate(),
		"reason_for_change": _plain(issue.description)[:1000] + _(" (Issue {0})").format(issue.name),
		"proposed_change": issue.custom_dcr_proposed_change,
		"affects_training": cint(issue.custom_dcr_affects_training),
		"affects_other_documents": cint(issue.custom_dcr_affects_other),
	})
	_save_sub(issue, "dcr", dcr)
	return steps, None


def _do_dcr_issue(issue, steps):
	status = frappe.db.get_value("Document Change Request", issue.custom_change_request, "status")
	if status not in ("Implemented", "Rejected"):
		frappe.throw(_("Change Request {0} is {1}. It must be Implemented or Rejected first.")
		             .format(issue.custom_change_request, status))
	return steps, None


def _do_risk(issue, steps):
	risk = frappe.new_doc("Risk and Opportunity")
	risk.update({
		"title": issue.subject, "entry_type": "Risk", "description": _plain(issue.description)[:1000],
		"source": _("Issue {0}").format(issue.name), "status": "Open",
		"department": issue.custom_risk_department, "severity": issue.custom_risk_severity,
		"probability": issue.custom_risk_probability, "existing_controls": issue.custom_risk_controls,
	})
	_save_sub(issue, "risk", risk)
	return steps, None


def _do_risk_plan(issue, steps):
	risk = frappe.get_doc("Risk and Opportunity", issue.custom_risk)
	risk.update({"action_required": issue.custom_risk_action, "responsibility": issue.custom_risk_responsibility,
	             "target_date": issue.custom_risk_target_date, "status": "In Progress"})
	_save_sub(issue, "risk", risk)
	return steps, None


def _do_risk_review(issue, steps):
	risk = frappe.get_doc("Risk and Opportunity", issue.custom_risk)
	risk.update({"last_reviewed_on": issue.custom_risk_reviewed_on, "status": "Closed"})
	_save_sub(issue, "risk", risk)
	return steps, None


@frappe.whitelist()
def complete_step(issue, step, values=None):
	"""File the current step and hand the Issue to the next owner.

	The answers are the Issue's own fields, saved on the form before this is
	called; `values` may carry them instead (scripts and tests)."""
	doc = frappe.get_doc("Issue", issue)
	steps = _steps(doc)
	require_turn(doc, step)
	fields = routes.step_fields(step)
	if values:
		names = {f["fieldname"] for f in fields}
		for name, value in frappe.parse_json(values).items():
			if name in names:
				doc.set(name, value)
	if step in ("fix", "resolve"):
		forced = ca_forced(doc)
		if forced:
			doc.custom_ca_needed, doc.custom_ca_reason = "Yes", forced
	_check_mandatory(fields, doc)
	if step == "rca":
		if not doc.get("custom_actions"):
			frappe.throw(_("Add at least one action."))
		for row in doc.custom_actions:
			if not (_plain(row.problem) and row.responsible and row.completion_by):
				frappe.throw(_("Action {0}: fill Action, Responsible and Completion By.").format(row.idx))
	_write(doc, step)

	handler = globals().get(f"_do_{step}")
	steps, info = handler(doc, steps) if handler else (steps, None)
	info = info or {}
	if not info.get("back"):
		mine = next(s for s in steps if s["key"] == step)
		mine.update(status="done", by=frappe.session.user, on=str(now_datetime())[:19])
	_start_next(doc, steps)
	_save(doc)
	return {"step": doc.custom_step, "owner": doc.custom_step_owner, "mail": info.get("mail")}


def _save(doc):
	# sending an email or filing a sub-record touches the Issue behind our back
	doc.modified = frappe.db.get_value("Issue", doc.name, "modified")
	doc.flags.ignore_permissions = True
	doc.flags.ri_engine = True
	doc.save()


@frappe.whitelist()
def mark_action_done(issue, idx):
	"""The person responsible for an action marks it Completed, at any step
	from RCA and CAPA onwards."""
	doc = frappe.get_doc("Issue", issue)
	doc.check_permission("read")
	row = next((r for r in doc.get("custom_actions") or [] if r.idx == cint(idx)), None)
	if not row:
		frappe.throw(_("No such action."))
	steps = _steps(doc)
	current = _current(steps)
	user = frappe.session.user
	if not (user == row.responsible or _privileged() or (current and can_act(doc, current))):
		frappe.throw(_("This action is with {0}.").format(frappe.utils.get_fullname(row.responsible)), frappe.PermissionError)
	if "rca" not in {s["key"] for s in steps if s["status"] == "done"}:
		frappe.throw(_("The actions are not filed yet."))
	row.status = "Completed"
	if doc.get("custom_quality_action"):
		ca = frappe.get_doc("Quality Action", doc.custom_quality_action)
		if len(ca.resolutions) >= row.idx:
			ca.resolutions[row.idx - 1].status = "Completed"
			ca.flags.ignore_permissions = True
			ca.save()
	if current and current["key"] == "actions":
		current["owners"] = _owners(doc, "actions", steps)
		doc.custom_step_owner = current["owners"][0] if current["owners"] else None
		doc.custom_steps = json.dumps(steps)
	_save(doc)
	return _open_actions(doc)


def _row_values(rows):
	return [tuple(str(r.get(c) or "") for c in routes.ACTION_COLUMNS) for r in rows or []]


def guard(doc, method=None):
	"""On every save of a Report Issue: a step's answers can be changed only by
	the person whose turn it is, while it is their turn. Filed steps and steps
	not yet reached are closed to everyone, as in the Techno-Commercial Review."""
	if not doc.get("custom_steps") or doc.flags.ri_engine or doc.is_new() or _privileged():
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	if before.custom_steps != doc.custom_steps:
		frappe.throw(_("The steps of an Issue are changed only by filing a step."))
	steps = _steps(doc)
	current = _current(steps)
	mine = current["key"] if current and can_act(doc, current) else None
	free = {f["fieldname"] for f in routes.step_fields(mine)} if mine else set()
	for s in steps:
		if s["key"] in ("log", "closed"):
			continue
		for f in routes.step_fields(s["key"]):
			name = f["fieldname"]
			if name in free:
				continue
			old, new = before.get(name), doc.get(name)
			changed = _row_values(old) != _row_values(new) if f["fieldtype"] == "Table" else (old or "") != (new or "")
			if changed:
				who = ", ".join(frappe.utils.get_fullname(u) for u in s.get("owners") or []) or _("its owner")
				frappe.throw(_("{0} ({1}) can be changed only by {2}, at that step.").format(
					f["label"], routes.STEPS[s["key"]]["label"], who), frappe.PermissionError)


# ---------------------------------------------------------------- assignment


def settle(doc, method=None):
	"""The current step's owner holds the one open assignment on the Issue.

	Runs after insert and after every save. Finished steps are Cancelled, not
	Closed: the complaint assignment rule in hcc_erp_edits (R9) reopens Closed
	assignments, and assigns by round robin whenever an Issue has none."""
	if not doc.get("custom_steps"):
		return
	steps = _steps(doc)
	current = _current(steps)
	wanted = list(current.get("owners") or []) if current else []
	todos = frappe.get_all("ToDo", filters={"reference_type": "Issue", "reference_name": doc.name},
	                       fields=["name", "allocated_to", "status"], order_by="creation")
	have = {}
	for t in todos:
		if t.allocated_to in wanted and t.allocated_to not in have:
			have[t.allocated_to] = t
		elif t.status != "Cancelled":
			_todo_status(t.name, "Cancelled")
	label = routes.STEPS[current["key"]]["label"] if current else ""
	for user in wanted:
		text = _("{0}: {1}").format(label, doc.subject)
		if user in have:
			todo = frappe.get_doc("ToDo", have[user].name)
			if todo.status != "Open" or todo.description != text or str(todo.date or "") != str(current.get("due") or ""):
				todo.update({"status": "Open", "description": text, "date": current.get("due")})
				todo.flags.ignore_permissions = True
				todo.save()
		else:
			from frappe.desk.form import assign_to

			assign_to._add({"assign_to": [user], "doctype": "Issue", "name": doc.name, "description": text,
			                "date": current.get("due"), "priority": "High" if doc.custom_severity == "Critical" else "Medium"},
			               ignore_permissions=True)


def _todo_status(name, status):
	todo = frappe.get_doc("ToDo", name)
	todo.status = status
	todo.flags.ignore_permissions = True
	todo.save()


# ---------------------------------------------------------------- what the form draws


@frappe.whitelist()
def get_state(issue):
	"""Steps, whose turn it is and what the current step still needs. The
	answers themselves are the Issue's own fields, already on the form."""
	doc = frappe.get_doc("Issue", issue)
	doc.check_permission("read")
	steps = _steps(doc)
	if not steps:
		return None
	current = _current(steps)
	user = frappe.session.user
	out_steps = []
	for i, s in enumerate(steps, 1):
		spec = routes.STEPS[s["key"]]
		kind = _owner_kind(doc, s["key"]) if spec["owner"] else None
		real = s["key"] not in ("log", "closed")
		out_steps.append({
			"key": s["key"], "idx": i, "label": spec["label"], "status": s["status"],
			"tab": routes.tab_fieldname(s["key"]) if real else None,
			"intro": routes.intro_fieldname(s["key"]) if real else None,
			"owner_label": routes.OWNER_LABEL.get(kind, ""), "owners": s.get("owners") or [],
			"by": frappe.utils.get_fullname(s["by"]) if s.get("by") else None,
			"on": s.get("on"), "due": s.get("due"),
			"action": spec.get("action"), "help": spec.get("help"), "create": spec.get("create"),
			"fields": [{"fieldname": f["fieldname"], "reqd": cint(f.get("reqd")),
			            "must": f.get("mandatory_depends_on"), "tip": routes.tip(f)} for f in routes.step_fields(s["key"])],
		})
	total = len(steps)
	state = {
		"name": doc.name, "steps": out_steps, "total": total,
		"current": current["key"] if current else None,
		"can_act": bool(current and can_act(doc, current)),
		"all_fields": sorted(routes.all_step_fieldnames()),
		"mail": mail.status(),
		"links": [{"label": label, "doctype": dt, "name": doc.get(field)} for label, dt, field in LINKS if doc.get(field)],
		"ca_forced": ca_forced(doc) if current and current["key"] in ("fix", "resolve") else None,
	}
	if current:
		spec = routes.STEPS[current["key"]]
		due = getdate(current["due"]) if current.get("due") else None
		late = (getdate() - due).days if due else 0
		who = ", ".join(frappe.utils.get_fullname(u) for u in current.get("owners") or [])
		when = "" if not due else _(" · due {0}").format(frappe.utils.formatdate(due, "d MMM"))
		if late > 0:
			when += _(" ({0} days overdue)").format(late)
		n = next(s["idx"] for s in out_steps if s["key"] == current["key"])
		if user in (current.get("owners") or []):
			text, color = _("Step {0} of {1} · Your turn: {2}{3}").format(n, total, spec["label"], when), "orange"
		else:
			text = _("Step {0} of {1} · With {2}: {3}{4}.").format(n, total, who, spec["label"], when)
			text += "" if state["can_act"] else " " + _("Nothing for you to do.")
			color = "blue"
		state["headline"] = {"text": text, "color": "red" if late > 0 else color}
	else:
		last = steps[-1]
		state["headline"] = {"text": _("Closed on {0}. All {1} steps are done.").format(
			frappe.utils.formatdate(getdate(last.get("on")), "d MMM yyyy"), total), "color": "green"}
	return state
