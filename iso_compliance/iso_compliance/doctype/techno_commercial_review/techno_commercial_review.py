# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""FRM-036: the techno-commercial review behind every accepted order (SOP-004).

One form, filled by up to three people. Sales opens it from the Sales Order,
names a Technical, a Costing and a Commercial reviewer, and saves: each is
assigned the form (bell, email, ToDo) and given edit access to it. Anyone
assigned may fill any section; the version history shows who changed what.
Sales records the decision and submits once every check is answered.

The tier is computed, never chosen: order value and the four criticality
factors decide it, so the slab rule in SOP-004 and the rule enforced here
cannot drift apart. Sales Order submission checks this doctype through
iso_compliance.overrides.sales_order.
"""

import frappe
from frappe import _
from frappe.desk.form import assign_to
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

#: Figures a Detailed review must carry before it can be submitted; the
#: rest of the cost block is optional and the margin is computed.
REQUIRED_COST_FIELDS = ("estimated_material_cost", "proposed_selling_price")

#: section key -> (assignee field, checklist table, label)
SECTIONS = (
	("technical", "technical_assignee", "technical_parameters", "Technical"),
	("costing", "costing_assignee", "costing_parameters", "Costing"),
	("commercial", "commercial_assignee", "commercial_parameters", "Commercial"),
)

# The essential checks of a Detailed review, cut down on 2026-10-09 from the
# 39 lines of the source Techno-Commercial Review Form. Each line asks one
# question a reviewer can answer OK / Not OK / NA without a manual.
TECHNICAL_PARAMETERS = (
	"Specification and drawings are clear and complete",
	"Applicable standards and statutory requirements identified",
	"We can make it: machines, people and material available",
	"Inspection, testing and acceptance criteria agreed",
	"Delivery schedule is achievable",
)

COSTING_PARAMETERS = (
	"Material, labour and overhead costed",
	"Freight, testing, packing and taxes included",
	"Price gives an acceptable margin",
)

COMMERCIAL_PARAMETERS = (
	"Payment terms and credit risk acceptable",
	"Penalty, LD and price-variation clauses acceptable",
	"Warranty and after-sales terms acceptable",
	"No open deviations or customer clarifications",
)

# The standard-depth review: the order verified against the quotation.
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

def blank_form_rows():
	"""The paper FRM-036 prints the Detailed checks, so it can be filled by hand."""
	return {
		"technical_parameters": TECHNICAL_PARAMETERS,
		"costing_parameters": COSTING_PARAMETERS,
		"commercial_parameters": COMMERCIAL_PARAMETERS,
	}


PASSING_OUTCOMES = ("Accept", "Accept with Conditions")


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
		self.require_cost_figures()
		if not self.outcome:
			frappe.throw(
				_("Record the decision before completing the review."),
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
			)
		return (
			("technical_parameters", STANDARD_TECHNICAL),
			("costing_parameters", STANDARD_COSTING),
			("commercial_parameters", STANDARD_COMMERCIAL),
		)

	def seed_checklist(self):
		"""Fill the parameter tables for the computed tier.

		Seeds an empty form, and reseeds when the tier flips while nothing is
		answered. Otherwise the tables are left alone -- a recorded answer
		must not vanish because someone edited the order value, and a review
		raised on the longer pre-2026-10 checklist keeps the rows it has."""
		sets = self._parameter_sets()
		has_rows = any(self.get(field) for field, _p in sets)
		before = self.get_doc_before_save()
		tier_changed = bool(before and before.review_tier != self.review_tier)
		if has_rows and not tier_changed:
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
		picks. Sales stays accountable for the decision; this line and the
		before_submit rules keep the decision honest."""
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

	def require_cost_figures(self):
		if self.review_tier != "Detailed":
			return
		missing = [
			_(self.meta.get_label(field)) for field in REQUIRED_COST_FIELDS if not flt(self.get(field))
		]
		if missing:
			frappe.throw(
				_("A Detailed review needs these figures under Costing: {0}").format(
					frappe.bold(", ".join(missing))
				),
				title=_("Cost Figures Missing"),
			)

	def progress(self):
		"""What is filled and what is left, per section, for the progress bar
		on the form and for the Sales Order gate's message."""
		sections = []
		for key, assignee_field, table, label in SECTIONS:
			rows = self.get(table) or []
			done = len([row for row in rows if row.response])
			total = len(rows)
			if key == "costing" and self.review_tier == "Detailed":
				total += len(REQUIRED_COST_FIELDS)
				done += len([f for f in REQUIRED_COST_FIELDS if flt(self.get(f))])
			sections.append(
				{
					"key": key,
					"label": _(label),
					"assignee": self.get(assignee_field),
					"done": done,
					"total": total,
				}
			)
		sections.append(
			{
				"key": "outcome",
				"label": _("Decision"),
				"assignee": self.owner,
				"done": 1 if self.outcome else 0,
				"total": 1,
			}
		)
		return {
			"sections": sections,
			"done": sum(s["done"] for s in sections),
			"total": sum(s["total"] for s in sections),
		}

	def on_update(self):
		self.sync_assignments()
		self.close_finished_assignments()

	def on_submit(self):
		for user in self._assignees():
			_close_assignment(self, user)

	def on_cancel(self):
		for user in self._assignees():
			_close_assignment(self, user)

	def _assignees(self):
		return {self.get(field) for _k, field, _t, _l in SECTIONS if self.get(field)}

	def sync_assignments(self):
		"""Assign the form to each named reviewer and let them edit it.

		Assignment is ERPNext's own (ToDo + bell + email), so it shows in the
		reviewer's to-do list like any other work. A reviewer replaced on the
		form has their open assignment cancelled. Sharing with write is what
		lets someone without a sales role fill their section."""
		before = self.get_doc_before_save()
		previous = set()
		if before:
			previous = {before.get(field) for _k, field, _t, _l in SECTIONS if before.get(field)}
		current = self._assignees()

		for user in previous - current:
			_close_assignment(self, user, status="Cancelled")

		for user in current:
			sections = [
				_(label) for _k, field, _t, label in SECTIONS if self.get(field) == user
			]
			frappe.share.add_docshare(
				self.doctype, self.name, user, read=1, write=1, flags={"ignore_share_permission": True}
			)
			if _open_assignment(self, user):
				continue
			assign_to._add(
				{
					"assign_to": [user],
					"doctype": self.doctype,
					"name": self.name,
					"description": _("Complete the {0} section of review {1} for order {2} ({3}).").format(
						", ".join(sections), self.name, self.sales_order or "-", self.customer_name or ""
					),
				},
				ignore_permissions=True,
			)

	def close_finished_assignments(self):
		"""Close a reviewer's to-do once every section they hold is answered,
		and tell whoever raised the review when the checks are all done."""
		progress = {s["key"]: s for s in self.progress()["sections"]}
		for user in self._assignees():
			keys = [key for key, field, _t, _l in SECTIONS if self.get(field) == user]
			if all(progress[k]["done"] >= progress[k]["total"] for k in keys):
				_close_assignment(self, user)

		before = self.get_doc_before_save()
		if (
			before
			and not self.outcome
			and self.owner != frappe.session.user
			and _checks_done(self)
			and not _checks_done(before)
		):
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": self.owner,
					"type": "Alert",
					"document_type": self.doctype,
					"document_name": self.name,
					"subject": _("Review {0}: every section is done. Record the decision.").format(
						self.name
					),
				}
			).insert(ignore_permissions=True)


def _checks_done(doc):
	return all(s["done"] >= s["total"] for s in doc.progress()["sections"] if s["key"] != "outcome")


def _open_assignment(doc, user):
	return frappe.db.get_value(
		"ToDo",
		{
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"allocated_to": user,
			"status": "Open",
		},
		"name",
	)


def _close_assignment(doc, user, status="Closed"):
	todo = _open_assignment(doc, user)
	if todo:
		assign_to.set_status(doc.doctype, doc.name, todo=todo, status=status, ignore_permissions=True)


@frappe.whitelist()
def get_progress(review: str):
	doc = frappe.get_doc("Techno Commercial Review", review)
	doc.check_permission("read")
	return doc.progress()
