# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The criteria an FRM-005 supplier evaluation is scored on, one template
per supplier category (SOP-005). Quality owns them: criteria, weights and
the re-evaluation interval change here, not in code."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SupplierEvaluationTemplate(Document):
	def validate(self):
		self.total_weight = sum(flt(row.weight) for row in self.criteria)
		if abs(self.total_weight - 100) > 0.01:
			frappe.throw(
				_("The weights add up to {0}%. They must add up to 100%.").format(flt(self.total_weight, 2)),
				title=_("Weights Don't Add Up"),
			)
		for kind in ("Acceptance % from receipts", "On-time % from receipts"):
			if len([row for row in self.criteria if row.auto_rate == kind]) > 1:
				frappe.throw(_("Only one criterion can be pre-rated from {0}.").format(_(kind)))
		if self.review_months < 1:
			frappe.throw(_("Re-evaluate every: enter at least 1 month."))
