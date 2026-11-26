# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The make-Work-Order dialog shows the BOM that will actually be used.

The dialog fills itself from get_work_order_items, which reads only the
item's default BOM -- so a user who chose a customer-variant BOM on the Sales
Order row saw the wrong BOM in the dialog even though the before_insert hook
would build correctly. This wrapper calls the core function and then swaps in
each row's chosen BOM, so what the dialog displays, what it submits, and what
the Work Order builds are the same thing. The raw-material-request dialog
uses the same endpoint and is corrected by the same swap.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money
from erpnext.selling.doctype.sales_order.sales_order import (
	get_work_order_items as _core_get_work_order_items,
)

from iso_compliance.iso_compliance.doctype.techno_commercial_review.techno_commercial_review import (
	PASSING_OUTCOMES,
	required_tier,
)

#: "block" stops submission; "warn" shows the same message but lets the order
#: through -- the setting to use while sales staff are still learning the form.
TCR_ENFORCEMENT = "block"

TIER_RANK = {"Standard": 1, "Detailed": 2}


def enforce_techno_commercial_review(doc, method=None):
	"""SOP-004's contract-review gate, run when a Sales Order is submitted.

	Below the slabs (< STANDARD_FROM) the submission of the Sales Order is
	itself the contract review, so those orders pass untouched -- unless a
	review was opened anyway (a criticality factor spotted by sales), in which
	case the opened review must finish. At or above the slabs, an approved
	FRM-036 of at least the required tier, concluding Accept, must exist.
	A review concluding Reject always blocks, whatever the enforcement mode.

	A review done on the Quotation the order was made from counts as the
	order's own: nobody is asked for the same review twice. It still has to be
	of the tier the order's value demands.

	The slabs are rupee values, so the comparison uses base_grand_total (the
	company-currency total) -- an export order priced in EUR or USD is judged
	by what it is worth in INR, not by the foreign-currency figure.
	"""
	quotations = sorted({row.prevdoc_docname for row in doc.get("items") or [] if row.get("prevdoc_docname")})
	_gate(doc, _reviews(sales_orders=_with_predecessor(doc), quotations=quotations), _("order"))


def enforce_quotation_review(doc, method=None):
	"""The same gate, run when a Quotation is submitted: by the same slabs, on
	the quotation's company-currency total, against the reviews raised on it."""
	_gate(doc, _reviews(quotations=_with_predecessor(doc)), _("quotation"))


def _with_predecessor(doc):
	# An amendment inherits its predecessor's review; if the amended value
	# crosses a slab, the old review's tier no longer satisfies the gate
	# and a fresh review is demanded by the tier check in _gate.
	return [doc.name] + ([doc.amended_from] if doc.get("amended_from") else [])


def _reviews(sales_orders=None, quotations=None):
	or_filters = {}
	if sales_orders:
		or_filters["sales_order"] = ("in", sales_orders)
	if quotations:
		or_filters["quotation"] = ("in", quotations)
	return frappe.get_all(
		"Techno Commercial Review",
		filters={"docstatus": ("<", 2)},
		or_filters=or_filters,
		fields=["name", "docstatus", "review_tier", "outcome"],
		order_by="modified desc",
	)


def _gate(doc, reviews, noun):
	"""`noun` is what the document is called in the messages: order or quotation."""
	required = required_tier(doc.base_grand_total)
	approved = [r for r in reviews if r.docstatus == 1]
	pending = [r for r in reviews if r.docstatus == 0]

	if approved and approved[0].outcome == "Reject":
		frappe.throw(
			_(
				"Techno-Commercial Review {0} concluded <b>Reject</b> for this {1}. "
				"It cannot be accepted; amend the review decision first."
			).format(frappe.utils.get_link_to_form("Techno Commercial Review", approved[0].name), noun),
			title=_("Rejected by Review"),
		)

	if required:
		satisfied = any(
			r.outcome in PASSING_OUTCOMES and TIER_RANK.get(r.review_tier, 0) >= TIER_RANK[required]
			for r in approved
		)
		if not satisfied:
			if pending:
				message = _(
					"Techno-Commercial Review {0} for this {2} is still open "
					"(<b>{1}</b>). It must be completed before the {2} can be submitted."
				).format(
					frappe.utils.get_link_to_form("Techno Commercial Review", pending[0].name),
					_progress_text(pending[0].name),
					noun,
				)
			else:
				company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
				message = _(
					"This {2} is {0}, so SOP-004 requires a <b>{1}</b> "
					"Techno-Commercial Review (FRM-036) before acceptance. "
					"Use <b>Create → Techno-Commercial Review</b> on this {2}."
				).format(fmt_money(flt(doc.base_grand_total), currency=company_currency), _(required), noun)
			_fail(message)
	elif pending:
		_fail(
			_(
				"Techno-Commercial Review {0} was opened for this {2} and is still open "
				"(<b>{1}</b>). Complete or cancel it before submitting the {2}."
			).format(
				frappe.utils.get_link_to_form("Techno Commercial Review", pending[0].name),
				_progress_text(pending[0].name),
				noun,
			)
		)


