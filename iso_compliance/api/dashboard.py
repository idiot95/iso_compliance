# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Numbers behind the compliance dashboard.

Cards that a plain DocType filter can express are configured as Document Type
cards. What lives here is the rest: questions that span DocTypes, or that ask
whether something is *absent* -- which is usually where a management system is
actually failing. A count of corrective actions is only meaningful next to the
count of nonconformities that should have produced them.

Every query orders and filters explicitly. None of these is a health score; each
one names a specific thing somebody has to go and do.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

#: The ERPNext DocTypes each ISO area is actually recorded in on this site.
NONCONFORMANCE = "Non Conformance"
CORRECTIVE_ACTION = "Quality Action"
MANAGEMENT_REVIEW = "Quality Meeting"
INSPECTION = "Quality Inspection"
INSTRUMENT_CATEGORY = "Measuring Instruments"


def _card(value, label=None):
	return {"value": value, "fieldtype": "Int", "label": label}


# ---------------------------------------------------------------------------
# Document control (ISO 9001 clause 7.5)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def documents_without_approval_evidence(filters=None):
	"""Controlled documents carrying no Prepared / Reviewed / Approved stamp.

	This is the Major NC expressed as a number. It should fall to zero as
	documents are routed through the workflow.
	"""
	return _card(
		frappe.db.count(
			"Controlled Document",
			{"approved_by": ("is", "not set")},
		)
	)


@frappe.whitelist()
def documents_never_written(filters=None):
	"""Entries listed in the register that have no document behind them."""
	return _card(frappe.db.count("Controlled Document", {"workflow_state": "Draft"}))


@frappe.whitelist()
def documents_review_overdue(filters=None):
	return _card(
		frappe.db.count(
			"Controlled Document",
			{
				"next_review_date": ("<", nowdate()),
				"workflow_state": ("not in", ("Superseded", "Obsolete")),
			},
		)
	)


@frappe.whitelist()
def documents_review_due_soon(filters=None, days: int = 90):
	return _card(
		frappe.db.count(
			"Controlled Document",
			{
				"next_review_date": ("between", [nowdate(), add_days(nowdate(), days)]),
				"workflow_state": ("not in", ("Superseded", "Obsolete")),
			},
		)
	)


# ---------------------------------------------------------------------------
# Nonconformity and corrective action (clauses 8.7, 10.2)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def corrective_actions_missing(filters=None):
	"""Nonconformities with no corrective action recorded anywhere.

	Clause 10.2 expects a nonconformity to lead to action. If this equals the
	nonconformity count, the corrective action process is not being recorded.
	"""
	ncs = frappe.db.count(NONCONFORMANCE)
	if not frappe.db.exists("DocType", CORRECTIVE_ACTION):
		return _card(ncs)
	cars = frappe.db.count(CORRECTIVE_ACTION)
	return _card(max(ncs - cars, 0))


@frappe.whitelist()
def open_nonconformities(filters=None):
	return _card(frappe.db.count(NONCONFORMANCE, {"status": ("!=", "Resolved")}))


@frappe.whitelist()
def rejected_inspections_cancelled(filters=None):
	"""Inspections that were rejected and then cancelled.

	Cancelling a rejected inspection removes the record of the rejection. Clause
	8.7 requires nonconforming output to be retained as evidence, so anything
	counted here is evidence that no longer exists in a submitted document.
	"""
	return _card(frappe.db.count(INSPECTION, {"status": "Rejected", "docstatus": 2}))


# ---------------------------------------------------------------------------
# Calibration (clause 7.1.5)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def instruments_not_in_service(filters=None):
	"""Measuring instruments still in draft or cancelled rather than submitted."""
	return _card(
		frappe.db.count("Asset", {"asset_category": INSTRUMENT_CATEGORY, "docstatus": ("!=", 1)})
	)


@frappe.whitelist()
def calibration_overdue(filters=None):
	"""Maintenance or calibration tasks past their due date.

	ERPNext already models this: an Asset Maintenance holds tasks with a type of
	Preventive Maintenance or Calibration, a periodicity, and a next due date.
	Nothing needed adding to Asset to make calibration reportable -- the schema
	was there and unused.
	"""
	return _card(
		frappe.db.count(
			"Asset Maintenance Task",
			{"next_due_date": ("<", nowdate()), "maintenance_status": ("!=", "Cancelled")},
		)
	)


