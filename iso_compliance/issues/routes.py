# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Report Issue: what each issue type asks for and which steps it goes through.

Pure data and pure functions; nothing here touches the database, so the whole
file can be unit tested without a site. engine.py reads it, setup.py creates
the Issue Types and custom fields from it, and the two scripts in public/js
draw whatever get_state() returns.

Every step is a tab on the Issue form and every answer is a real field on the
Issue, like the Sales Order's steps and the Techno-Commercial Review. A field
is a dict: fieldname, label, fieldtype, options, reqd, and

    on   the record the answer is copied to when the step is filed: "ncr" (Non
         Conformance), "ca" (Quality Action), "dcr", "risk"; none = Issue only
    to   its fieldname there, when it differs
    mandatory_depends_on / depends_on
         the usual Frappe expressions, checked by the browser and, for the
         mandatory ones, again by engine.py when the step is filed.
"""

AREAS = (
	"Product Quality",
	"Delivery and Logistics",
	"Commercial and Service",
	"Supplier",
	"Equipment and Calibration",
	"Quality System",
)

SEVERITIES = ("Critical", "Major", "Minor")

#: who may raise it: "both", "customer" (always a complaint) or "internal" (never)
ISSUE_TYPES = {
	"Product / Material NC": ("Product Quality", "both", "Product or material does not meet the specification."),
	"Design or Drawing Error": ("Product Quality", "both", "The drawing, BOM or design is wrong."),
	"Delivery Delay": ("Delivery and Logistics", "customer", "Delivered later than promised."),
	"Quantity or Item Discrepancy": ("Delivery and Logistics", "both", "Wrong item, mix-up, short or excess quantity."),
	"Packaging or Handling Damage": ("Delivery and Logistics", "both", "Damaged in packing, transit or storage."),
	"Documentation Discrepancy": ("Delivery and Logistics", "both", "A wrong or missing certificate, label or document."),
	"Invoice or Pricing Dispute": ("Commercial and Service", "customer", "The customer disputes an invoice or price."),
	"Service Complaint": ("Commercial and Service", "customer", "Slow reply or poor service."),
	"Customer Property Loss or Damage": ("Commercial and Service", "customer", "Material, tooling or drawings owned by the customer."),
	"Supplier Nonconformance": ("Supplier", "internal", "Supplier late, short, or supplied without a certificate."),
	"Equipment Breakdown": ("Equipment and Calibration", "internal", "A machine stopped or broke down."),
	"Calibration Issue": ("Equipment and Calibration", "internal", "An instrument is out of calibration."),
	"Process Nonconformance": ("Quality System", "internal", "A procedure or work instruction was not followed."),
	"Competence or Training Gap": ("Quality System", "internal", "A person lacks a skill or training the job needs."),
	"Document Change Request": ("Quality System", "internal", "A controlled document needs changing."),
	"Risk Identified": ("Quality System", "internal", "A new risk to record in the risk register."),
}

PRODUCT_TYPES = ("Product / Material NC", "Quantity or Item Discrepancy", "Packaging or Handling Damage")

#: record the issue was reported on -> the area suggested in the small form
AREA_BY_DOCTYPE = {
	"Delivery Note": "Product Quality",
	"Sales Order": "Delivery and Logistics",
	"Sales Invoice": "Commercial and Service",
	"Quotation": "Commercial and Service",
	"Customer": "Commercial and Service",
	"Purchase Receipt": "Supplier",
	"Purchase Order": "Supplier",
	"Purchase Invoice": "Supplier",
	"Supplier": "Supplier",
	"Asset": "Equipment and Calibration",
	"Asset Repair": "Equipment and Calibration",
	"Workstation": "Equipment and Calibration",
	"Work Order": "Product Quality",
	"Job Card": "Product Quality",
	"Stock Entry": "Product Quality",
	"Quality Inspection": "Product Quality",
	"Item": "Product Quality",
	"BOM": "Product Quality",
	"Batch": "Product Quality",
	"Controlled Document": "Quality System",
	"Employee": "Quality System",
}

CUSTOMER_DOCTYPES = ("Delivery Note", "Sales Order", "Sales Invoice", "Quotation", "Customer")

#: who fixes a customer complaint that is not about the product
FIX_OWNER = {
	"Delivery Delay": "planning",
	"Quantity or Item Discrepancy": "stores",
	"Packaging or Handling Damage": "stores",
	"Documentation Discrepancy": "quality",
	"Invoice or Pricing Dispute": "accounts",
	"Service Complaint": "sales",
	"Customer Property Loss or Damage": "stores",
}

#: owner kind -> designations tried in order, then roles tried in order
OWNERS = {
	"sales": (("Sales Executive",), ("Sales Manager",)),
	"quality": (("Quality Manager / Management Representative",), ("Quality Manager",)),
	"inspector": (("Engineer",), ("Quality Inspector", "Quality Manager")),
	"planning": (("Production Lead",), ("Manufacturing Manager",)),
	"stores": (("Storekeeper",), ("Stock Manager",)),
	"accounts": (("Accountant",), ("Accounts Manager",)),
	"purchase": (("Purchase Executive",), ("Purchase Manager",)),
	"production": (("Production Lead", "Foreman"), ("Manufacturing Manager",)),
}

OWNER_LABEL = {
	"reporter": "Reporter",
	"sales": "Sales Executive",
	"quality": "Quality Manager",
	"inspector": "Inspector",
	"planning": "Planning and Dispatch",
	"stores": "Stores and Dispatch",
	"accounts": "Accounts",
	"purchase": "Purchase Executive",
	"production": "Production Lead",
	"action_owner": "Action Owner",
	"action_people": "people responsible for the actions",
}


def F(fieldname, label, fieldtype="Data", options=None, reqd=0, on=None, **more):
	field = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "reqd": reqd}
	if on:
		field["on"] = on
	if options:
		field["options"] = options
	field.update(more)
	return field


def S(label):
	"""A heading inside a step's tab: the fields after it sit under it."""
	return {"section": label}


