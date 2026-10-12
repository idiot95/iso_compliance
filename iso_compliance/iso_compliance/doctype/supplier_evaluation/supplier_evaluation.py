# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""FRM-005: the supplier evaluation behind every approval on REG-007 (SOP-005).

The criteria come from the Supplier Evaluation Template of the supplier's
category -- Critical or Non-Critical -- which Quality maintains. Criteria the
system can measure (acceptance and on-time delivery) are pre-rated from the
last twelve months of Purchase Receipts, so the evaluator judges only what
genuinely needs judgment. The template also sets the re-evaluation interval,
so the next review date fills itself. Submitting writes the decision onto the
Supplier record: the evaluation is the evidence, the master carries the
state, and REG-007 reads the master.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, cint, flt, today

ACCEPTANCE = "Acceptance % from receipts"
ON_TIME = "On-time % from receipts"

#: Before templates were records, the two data-backed criteria were known by
#: name; evaluations from then still carry these rows without auto_rate.
LEGACY_AUTO = {
	"Quality of supplied product / service": ACCEPTANCE,
	"On-time delivery / service": ON_TIME,
}

#: Score-to-decision suggestion shown beside the evaluator's own choice.
DECISION_BANDS = ((80, "Approved"), (60, "Provisional"), (0, "Not Approved"))

#: Percentage-to-rating bands for the computed criteria.
RATING_BANDS = ((95, "5"), (90, "4"), (80, "3"), (60, "2"), (0, "1"))


def _pct_to_rating(pct):
	for floor, rating in RATING_BANDS:
		if flt(pct) >= floor:
			return rating
	return "1"


class SupplierEvaluation(Document):
	def validate(self):
		self.default_category()
		self.seed_criteria()
		self.compute_metrics()
		self.suggest_ratings()
		self.compute_score()
		self.default_next_review()

	def before_submit(self):
		if not self.approval_status:
			frappe.throw(
				_("Record the evaluation decision (approval status) before submitting."),
				title=_("Decision Missing"),
			)
		unrated = [row.criterion for row in self.criteria if not row.rating]
		if unrated:
			frappe.throw(
				_("Rate every criterion (1-5) before submitting. Unrated: {0}").format(
					frappe.bold(len(unrated))
				),
				title=_("Evaluation Incomplete"),
			)

	def on_submit(self):
		self.write_to_supplier()

	def default_category(self):
		if not self.category and self.supplier:
			self.category = frappe.db.get_value("Supplier", self.supplier, "custom_category")
		if not self.category:
			frappe.throw(_("Choose the supplier category (Critical or Non-Critical)."), title=_("Category Missing"))

	def _template(self):
		if not frappe.db.exists("Supplier Evaluation Template", self.category):
			frappe.throw(
				_("No Supplier Evaluation Template exists for {0} suppliers. Quality must create one first.").format(
					frappe.bold(_(self.category))
				),
				title=_("Template Missing"),
			)
		return frappe.get_cached_doc("Supplier Evaluation Template", self.category)

	def seed_criteria(self):
		"""Load the criteria of the category's template. On a draft, a change
		of category swaps templates; recorded ratings for the old template do
		not carry over, and the pre-rated rows recompute. A submitted
		evaluation keeps the criteria it was scored on."""
		if self.docstatus != 0:
			return
		template = self._template()
		self.template = template.name
		current = [(row.criterion, flt(row.weight)) for row in self.criteria]
		expected = [(row.criterion, flt(row.weight)) for row in template.criteria]
		if current == expected:
			return
		if current and any(row.rating for row in self.criteria):
			frappe.msgprint(
				_("Criteria reloaded from the {0} template; check the ratings again.").format(_(self.category))
			)
		self.set("criteria", [])
		for row in template.criteria:
			self.append(
				"criteria", {"criterion": row.criterion, "weight": row.weight, "auto_rate": row.auto_rate}
			)

	def compute_metrics(self):
		"""Acceptance and on-time percentages from the last 12 months of
		submitted Purchase Receipts. Absent data leaves the fields empty and
		the matching criteria to human judgment."""
		self.on_time_delivery_pct = None
		self.acceptance_pct = None
		self.metrics_basis = None
		if not self.supplier or self.docstatus != 0:
			return
		rows = frappe.db.sql(
			"""
			select pri.qty, pri.received_qty, pri.rejected_qty,
				pr.posting_date, po_item.schedule_date
			from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			left join `tabPurchase Order Item` po_item on po_item.name = pri.purchase_order_item
			where pr.docstatus = 1 and pr.supplier = %s and pr.posting_date >= %s
			""",
			(self.supplier, add_days(today(), -365)),
			as_dict=True,
		)
		if not rows:
			self.metrics_basis = _("No submitted Purchase Receipts in the last 12 months")
			return
		received = sum(flt(r.received_qty) or flt(r.qty) for r in rows)
		rejected = sum(flt(r.rejected_qty) for r in rows)
		if received:
			self.acceptance_pct = (received - rejected) / received * 100
		scheduled = [r for r in rows if r.schedule_date]
		if scheduled:
			on_time = len([r for r in scheduled if r.posting_date <= r.schedule_date])
			self.on_time_delivery_pct = on_time / len(scheduled) * 100
		self.metrics_basis = _("{0} receipt lines, last 12 months").format(len(rows))

	def suggest_ratings(self):
		"""Pre-rate the two data-backed criteria from the computed metrics.
		Only empty ratings are filled; an evaluator's override stands."""
		for row in self.criteria:
			if row.rating:
				continue
			source = row.auto_rate or LEGACY_AUTO.get(row.criterion)
			if source == ACCEPTANCE and self.acceptance_pct is not None:
				row.rating = _pct_to_rating(self.acceptance_pct)
				if not row.remarks:
					row.remarks = _("auto: {0}% accepted, last 12 months").format(
						round(flt(self.acceptance_pct), 1)
					)
			elif source == ON_TIME and self.on_time_delivery_pct is not None:
				row.rating = _pct_to_rating(self.on_time_delivery_pct)
				if not row.remarks:
					row.remarks = _("auto: {0}% on time, last 12 months").format(
						round(flt(self.on_time_delivery_pct), 1)
					)

	def compute_score(self):
		total = 0.0
		for row in self.criteria:
			row.weighted_score = flt(row.weight) * cint(row.rating) / 5 if row.rating else 0
			total += row.weighted_score
		self.overall_score = total
		self.recommended_status = None
		if self.criteria and all(row.rating for row in self.criteria):
			self.recommended_status = next(status for floor, status in DECISION_BANDS if total >= floor)

	def default_next_review(self):
		"""Always the evaluation date plus the template's interval, so the date
		on the form is the one the supplier will carry."""
		if self.docstatus != 0:
			return
		months = cint(frappe.db.get_value("Supplier Evaluation Template", self.category, "review_months")) or 12
		self.next_review_date = add_months(self.evaluation_date or today(), months)

	def write_to_supplier(self):
		"""The submitted decision becomes the supplier's state. db.set_value,
		because the evaluator's authority over the evaluation is the approval;
		they need no write permission on the Supplier master itself."""
		updates = {
			"custom_approval_status": self.approval_status,
			"custom_score": self.overall_score,
			"custom_rating": flt(self.overall_score) / 100,
			"custom_approved_on": today(),
			"custom_approved_by": frappe.session.user,
			"custom_reapproval_due": self.next_review_date,
		}
		if self.category:
			updates["custom_category"] = self.category
		frappe.db.set_value("Supplier", self.supplier, updates)
