# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""FRM-005: the supplier evaluation behind every approval on REG-007 (SOP-005).

The nine weighted criteria come from the Supplier Evaluation Form source file.
The two criteria the system can measure -- quality of supply and on-time
delivery -- are pre-rated from the last twelve months of Purchase Receipts, so
the evaluator judges only what genuinely needs judgment. Submitting the
evaluation writes the decision onto the Supplier record: the evaluation is the
evidence, the master carries the state, and REG-007 reads the master.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, cint, flt, today

#: Criteria and weights, verbatim from the Supplier Evaluation Form (F-PUR-01).
#: The first two are pre-rated from receipt data.
CRITERIA = (
	("Quality of supplied product / service", 25),
	("On-time delivery / service", 20),
	("Technical capability", 15),
	("Price / commercial competitiveness", 10),
	("Capacity / resource availability", 10),
	("Statutory / regulatory compliance", 5),
	("Management system / certifications", 5),
	("Communication & responsiveness", 5),
	("Corrective action effectiveness", 5),
)

QUALITY_CRITERION = CRITERIA[0][0]
DELIVERY_CRITERION = CRITERIA[1][0]

#: Percentage-to-rating bands for the computed criteria.
RATING_BANDS = ((95, "5"), (90, "4"), (80, "3"), (60, "2"), (0, "1"))

def _pct_to_rating(pct):
	for floor, rating in RATING_BANDS:
		if flt(pct) >= floor:
			return rating
	return "1"


class SupplierEvaluation(Document):
	def validate(self):
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

	def seed_criteria(self):
		if self.criteria:
			return
		for criterion, weight in CRITERIA:
			self.append("criteria", {"criterion": criterion, "weight": weight})

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
			if row.criterion == QUALITY_CRITERION and self.acceptance_pct is not None:
				row.rating = _pct_to_rating(self.acceptance_pct)
				if not row.remarks:
					row.remarks = _("auto: {0}% accepted, last 12 months").format(
						round(flt(self.acceptance_pct), 1)
					)
			elif row.criterion == DELIVERY_CRITERION and self.on_time_delivery_pct is not None:
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

	def default_next_review(self):
		if self.next_review_date:
			return
		months = 12 if self.category == "Critical" else 24
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