YES_NO = "\nYes\nNo"
#: mildest first; the values are the Non Conformance form's own
DISPOSITIONS = "\nAccept under Concession\nRework\nRepair\nRe-grade\nReturn to Supplier\nScrap"
DISPOSITION_HELP = (
	"<b>Accept under Concession</b>: use as it is, with the customer's written approval.<br>"
	"<b>Rework</b>: redo it so it fully meets the drawing. Re-inspected after.<br>"
	"<b>Repair</b>: make it usable, though not fully to drawing. Re-inspected after.<br>"
	"<b>Re-grade</b>: use it for a different grade or purpose it does meet.<br>"
	"<b>Return to Supplier</b>: send bought material back.<br>"
	"<b>Scrap</b>: cannot be used; destroy it."
)
COMPLAINT = "eval:doc.custom_customer_complaint"
JUSTIFIED = "eval:doc.custom_justified=='Yes' || !doc.custom_customer_complaint"
IS_FIX = "eval:(doc.custom_steps || '').includes('\"fix\"')"
HOW_CHECKED = ("\nReturned pieces inspected\nSame batch in stock inspected\nOriginal inspection record reviewed"
               "\nAccepted on the customer's evidence\nCould not be checked")

#: columns of the actions table (child doctype Quality Action Resolution)
ACTION_COLUMNS = ("problem", "responsible", "completion_by", "status")