def _progress_text(review):
	progress = frappe.get_doc("Techno Commercial Review", review).progress()
	return _("{0} of {1} done").format(progress["done"], progress["total"])


def _fail(message):
	if TCR_ENFORCEMENT == "block":
		frappe.throw(message, title=_("Techno-Commercial Review Required"))
	frappe.msgprint(message, title=_("Techno-Commercial Review Pending"), indicator="orange")


@frappe.whitelist()
def get_work_order_items(sales_order, for_raw_material_request=0):
	items = _core_get_work_order_items(sales_order, for_raw_material_request)
	if not items:
		return items

	chosen = {
		row.name: row.bom_no
		for row in frappe.get_all(
			"Sales Order Item",
			filters={"parent": sales_order, "bom_no": ("is", "set")},
			fields=["name", "bom_no"],
		)
	}
	for item in items:
		selected = chosen.get(item.get("sales_order_item") or item.get("name"))
		if selected:
			item["bom"] = selected
	return items


# Used by the Sales Order's step 5 (hcc_erp_edits sales_order_steps.js, Abdeali 25-11-2026):
# the review's state on the order, and opening it with its reviewers right after a save.
# The review itself is unchanged; the same review serves the Quotation and the order.
REVIEWER_FIELDS = ("technical_assignee", "costing_assignee", "commercial_assignee")


@frappe.whitelist()
def review_status(sales_order: str):
	"""Is a review needed for this order, why, and where the latest one stands."""
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")
	tier = required_tier(doc.base_grand_total)
	reasons = []
	if tier:
		currency = frappe.get_cached_value("Company", doc.company, "default_currency")
		reasons.append(_("Order value {0}: a {1} review is needed").format(fmt_money(flt(doc.base_grand_total), currency=currency), _(tier)))
	quotations = sorted({row.prevdoc_docname for row in doc.get("items") or [] if row.get("prevdoc_docname")})
	reviews = _reviews(sales_orders=_with_predecessor(doc), quotations=quotations)
	out = {"needed": bool(tier), "reasons": reasons, "review": None, "state": "none", "progress": None}
	if not reviews:
		return out
	latest = reviews[0]
	review = frappe.get_doc("Techno Commercial Review", latest.name)
	progress = review.progress()
	out.update(review=review.name, outcome=latest.outcome, progress={"done": progress["done"], "total": progress["total"]})
	if latest.docstatus == 0:
		out["state"] = "open"
	elif latest.outcome == "Reject":
		out["state"] = "rejected"
	elif latest.outcome in PASSING_OUTCOMES:
		out["state"] = "approved"
	else:
		out["state"] = "clarification"
	return out


@frappe.whitelist()
def reviewer_defaults():
	"""The three reviewers last picked by this user, else by anyone."""
	for filters in ({"owner": frappe.session.user}, {}):
		rows = frappe.get_all(
			"Techno Commercial Review",
			filters={**filters, "docstatus": ("<", 2), **{f: ("is", "set") for f in REVIEWER_FIELDS}},
			fields=list(REVIEWER_FIELDS),
			order_by="creation desc",
			limit=1,
		)
		if rows:
			return rows[0]
	return {}


@frappe.whitelist()
def create_review(
	sales_order: str,
	technical_assignee: str,
	costing_assignee: str,
	commercial_assignee: str,
	new_or_first_time_product: int = 0,
	customer_drawings_design_inputs: int = 0,
	special_contract_conditions: int = 0,
	special_statutory_requirements: int = 0,
):
	"""Open the order's review with its three reviewers (assigned on insert) and Sales's
	answers to "Is this order critical?". Returns an existing review for the order instead."""
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")
	existing = frappe.get_all(
		"Techno Commercial Review",
		filters={"sales_order": sales_order, "docstatus": ("<", 2)},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	if existing:
		return existing[0]
	return frappe.get_doc(
		{
			"doctype": "Techno Commercial Review",
			"sales_order": sales_order,
			"review_stage": "Contract Review",
			"technical_assignee": technical_assignee,
			"costing_assignee": costing_assignee,
			"commercial_assignee": commercial_assignee,
			"new_or_first_time_product": cint(new_or_first_time_product),
			"customer_drawings_design_inputs": cint(customer_drawings_design_inputs),
			"special_contract_conditions": cint(special_contract_conditions),
			"special_statutory_requirements": cint(special_statutory_requirements),
		}
	).insert().name


def refresh_open_reviews(doc, method=None):
	"""The quotation's review is linked to the order made from it, and a saved draft order
	brings its open draft review's value up to date."""
	quotations = list({row.prevdoc_docname for row in doc.items if row.get("prevdoc_docname")})
	if quotations:
		for name in frappe.get_all(
			"Techno Commercial Review",
			filters={"quotation": ("in", quotations), "sales_order": ("is", "not set"), "docstatus": ("<", 2)},
			pluck="name",
		):
			frappe.db.set_value("Techno Commercial Review", name, "sales_order", doc.name, update_modified=False)
	if doc.docstatus != 0:
		return
	for name in frappe.get_all(
		"Techno Commercial Review", filters={"sales_order": doc.name, "docstatus": 0}, pluck="name"
	):
		frappe.get_doc("Techno Commercial Review", name).save(ignore_permissions=True)
