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
from frappe.utils import flt, fmt_money
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

	The slabs are rupee values, so the comparison uses base_grand_total (the
	company-currency total) -- an export order priced in EUR or USD is judged
	by what it is worth in INR, not by the foreign-currency figure.
	"""
	required = required_tier(doc.base_grand_total)
	names = [doc.name]
	if doc.get("amended_from"):
		# An amendment inherits its predecessor's review; if the amended value
		# crosses a slab, the old review's tier no longer satisfies the gate
		# and a fresh review is demanded by the tier check below.
		names.append(doc.amended_from)
	reviews = frappe.get_all(
		"Techno Commercial Review",
		filters={"sales_order": ("in", names), "docstatus": ("<", 2)},
		fields=["name", "docstatus", "review_tier", "outcome", "workflow_state"],
		order_by="modified desc",
	)
	approved = [r for r in reviews if r.docstatus == 1]
	pending = [r for r in reviews if r.docstatus == 0]

	if approved and approved[0].outcome == "Reject":
		frappe.throw(
			_(
				"Techno-Commercial Review {0} concluded <b>Reject</b> for this order. "
				"It cannot be accepted; amend the review decision first."
			).format(frappe.utils.get_link_to_form("Techno Commercial Review", approved[0].name)),
			title=_("Order Rejected by Review"),
		)

	if required:
		satisfied = any(
			r.outcome in PASSING_OUTCOMES and TIER_RANK.get(r.review_tier, 0) >= TIER_RANK[required]
			for r in approved
		)
		if not satisfied:
			if pending:
				message = _(
					"Techno-Commercial Review {0} for this order is still at "
					"<b>{1}</b>. It must complete the review chain and be approved "
					"before the order can be submitted."
				).format(
					frappe.utils.get_link_to_form("Techno Commercial Review", pending[0].name),
					pending[0].workflow_state or _("Draft"),
				)
			else:
				company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
				message = _(
					"This order is {0}, so SOP-004 requires a <b>{1}</b> "
					"Techno-Commercial Review (FRM-036) before acceptance. "
					"Use <b>Create → Techno-Commercial Review</b> on this order."
				).format(fmt_money(flt(doc.base_grand_total), currency=company_currency), _(required))
			_fail(message)
	elif pending:
		_fail(
			_(
				"Techno-Commercial Review {0} was opened for this order and is still at "
				"<b>{1}</b>. Complete or cancel it before submitting the order."
			).format(
				frappe.utils.get_link_to_form("Techno Commercial Review", pending[0].name),
				pending[0].workflow_state or _("Draft"),
			)
		)


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