#: every step a route can contain. `tab` names the Tab Break when two steps
#: share one (Fix It and Resolve ask the same closing question).
STEPS = {
	"log": {"label": "Log Issue", "owner": "reporter", "fields": []},
	"email": {
		"label": "Email Reply", "owner": "sales", "due": (1, 1, 2), "action": "Send Email",
		"fields": [
			S("Customer's email thread"),
			F("custom_thread_html", "Email Thread", "HTML"),
			F("custom_reply_to", "To", "Data", depends_on="eval:!doc.custom_thread_message",
			  description="Only for a new email. A reply goes to everyone on the thread."),
			F("custom_reply_cc", "CC", "Data"),
			F("custom_reply_attachment", "Attachment", "Attach"),
			S("Your reply"),
			F("custom_reply_message", "Message", "Text Editor", reqd=1),
		],
	},
	"inspection": {
		"label": "Inspection", "owner": "inspector", "due": (1, 2, 3), "action": "Save Inspection",
		"help": "Do the inspection on the Quality Inspection screen, submit it, then pick it here. "
		"An accepted inspection closes the Issue.",
		"fields": [F("custom_quality_inspection", "Quality Inspection", "Link", "Quality Inspection", reqd=1)],
	},
	"ncr": {
		"label": "NCR", "owner": "quality", "due": (1, 3, 5), "action": "Save NCR",
		"fields": [
			S("1 · Verify the complaint"),
			F("custom_how_checked", "How Checked", "Select", HOW_CHECKED, on="ncr",
			  depends_on=COMPLAINT, mandatory_depends_on=COMPLAINT),
			F("custom_justified", "Justified", "Select", YES_NO, depends_on=COMPLAINT, mandatory_depends_on=COMPLAINT,
			  description="No skips RCA and CAPA and Check. The NCR is still kept."),
			F("custom_evidence", "Evidence", "Attach", on="ncr", description="Test sheet or photos."),
			F("custom_findings", "Findings", "Small Text", reqd=1, on="ncr"),
			S("2 · Contain"),
			F("custom_containment", "Containment", "Small Text", on="ncr", mandatory_depends_on=JUSTIFIED,
			  description="What has been held or quarantined."),
			S("3 · Probable cause"),
			F("custom_probable_cause", "Probable Cause", "Small Text", on="ncr",
			  description="A first view. The full root cause comes with the corrective action."),
			S("4 · Disposition: what happens to the material"),
			F("custom_disposition", "Disposition", "Select", DISPOSITIONS, on="ncr", mandatory_depends_on=JUSTIFIED),
			F("custom_concession_approval", "Concession Approval", "Attach", on="ncr",
			  depends_on="eval:doc.custom_disposition=='Accept under Concession'",
			  mandatory_depends_on="eval:doc.custom_disposition=='Accept under Concession'",
			  description="The customer's written approval."),
			F("custom_replacement", "Replacement", on="ncr", depends_on=COMPLAINT,
			  description="What is being sent to the customer, and on which order."),
			F("custom_disposition_help", "Disposition Guide", "HTML", options=DISPOSITION_HELP),
		],
	},
	"reinspect": {
		"label": "Re-inspect", "owner": "inspector", "due": (2, 3, 5), "action": "Save Re-inspection",
		"fields": [
			F("custom_reinspection_qi", "Re-inspection", "Link", "Quality Inspection", on="ncr",
			  to="custom_quality_inspection", description="The inspection done after rework or repair."),
			F("custom_reinspection", "Re-inspection After Rework", "Select",
			  "\nPending\nRe-inspected & Cleared", reqd=1, on="ncr"),
		],
	},
	"fix": {
		"label": "Fix It", "owner": "fix", "due": (1, 3, 5), "action": "Save Fix", "tab": "resolve",
		"fields": [
			S("What happened and what was done"),
			F("custom_fix_cause", "Cause", "Small Text", depends_on=IS_FIX, mandatory_depends_on=IS_FIX),
			F("custom_correction", "Correction", "Small Text", depends_on=IS_FIX, mandatory_depends_on=IS_FIX,
			  description="What was done to put it right."),
			S("Decision"),
			F("custom_ca_needed", "Corrective Action Needed", "Select", YES_NO, reqd=1),
			F("custom_ca_reason", "Reason", "Small Text", reqd=1),
		],
	},
	"resolve": {"label": "Resolve", "owner": "quality", "due": (2, 5, 7), "action": "Resolve", "tab": "resolve",
	            "fields": "fix"},
	"assign": {
		"label": "Assign Owner", "owner": "quality", "due": (1, 2, 3), "action": "Assign",
		"fields": [F("custom_action_owner", "Owner", "Link", "User", reqd=1,
		             description="Gets the root cause and action steps.")],
	},
	"recheck": {
		"label": "Re-check Results", "owner": "action_owner", "due": (2, 5, 7), "action": "Save Re-check",
		"fields": [
			F("custom_past_results_rechecked", "Past Results Re-checked", "Select", YES_NO, reqd=1),
			F("custom_recheck_findings", "What Was Found", "Small Text", reqd=1),
		],
	},
	"rca": {
		"label": "RCA and CAPA", "owner": "quality", "due": (3, 7, 10), "action": "Save RCA",
		"fields": [
			S("Root cause"),
			F("custom_rca_method", "RCA Method", "Select", "\n5 Why\nFishbone\nProcess Review\nData Analysis",
			  reqd=1, on="ca"),
			F("custom_target_date", "Target Date", "Date", reqd=1, on="ca"),
			F("custom_root_cause_analysis", "Root Cause", "Text Editor", reqd=1, on="ca", to="custom_root_cause", plain=1),
			S("Corrective actions"),
			F("custom_actions", "Actions", "Table", "Quality Action Resolution", reqd=1, on="ca", to="resolutions",
			  description="One row per action. Each Responsible person gets a task."),
		],
	},
	"new_bom": {
		"label": "New BOM", "owner": "action_owner", "due": (3, 7, 10), "action": "Save BOM",
		"fields": [F("custom_new_bom", "New BOM", "Link", "BOM", reqd=1, description="The corrected version.")],
	},
	"training": {
		"label": "Training", "owner": "action_owner", "due": (7, 14, 21), "action": "Save Training",
		"fields": [F("custom_training_event", "Training Event", "Link", "Training Event")],
	},
	"actions": {
		"label": "Do the Actions", "owner": "action_people", "due": None, "action": "Actions Done",
		"help": "Each person marks their own action Completed. The step moves on when every action is done.",
		"fields": [F("custom_actions_html", "Actions", "HTML")],
	},
	"complete": {
		"label": "Mark Completed", "owner": "quality", "due": (1, 2, 3), "action": "Mark Completed",
		"help": "Confirms every action is done. The effectiveness check falls due 30 days from today.",
		"fields": [],
	},
	"outcome": {
		"label": "Outcome", "owner": "sales", "due": (1, 1, 2), "action": "Send Outcome",
		"help": "This is an email: it goes to the customer in the same thread as the first reply.",
		"fields": [
			S("Customer's email thread"),
			F("custom_outcome_thread_html", "Email Thread", "HTML"),
			S("Your message"),
			F("custom_outcome_cc", "CC", "Data"),
			F("custom_outcome_attachment", "Attachment", "Attach"),
			F("custom_outcome_message", "Message to the Customer", "Text Editor", reqd=1),
		],
	},
	"close": {
		"label": "Close", "owner": "sales", "due": (3, 5, 7), "action": "Close Complaint",
		"help": "Closing also closes the NCR.",
		"fields": [F("custom_customer_confirmed_on", "Customer Confirmed On", "Date", reqd=1)],
	},
	"check": {
		"label": "Check", "owner": "quality", "due": 30, "action": "Save Check",
		"help": "Answer No to send the Issue back to RCA and CAPA.",
		"fields": [
			S("Actions taken"),
			F("custom_check_actions_html", "Actions", "HTML"),
			S("Did it work"),
			F("custom_effectiveness_verified", "Effectiveness Verified", "Select", YES_NO, reqd=1, on="ca"),
			F("custom_effectiveness_evidence", "Evidence", "Small Text", reqd=1, on="ca",
			  description="What shows it worked."),
		],
	},
	# single sub-form routes
	"supplier_eval": {
		"label": "Supplier Evaluation", "owner": "purchase", "due": (2, 5, 7), "action": "Save Evaluation",
		"help": "Score the supplier on the Supplier Evaluation form, then pick it here.",
		"create": "Supplier Evaluation",
		"fields": [F("custom_supplier_evaluation", "Supplier Evaluation", "Link", "Supplier Evaluation", reqd=1)],
	},
	"supplier_decide": {
		"label": "Decide", "owner": "quality", "due": (2, 5, 7), "action": "Confirm Decision",
		"help": "Submit the Supplier Evaluation with its approval decision. This step checks it is submitted.",
		"fields": [],
	},
	"asset_repair": {
		"label": "Asset Repair", "owner": "production", "due": (1, 2, 3), "action": "Save Repair",
		"help": "Record the repair on the Asset Repair form, then pick it here.",
		"create": "Asset Repair",
		"fields": [F("custom_asset_repair", "Asset Repair", "Link", "Asset Repair", reqd=1)],
	},
	"back_in_service": {
		"label": "Back in Service", "owner": "production", "due": (1, 3, 5), "action": "Confirm Back in Service",
		"help": "The Asset Repair must be marked Completed first.",
		"fields": [F("custom_hours_lost", "Hours Lost", "Float")],
	},
	"dcr": {
		"label": "Change Request", "owner": "quality", "due": (2, 5, 7), "action": "Raise Change Request",
		"fields": [
			F("custom_dcr_change_type", "Change Type", "Select", "\nRevision\nNew Document\nWithdrawal\nReinstatement",
			  reqd=1),
			F("custom_dcr_affects_training", "Affects Training", "Check"),
			F("custom_dcr_affects_other", "Affects Other Documents", "Check"),
			F("custom_dcr_proposed_change", "Proposed Change", "Text Editor", reqd=1),
		],
	},
	"dcr_issue": {
		"label": "New Revision", "owner": "quality", "due": (7, 14, 21), "action": "Confirm New Revision",
		"help": "Review and approve the Change Request on its own form and issue the revision. "
		"This step checks the request is Implemented or Rejected.",
		"fields": [],
	},
	"risk": {
		"label": "Risk Register", "owner": "quality", "due": (2, 5, 7), "action": "Save Risk",
		"fields": [
			F("custom_risk_department", "Department", "Select",
			  "\nManagement\nQuality\nProduction\nSales & Marketing\nPurchase\nAccounts"),
			F("custom_risk_severity", "Risk Severity", "Select", "\n1\n2\n3\n4\n5", reqd=1),
			F("custom_risk_probability", "Probability", "Select", "\n1\n2\n3\n4\n5", reqd=1),
			F("custom_risk_controls", "Existing Controls", "Small Text"),
		],
	},
	"risk_plan": {
		"label": "Plan the Action", "owner": "quality", "due": (3, 7, 10), "action": "Save Plan",
		"fields": [
			F("custom_risk_responsibility", "Responsibility", "Link", "Designation", reqd=1),
			F("custom_risk_target_date", "Target Date", "Date", reqd=1),
			F("custom_risk_action", "Action Required", "Text Editor", reqd=1),
		],
	},
	"risk_review": {
		"label": "Review and Close", "owner": "quality", "due": None, "action": "Close Risk",
		"fields": [F("custom_risk_reviewed_on", "Last Reviewed On", "Date", reqd=1)],
	},
	"closed": {"label": "Closed", "owner": None, "fields": []},
}
STEPS["resolve"]["fields"] = STEPS["fix"]["fields"]

