# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""FRM-036: the techno-commercial review behind every accepted order (SOP-004).

One doctype serves both review depths. The tier is computed, never chosen:
order value and the four criticality factors decide it, so the slab rule in
SOP-004 and the rule enforced here cannot drift apart. Sales Order submission
checks this doctype through iso_compliance.overrides.sales_order.

The checklist parameters are seeded as rows rather than fixed as fields so a
reviewer can add an order-specific line, yet every seeded question must be
answered (Yes/No/NA) before the review can complete. Who answered which
section is not typed in -- the workflow chain (technical -> costing ->
commercial) stamps each hand-off, and permission levels keep each section
writable only by its reviewer.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

#: SOP-004 slab thresholds, in company currency.
DETAILED_FROM = 1_000_000
STANDARD_FROM = 500_000

CRITICALITY_FIELDS = (
	"new_or_first_time_product",
	"customer_drawings_design_inputs",
	"special_contract_conditions",
	"special_statutory_requirements",
)

COST_FIELDS = (
	"estimated_material_cost",
	"estimated_labour_cost",
	"estimated_overhead_cost",
	"logistics_cost",
	"other_direct_cost",
)

# The 39 detailed parameters, verbatim from the Techno-Commercial Review Form
# source file, sectioned the way the sheet numbers them (1-17, 18-25, 26-31,
# 32-39). Row 40, the final recommendation, is the outcome field.
TECHNICAL_PARAMETERS = (
	"Customer specifications clearly defined",
	"Technical drawings / documents reviewed",
	"Applicable standards / codes identified",
	"Legal / statutory requirements identified",
	"Technical feasibility confirmed",
	"Manufacturing / service capability available",
	"Required machinery / equipment available",
	"Required manpower / competency available",
	"Raw material / resource availability assessed",
	"Special process / subcontracting requirement identified",
	"Inspection / testing requirements identified",
	"Quality / acceptance criteria defined",
	"Packaging / preservation requirements reviewed",
	"Delivery schedule technically achievable",
	"Installation / commissioning requirement reviewed",
	"Customer site conditions / access requirements reviewed",
	"Warranty / after-sales requirements reviewed",
)

COSTING_PARAMETERS = (
	"Quotation prepared as per technical requirement",
	"Cost of material assessed",
	"Labour / manpower cost assessed",
	"Manufacturing / service overheads considered",
	"Transportation / logistics cost considered",
	"Testing / inspection cost considered",
	"Installation / commissioning cost considered",
	"Taxes / duties / statutory charges considered",
)

COMMERCIAL_PARAMETERS = (
	"Customer payment terms reviewed",
	"Credit / commercial risk assessed",
	"Target price / expected margin evaluated",
	"Price escalation / variation clause reviewed",
	"Penalty / LD clauses reviewed",
	"Delivery / completion commitment reviewed",
)

# Normalised so OK is always the favourable answer -- the source sheet's
# "risks identified: Yes" was good diligence but read as bad news, which made
# any arithmetic on the answers meaningless. The sheet's last two rows
# ("conditions acceptable", "feasibility confirmed") became the computed
# recommendation rather than checklist rows.
OVERALL_PARAMETERS = (
	"Contractual risks reviewed and acceptable / mitigated",
	"Technical risks reviewed and acceptable / mitigated",
	"Commercial risks reviewed and acceptable / mitigated",
	"Opportunities considered and noted in remarks",
	"No unresolved deviations from customer requirements",
	"No customer clarifications outstanding",
)

# The standard-depth review: the order verified against the quotation, split
# so each reviewer in the chain still confirms their own portion.
STANDARD_TECHNICAL = (
	"Specification and grade match the quotation / previously supplied item",
	"Delivery schedule technically achievable",
)

STANDARD_COSTING = (
	"Price matches the quotation / established terms",
	"Taxes / duties / statutory charges as quoted",
)

STANDARD_COMMERCIAL = (
	"Payment terms as per quotation",
	"No special contractual conditions (penalty / LD / price variation) introduced in the order",
)

PASSING_OUTCOMES = ("Accept", "Accept with Conditions")


@frappe.whitelist()
def record_send_back(review: str, reason: str):
	"""The reason a reviewer sent a review back, written where people look.

	Called by the Send Back popup before the workflow action runs. The reason
	lands as a comment on the review's own timeline and, because the fix
	usually happens on the order, on the Sales Order's timeline too.
	"""
	doc = frappe.get_doc("Techno Commercial Review", review)
	doc.check_permission("write")
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("A reason is required to send a review back."))
	stage = _(doc.workflow_state or "Draft")
	doc.add_comment("Comment", _("Sent back from {0}: {1}").format(stage, reason))
	if doc.sales_order:
		frappe.get_doc("Sales Order", doc.sales_order).add_comment(
			"Comment",
			_("Review {0} sent back from {1}: {2}").format(doc.name, stage, reason),
		)


def required_tier(order_value):
	"""The SOP-004 slab a given order value falls in, or None below the
	form-based slabs (there, submitting the Sales Order is the review)."""
	value = flt(order_value)
	if value >= DETAILED_FROM:
		return "Detailed"
	if value >= STANDARD_FROM:
		return "Standard"
	return None