@frappe.whitelist()
def calibration_due_soon(filters=None, days: int = 30):
	return _card(
		frappe.db.count(
			"Asset Maintenance Task",
			{
				"next_due_date": ("between", [nowdate(), add_days(nowdate(), days)]),
				"maintenance_status": ("!=", "Cancelled"),
			},
		)
	)


@frappe.whitelist()
def assets_without_maintenance_plan(filters=None):
	"""Assets with no maintenance schedule at all.

	Covers jigs, dies and measuring instruments alike: anything the business runs
	on that needs periodic attention. An asset with no plan is one nobody will be
	reminded about.
	"""
	total = frappe.db.count("Asset", {"docstatus": ("<", 2)})
	planned = frappe.db.sql(
		"""select count(distinct am.asset_name)
		   from `tabAsset Maintenance` am
		   where ifnull(am.asset_name, '') != ''"""
	)[0][0]
	return _card(max(total - (planned or 0), 0))


# ---------------------------------------------------------------------------
# Supplier control (clause 8.4)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def suppliers_without_approval(filters=None):
	"""Suppliers that have been ordered from without a recorded approval.

	Scoped to suppliers with a purchase order, because the register that matters
	is the list actually being bought from, not every party ever created.
	"""
	ordered = frappe.db.sql_list("select distinct supplier from `tabPurchase Order` where docstatus < 2")
	if not ordered:
		return _card(0)
	if not frappe.db.has_column("Supplier", "custom_approval_status"):
		return _card(len(ordered))
	approved = frappe.db.count(
		"Supplier", {"name": ("in", ordered), "custom_approval_status": "Approved"}
	)
	return _card(len(ordered) - approved)


# ---------------------------------------------------------------------------
# Audit, review and training (clauses 9.2, 9.3, 7.2)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def management_reviews_recorded(filters=None):
	if not frappe.db.exists("DocType", MANAGEMENT_REVIEW):
		return _card(0)
	return _card(frappe.db.count(MANAGEMENT_REVIEW))


@frappe.whitelist()
def training_without_effectiveness(filters=None):
	"""Training attendances with no effectiveness evaluation.

	Clause 7.2 asks for the effectiveness of training to be evaluated, not just
	that it happened.
	"""
	attended = frappe.db.count("Training Event Employee")
	if not frappe.db.exists("DocType", "Training Result"):
		return _card(attended)
	evaluated = frappe.db.count("Training Result")
	return _card(max(attended - evaluated, 0))


# ---------------------------------------------------------------------------
# Shared summary, used by the Compliance Gaps report
# ---------------------------------------------------------------------------