#: tab order on the form: every step that owns a tab
TAB_ORDER = [k for k, s in STEPS.items() if k not in ("log", "closed") and s.get("tab", k) == k or k == "resolve"]
TAB_ORDER = [k for k in dict.fromkeys(STEPS[k].get("tab", k) for k in STEPS if k not in ("log", "closed"))]


def tab_of(key):
	return STEPS[key].get("tab", key)


def tab_fieldname(key):
	return f"custom_tab_{tab_of(key)}"


def intro_fieldname(key):
	return f"custom_intro_{tab_of(key)}"


#: extra questions the small form asks, by issue type
EXTRA_FIELDS = {
	"Design or Drawing Error": [
		F("custom_drawing_no", "Drawing No.", reqd=1),
		F("custom_drawing_revision", "Drawing Revision"),
	],
	"Delivery Delay": [
		F("custom_promised_date", "Promised Date", "Date"),
		F("custom_actual_date", "Actual Date", "Date"),
	],
	"Quantity or Item Discrepancy": [
		F("custom_qty_on_document", "Quantity on Document", "Float"),
		F("custom_qty_received", "Quantity Received", "Float", reqd=1),
	],
	"Documentation Discrepancy": [
		F("custom_which_document", "Which Document", "Select",
		  "\nTest certificate\nLabel\nDrawing revision\nInvoice\nPacking list\nOther", reqd=1),
	],
	"Invoice or Pricing Dispute": [
		F("custom_sales_invoice", "Sales Invoice", "Link", "Sales Invoice", reqd=1),
		F("custom_amount_disputed", "Amount Disputed", "Currency", reqd=1),
	],
	"Customer Property Loss or Damage": [
		F("custom_customer_property", "What Property", "Select", "\nMaterial\nTooling\nDrawings\nOther", reqd=1),
		F("custom_customer_told_on", "Customer Told On", "Date", reqd=1),
	],
	"Supplier Nonconformance": [F("custom_supplier", "Supplier", "Link", "Supplier", reqd=1)],
	"Equipment Breakdown": [
		F("custom_asset", "Asset", "Link", "Asset",
		  description="Leave empty when the machine has no Asset record."),
		F("custom_what_stopped", "What Stopped", mandatory_depends_on="eval:!doc.custom_asset"),
		F("custom_production_affected", "Production Affected", "Select", YES_NO, reqd=1,
		  description="Yes adds an inspection of what was made."),
	],
	"Calibration Issue": [
		F("custom_asset", "Instrument", "Link", "Asset"),
		F("custom_what_stopped", "Instrument Name", mandatory_depends_on="eval:!doc.custom_asset"),
		F("custom_last_good_calibration", "Last Good Calibration Date", "Date", reqd=1),
		F("custom_out_of_use", "Instrument Taken Out of Use", "Check"),
	],
	"Process Nonconformance": [
		F("custom_controlled_document", "Procedure", "Link", "Controlled Document",
		  description="The SOP or work instruction not followed."),
	],
	"Competence or Training Gap": [
		F("custom_employee", "Employee", "Link", "Employee", reqd=1),
		F("custom_skill_needed", "Skill or Training Needed", reqd=1),
	],
	"Document Change Request": [
		F("custom_controlled_document", "Controlled Document", "Link", "Controlled Document", reqd=1),
	],
}