class TechnoCommercialReview(Document):
	def validate(self):
		self.fetch_from_sales_order()
		self.compute_tier()
		self.seed_checklist()
		self.compute_costing()
		self.compute_recommendation()

	def before_submit(self):
		self.require_complete_checklist()
		if not self.outcome:
			frappe.throw(
				_("Record the review outcome (final recommendation) before completing the review."),
				title=_("Outcome Missing"),
			)
		not_ok = self._not_ok_rows()
		if self.outcome == "Accept" and not_ok:
			frappe.throw(
				_(
					"{0} parameter(s) are marked Not OK, so the outcome cannot be a plain "
					"Accept. Resolve them, or choose Accept with Conditions (recording the "
					"conditions), Clarification Required, or Reject."
				).format(frappe.bold(len(not_ok))),
				title=_("Not OK Parameters Open"),
			)
		if self.outcome == "Accept with Conditions" and not (self.outcome_remarks or "").strip():
			frappe.throw(
				_("Record what the conditions are in Conditions / Remarks."),
				title=_("Conditions Missing"),
			)

	def fetch_from_sales_order(self):
		if not self.sales_order:
			if self.review_stage == "Contract Review":
				frappe.throw(
					_("A contract-stage review must be linked to the Sales Order it reviews."),
					title=_("Sales Order Missing"),
				)
			return
		so = frappe.db.get_value(
			"Sales Order",
			self.sales_order,
			("customer", "customer_name", "base_grand_total", "po_no"),
			as_dict=True,
		)
		if not so:
			return
		self.customer = self.customer or so.customer
		self.customer_name = so.customer_name
		# The company-currency total, because the slabs are rupee values and
		# export orders are priced in EUR/USD. Tracks the order while the
		# review is open, so a repriced order recomputes its tier; frozen
		# once submitted.
		self.order_value = so.base_grand_total
		if not self.enquiry_reference and so.po_no:
			self.enquiry_reference = so.po_no

	def compute_tier(self):
		"""Detailed on value or any criticality factor; Standard otherwise.
		A voluntary review of a below-slab order is Standard depth."""
		critical = any(cint(self.get(field)) for field in CRITICALITY_FIELDS)
		self.review_tier = (
			"Detailed" if critical or flt(self.order_value) >= DETAILED_FROM else "Standard"
		)

	def _parameter_sets(self):
		if self.review_tier == "Detailed":
			return (
				("technical_parameters", TECHNICAL_PARAMETERS),
				("costing_parameters", COSTING_PARAMETERS),
				("commercial_parameters", COMMERCIAL_PARAMETERS),
				("overall_parameters", OVERALL_PARAMETERS),
			)
		return (
			("technical_parameters", STANDARD_TECHNICAL),
			("costing_parameters", STANDARD_COSTING),
			("commercial_parameters", STANDARD_COMMERCIAL),
			("overall_parameters", ()),
		)

	def seed_checklist(self):
		"""Fill the parameter tables for the computed tier.

		Reseeds freely while nothing is answered (so a tier flip on a draft
		swaps the checklist); once any response exists the tables are never
		touched -- a recorded answer must not vanish because someone edited
		the order value."""
		sets = self._parameter_sets()
		expected = {field: list(params) for field, params in sets}
		current = {field: [row.parameter for row in (self.get(field) or [])] for field, _p in sets}
		seeded_subset = {f: [p for p in current[f] if p in expected[f]] for f in current}
		if all(seeded_subset[f] == expected[f] for f in expected):
			return
		answered = any(row.response for field, _p in sets for row in (self.get(field) or []))
		if answered:
			frappe.msgprint(
				_(
					"The review tier changed to {0} after responses were recorded, so the "
					"checklist was left untouched. Clear the parameter tables to load the "
					"{0} checklist."
				).format(self.review_tier)
			)
			return
		for field, params in sets:
			self.set(field, [])
			for parameter in params:
				self.append(field, {"parameter": parameter})

	def compute_costing(self):
		total = sum(flt(self.get(field)) for field in COST_FIELDS)
		self.total_estimated_cost = total
		selling = flt(self.proposed_selling_price)
		self.expected_gross_margin = selling - total if selling else 0
		self.expected_margin_pct = (self.expected_gross_margin / selling * 100) if selling else 0

	def _all_rows(self):
		return [row for field, _p in self._parameter_sets() for row in (self.get(field) or [])]

	def _not_ok_rows(self):
		return [row for row in self._all_rows() if row.response == "Not OK"]

	def compute_recommendation(self):
		"""What the answers add up to, stated next to the outcome the human
		picks. The commercial reviewer stays accountable for the decision;
		this line and the before_submit rules keep the decision honest."""
		rows = self._all_rows()
		if not rows:
			self.computed_recommendation = None
			return
		unanswered = len([row for row in rows if not row.response])
		not_ok = len(self._not_ok_rows())
		if not_ok:
			self.computed_recommendation = _("{0} Not OK — resolve, or accept only with conditions").format(not_ok)
		elif unanswered:
			self.computed_recommendation = _("{0} of {1} parameters still unanswered").format(
				unanswered, len(rows)
			)
		else:
			self.computed_recommendation = _("All parameters OK — clear to accept")

	def require_complete_checklist(self):
		unanswered = [row.parameter for row in self._all_rows() if not row.response]
		if unanswered:
			frappe.throw(
				_("Answer every review parameter (OK / Not OK / NA) before completing the review. Unanswered: {0}").format(
					frappe.bold(len(unanswered))
				),
				title=_("Checklist Incomplete"),
			)