def get_gap_rows() -> list[dict]:
	"""One row per gap: what is wrong, how big, which clause, what to do next."""
	rows = [
		{
			"area": _("Document control"),
			"clause": "7.5",
			"finding": _("Controlled documents with no evidence of review and approval"),
			"count": documents_without_approval_evidence()["value"],
			"action": _("Route each document through the approval workflow so the stamps are written."),
			"doctype": "Controlled Document",
		},
		{
			"area": _("Document control"),
			"clause": "7.5",
			"finding": _("Register entries with no document written"),
			"count": documents_never_written()["value"],
			"action": _("Write the document, or remove the entry from the register."),
			"doctype": "Controlled Document",
		},
		{
			"area": _("Document control"),
			"clause": "7.5",
			"finding": _("Documents past their review date"),
			"count": documents_review_overdue()["value"],
			"action": _("Review and re-issue, or confirm the current revision still applies."),
			"doctype": "Controlled Document",
		},
		{
			"area": _("Calibration"),
			"clause": "7.1.5",
			"finding": _("Maintenance or calibration tasks past their due date"),
			"count": calibration_overdue()["value"],
			"action": _("Carry out the task and record an Asset Maintenance Log against it."),
			"doctype": "Asset Maintenance Task",
		},
		{
			"area": _("Calibration"),
			"clause": "7.1.5",
			"finding": _("Assets with no maintenance or calibration plan"),
			"count": assets_without_maintenance_plan()["value"],
			"action": _("Create an Asset Maintenance record with a yearly task for each jig, die and instrument."),
			"doctype": "Asset Maintenance",
		},
		{
			"area": _("Calibration"),
			"clause": "7.1.5",
			"finding": _("Measuring instruments not submitted into service"),
			"count": instruments_not_in_service()["value"],
			"action": _("Submit the Asset records so the instrument register is live."),
			"doctype": "Asset",
		},
		{
			"area": _("Nonconformity"),
			"clause": "8.7",
			"finding": _("Rejected inspections cancelled, destroying the evidence"),
			"count": rejected_inspections_cancelled()["value"],
			"action": _("Stop cancelling rejected inspections; raise a nonconformity against them instead."),
			"doctype": INSPECTION,
		},
		{
			"area": _("Corrective action"),
			"clause": "10.2",
			"finding": _("Nonconformities with no corrective action recorded"),
			"count": corrective_actions_missing()["value"],
			"action": _("Raise a Quality Action against each nonconformity and record the resolution."),
			"doctype": CORRECTIVE_ACTION,
		},
		{
			"area": _("Supplier control"),
			"clause": "8.4",
			"finding": _("Suppliers ordered from without a recorded approval"),
			"count": suppliers_without_approval()["value"],
			"action": _("Approve the Supplier approval fields, then evaluate and record each supplier."),
			"doctype": "Supplier",
		},
		{
			"area": _("Competence"),
			"clause": "7.2",
			"finding": _("Training attendances with no effectiveness evaluation"),
			"count": training_without_effectiveness()["value"],
			"action": _("Record a Training Result for each attendee."),
			"doctype": "Training Event Employee",
		},
	]

	reviews = management_reviews_recorded()["value"]
	if reviews < 1:
		rows.append(
			{
				"area": _("Management review"),
				"clause": "9.3",
				"finding": _("No management review recorded"),
				"count": 1,
				"action": _("Hold and minute a management review. Certification depends on it."),
				"doctype": MANAGEMENT_REVIEW,
			}
		)

	trading_unclassified = suppliers_trading_unclassified()
	if trading_unclassified:
		rows.append(
			{
				"area": _("Supplier control"),
				"clause": "8.4",
				"finding": _("Suppliers with orders in the last 12 months but no approval status"),
				"count": trading_unclassified,
				"action": _(
					"Record a Supplier Evaluation (FRM-005) for each, or set a provisional "
					"status, so REG-007 is a controlled list."
				),
				"doctype": "Supplier Evaluation",
			}
		)

	overdue_suppliers = suppliers_past_reapproval()
	if overdue_suppliers:
		rows.append(
			{
				"area": _("Supplier control"),
				"clause": "8.4",
				"finding": _("Suppliers past their re-approval due date"),
				"count": overdue_suppliers,
				"action": _("Complete the drafted FRM-005 re-evaluations."),
				"doctype": "Supplier Evaluation",
			}
		)

	unstaffed = review_chain_roles_unstaffed()
	if unstaffed:
		rows.append(
			{
				"area": _("Contract review"),
				"clause": "8.2.3",
				"finding": _("Review-chain roles held by no active user: {0}").format(
					", ".join(unstaffed)
				),
				"count": len(unstaffed),
				"action": _(
					"Assign the role to the employee whose designation owns that stage "
					"(Settings → Users → open the user → Roles)."
				),
				"doctype": "Techno Commercial Review",
			}
		)

	return [r for r in rows if r["count"]]


def suppliers_trading_unclassified() -> int:
	"""Suppliers this company actually buys from who carry no approval status --
	the gap that makes REG-007 a list of names rather than a controlled register."""
	return frappe.db.sql(
		"""
		select count(distinct po.supplier)
		from `tabPurchase Order` po
		join `tabSupplier` s on s.name = po.supplier
		where po.docstatus = 1
			and po.transaction_date >= date_sub(curdate(), interval 12 month)
			and s.disabled = 0
			and ifnull(s.custom_approval_status, '') = ''
		"""
	)[0][0]


def suppliers_past_reapproval() -> int:
	return frappe.db.count(
		"Supplier",
		{"disabled": 0, "custom_reapproval_due": ("<", frappe.utils.today())},
	)


def review_chain_roles_unstaffed() -> list[str]:
	"""Reviewer roles no enabled user holds -- a stalled chain waiting to happen.

	The review chain routes by role because roles outlive people; the cost is
	that when the person holding one leaves and their user is disabled, the
	role sits empty and every review stalls at that stage. This is the
	reminder to hand the responsibility to someone else."""
	from iso_compliance.setup.install import REVIEW_CHAIN_ROLES

	unstaffed = []
	for role in REVIEW_CHAIN_ROLES:
		holders = [
			h.parent
			for h in frappe.get_all(
				"Has Role", filters={"role": role, "parenttype": "User"}, fields=["parent"]
			)
			if h.parent not in ("Administrator", "Guest")
		]
		active = holders and frappe.get_all(
			"User", filters={"name": ("in", holders), "enabled": 1}, limit=1
		)
		if not active:
			unstaffed.append(role)
	return unstaffed