#: what was reported: custom fields in the Issue's first tab, under Description
DETAIL_FIELDS = [
	F("custom_reported_doctype", "Reported Against Type", "Link", "DocType", read_only=1),
	F("custom_reported_name", "Reported Against", "Dynamic Link", "custom_reported_doctype", read_only=1),
	F("custom_customer_complaint", "Customer Complaint", "Check", in_standard_filter=1, read_only=1),
	F("custom_area", "Area", "Select", "\n" + "\n".join(AREAS), in_standard_filter=1, read_only=1),
	F("custom_severity", "Severity", "Select", "\n" + "\n".join(SEVERITIES), in_standard_filter=1),
	F("custom_item", "Item", "Link", "Item", read_only=1),
	F("custom_item_group", "Item Group", "Link", "Item Group", read_only=1),
	F("custom_batch", "Batch / Lot"),
	F("custom_qty_affected", "Quantity Affected", "Float"),
	F("custom_items_affected", "Items Affected", "Small Text", read_only=1,
	  description="Every item ticked when the issue was reported. Item holds the first."),
]
_seen = {f["fieldname"] for f in DETAIL_FIELDS}
for _type, _fields in EXTRA_FIELDS.items():
	for _f in _fields:
		if _f["fieldname"] not in _seen:
			_seen.add(_f["fieldname"])
			_types = [t for t, fs in EXTRA_FIELDS.items() if any(x["fieldname"] == _f["fieldname"] for x in fs)]
			DETAIL_FIELDS.append(dict(_f, reqd=0, mandatory_depends_on=None, description=None,
			                          depends_on="eval:" + " || ".join(f"doc.issue_type=={t!r}" for t in _types)))

#: where the Issue stands, and the records raised from it
STATE_FIELDS = [
	F("custom_step", "Step", read_only=1, in_list_view=1),
	F("custom_step_owner", "With", "Link", "User", read_only=1, in_list_view=1, in_standard_filter=1),
	F("custom_step_due", "Step Due", "Date", read_only=1, in_list_view=1),
	F("custom_non_conformance", "NCR", "Link", "Non Conformance", read_only=1),
	F("custom_quality_action", "Corrective Action", "Link", "Quality Action", read_only=1),
	F("custom_change_request", "Change Request", "Link", "Document Change Request", read_only=1),
	F("custom_risk", "Risk Register Entry", "Link", "Risk and Opportunity", read_only=1),
	# the Outlook conversation the first reply went into; the outcome follows it
	F("custom_thread_conversation", "Email Conversation", read_only=1, hidden=1, length=255),
	F("custom_thread_mailbox", "Email Mailbox", read_only=1, hidden=1),
	F("custom_thread_message", "Email Message", read_only=1, hidden=1, length=255),
	F("custom_thread_subject", "Email Subject", read_only=1, hidden=1),
	F("custom_customer_email", "Customer Email", read_only=1, options="Email"),
	F("custom_thread_people", "Email Participants", "Small Text", read_only=1, hidden=1),
	F("custom_steps", "Steps", "Long Text", hidden=1, read_only=1),
]

#: custom fields added to the two ERPNext quality forms the Issue fills
NCR_CUSTOM_FIELDS = [
	F("custom_issue", "Issue", "Link", "Issue", read_only=1),
	F("custom_how_checked", "How Checked", "Select", HOW_CHECKED),
	F("custom_findings", "Findings", "Small Text"),
	F("custom_evidence", "Evidence", "Attach"),
	F("custom_containment", "Containment", "Small Text"),
	F("custom_concession_approval", "Concession Approval", "Attach"),
	F("custom_probable_cause", "Probable Cause", "Small Text"),
	F("custom_replacement", "Replacement", "Data"),
]
CA_CUSTOM_FIELDS = [
	F("custom_issue", "Issue", "Link", "Issue", read_only=1),
	F("custom_effectiveness_evidence", "Effectiveness Evidence", "Small Text"),
]


def raised_by(issue_type):
	return ISSUE_TYPES[issue_type][1]


def is_complaint(issue_type, ticked):
	who = raised_by(issue_type)
	return 1 if who == "customer" else 0 if who == "internal" else int(bool(ticked))


def _is(text):
	return lambda d: text in (d.get("custom_steps") or "")


def _complaint(d):
	return bool(d.get("custom_customer_complaint"))


def _justified(d):
	return d.get("custom_justified") == "Yes" or not d.get("custom_customer_complaint")


#: the mandatory_depends_on rules again, for the server (fieldname -> test on the Issue)
MUST = {
	"custom_how_checked": _complaint,
	"custom_justified": _complaint,
	"custom_containment": _justified,
	"custom_disposition": _justified,
	"custom_concession_approval": lambda d: d.get("custom_disposition") == "Accept under Concession",
	"custom_fix_cause": _is('"fix"'),
	"custom_correction": _is('"fix"'),
}


def step_fields(key):
	"""The data fields of a step (headings and HTML carry no answer)."""
	return [f for f in STEPS[key]["fields"] if f.get("fieldtype") not in (None, "HTML")]


def all_step_fieldnames():
	return {f["fieldname"] for key in TAB_ORDER for f in step_fields(key)}


def build_route(issue_type, complaint=0, has_asset=False, production_affected=False):
	"""Step keys from Log Issue to Closed, before any answer changes them."""
	complaint = is_complaint(issue_type, complaint)
	corrective = ["assign", "rca", "actions", "complete", "check"]
	if issue_type == "Product / Material NC":
		steps = ["email", "ncr", "rca", "outcome", "close", "check"] if complaint else ["inspection", "ncr", "resolve"]
	elif issue_type in FIX_OWNER:
		steps = ["email", "fix", "outcome", "close"] if complaint else ["ncr", "resolve"]
	elif issue_type == "Design or Drawing Error":
		steps = ["assign", "rca", "new_bom", "complete", "check"]
	elif issue_type == "Supplier Nonconformance":
		steps = ["supplier_eval", "supplier_decide"]
	elif issue_type == "Equipment Breakdown":
		steps = ["asset_repair", "back_in_service"] if has_asset else list(corrective)
		if production_affected:
			steps.insert(steps.index("back_in_service") + 1 if has_asset else 0, "inspection")
	elif issue_type == "Calibration Issue":
		steps = ["assign", "recheck", "rca", "actions", "complete", "check"]
	elif issue_type == "Competence or Training Gap":
		steps = ["assign", "rca", "training", "actions", "complete", "check"]
	elif issue_type == "Document Change Request":
		steps = ["dcr", "dcr_issue"]
	elif issue_type == "Risk Identified":
		steps = ["risk", "risk_plan", "risk_review"]
	else:  # Process Nonconformance and anything added later
		steps = list(corrective)
	if complaint and "email" not in steps:
		# a customer raised something we normally handle on our own
		steps = ["email", *steps]
		at = steps.index("check") if "check" in steps else len(steps)
		steps[at:at] = ["outcome", "close"]
	return ["log", *steps, "closed"]


def add_corrective(steps, after):
	"""Corrective Action Needed = Yes on a route that had none: RCA and CAPA
	right after `after`, Check as the last working step."""
	steps = list(steps)
	if "rca" not in steps:
		steps.insert(steps.index(after) + 1, "rca")
	if "check" not in steps:
		steps.insert(steps.index("closed"), "check")
	return steps


def drop_corrective(steps):
	"""Not justified: no root cause to find and nothing to check."""
	return [s for s in steps if s not in ("rca", "check", "reinspect")]


def add_reinspect(steps):
	steps = list(steps)
	if "reinspect" not in steps:
		steps.insert(steps.index("ncr") + 1, "reinspect")
	return steps


def due_days(key, severity):
	due = STEPS[key].get("due")
	if isinstance(due, tuple):
		return due[SEVERITIES.index(severity) if severity in SEVERITIES else 1]
	return due


# ---------------------------------------------------------------- field tooltips
#: where an answer ends up, by the record it is copied to
WHERE = {
	"ncr": "Shown on the NCR raised from this Issue, and on its print.",
	"ca": "Shown on the Corrective Action raised from this Issue.",
	None: "Kept on this Issue.",
}

#: fieldname -> (what it is, what it changes or where else it shows). The second
#: part replaces the standard "where" line when the field does more than be stored.
TIPS = {
	"custom_reply_to": ("The customer's email address, for a new email only.", "Remembered as the customer's address for the Outcome email."),
	"custom_reply_cc": ("Anyone else to copy on this email.", "Added to the people already on the thread."),
	"custom_reply_attachment": ("A file to send with the email.", "Sent to the customer and listed in the Issue's email record."),
	"custom_reply_message": ("Your first reply to the customer.", "Emailed to the customer in their own thread and recorded under Activity on this Issue."),
	"custom_quality_inspection": ("The submitted inspection of the material.", "Linked on this Issue and on the NCR. An accepted inspection closes the Issue."),
	"custom_how_checked": ("How the complaint was verified.", None),
	"custom_justified": ("Whether the complaint is valid.", "Yes makes Corrective Action Needed = Yes. No removes the RCA and CAPA and Check steps; the NCR is still kept."),
	"custom_evidence": ("Test sheet or photos backing the findings.", None),
	"custom_findings": ("What the check found, in numbers where possible.", None),
	"custom_containment": ("What has been held, quarantined or stopped so no more goes out.", None),
	"custom_probable_cause": ("A first view of the cause, before the full analysis.", None),
	"custom_disposition": ("What happens to the nonconforming material.", "Shown on the NCR. Rework or Repair adds a Re-inspect step; Accept under Concession asks for the customer's approval."),
	"custom_concession_approval": ("The customer's written approval to use the material as it is.", None),
	"custom_replacement": ("What is being sent to the customer instead, and on which order.", None),
	"custom_reinspection_qi": ("The inspection done after rework or repair.", "Linked on the NCR."),
	"custom_reinspection": ("Whether the reworked material passed.", "The Issue stays at this step until it reads Re-inspected & Cleared. Shown on the NCR."),
	"custom_fix_cause": ("Why it happened.", "Also shown as Investigation / Root Cause on this Issue."),
	"custom_correction": ("What was done to put this one case right.", None),
	"custom_ca_needed": ("Whether the cause must be removed so it does not happen again.", "Yes adds the RCA and CAPA and Check steps. Set to Yes for you when Severity is Critical or it is the third issue of its type in 90 days."),
	"custom_ca_reason": ("Why corrective action is or is not needed.", "Kept on this Issue as the record of the decision."),
	"custom_action_owner": ("The person who will find the root cause and plan the actions.", "This person is assigned the RCA and CAPA step and sees it in My Work."),
	"custom_past_results_rechecked": ("Whether results measured with this instrument since its last good calibration were checked again.", None),
	"custom_recheck_findings": ("What the re-check of past results showed.", None),
	"custom_rca_method": ("The method used to find the root cause.", None),
	"custom_target_date": ("When all corrective actions should be complete.", None),
	"custom_root_cause_analysis": ("The real cause, found by the analysis.", "Shown on the Corrective Action as plain text, and sent to the customer in the RCA and CAPA report."),
	"custom_actions": ("One row for each corrective action, with who does it and by when.", "Each Responsible person gets a task. Shown on the Corrective Action; the Check step needs every row Completed."),
	"custom_new_bom": ("The corrected BOM version.", "Linked on this Issue."),
	"custom_training_event": ("The training arranged to close the gap.", "Linked on this Issue."),
	"custom_outcome_cc": ("Anyone else to copy on the outcome email.", "Added to the people already on the thread."),
	"custom_outcome_attachment": ("A file to send with the outcome.", "Sent to the customer. The RCA and CAPA report is attached for you when Outlook is connected."),
	"custom_outcome_message": ("What you tell the customer: the cause and what was done.", "Emailed to the customer in the same thread, and kept as Resolution Details on this Issue."),
	"custom_customer_confirmed_on": ("The date the customer accepted the outcome.", "Closing also closes the NCR. The Issue shows Resolved until the Check step is done."),
	"custom_effectiveness_verified": ("Whether the actions stopped the problem.", "Yes closes the Issue. No sends it back to RCA and CAPA. Shown on the Corrective Action."),
	"custom_effectiveness_evidence": ("What shows the actions worked.", None),
	"custom_supplier_evaluation": ("The Supplier Evaluation scored for this problem.", "Linked on this Issue. Its decision sets the supplier's approval status."),
	"custom_asset_repair": ("The Asset Repair record for this breakdown.", "Linked on this Issue. Its downtime and cost stay on the Asset."),
	"custom_hours_lost": ("Production hours lost to the breakdown.", None),
	"custom_dcr_change_type": ("What kind of change the document needs.", "Copied to the Document Change Request raised from this Issue."),
	"custom_dcr_affects_training": ("Tick if people need retraining after the change.", "Copied to the Document Change Request."),
	"custom_dcr_affects_other": ("Tick if other documents must change too.", "Copied to the Document Change Request."),
	"custom_dcr_proposed_change": ("The new wording or content proposed.", "Copied to the Document Change Request, where it is reviewed and approved."),
	"custom_risk_department": ("The department the risk belongs to.", "Copied to the Risk register entry."),
	"custom_risk_severity": ("How bad it would be, 1 (minor) to 5 (severe).", "Copied to the Risk register entry; with Probability it gives the risk score."),
	"custom_risk_probability": ("How likely it is, 1 (rare) to 5 (almost certain).", "Copied to the Risk register entry; with Severity it gives the risk score."),
	"custom_risk_controls": ("What already limits this risk today.", "Copied to the Risk register entry."),
	"custom_risk_responsibility": ("The designation that owns the action.", "Copied to the Risk register entry."),
	"custom_risk_target_date": ("When the action should be done.", "Copied to the Risk register entry."),
	"custom_risk_action": ("What will be done about the risk.", "Copied to the Risk register entry, which moves to In Progress."),
	"custom_risk_reviewed_on": ("The date the risk was reviewed after the action.", "Copied to the Risk register entry, which is then Closed."),
}


def tip(field):
	what, effect = TIPS.get(field["fieldname"], (None, None))
	return " ".join(p for p in (what, effect or WHERE[field.get("on")]) if p)
