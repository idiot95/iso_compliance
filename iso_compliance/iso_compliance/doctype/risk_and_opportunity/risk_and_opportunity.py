# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint

#: Score bands from the assessment methodology's Scoring sheet. Same numeric
#: bands for both kinds; the labels differ because a 20 is a threat on one
#: side and a windfall on the other.
RISK_BANDS = ((5, "Low"), (10, "Medium"), (15, "High"), (25, "Very High"))
OPPORTUNITY_BANDS = ((5, "Low"), (10, "Moderate"), (15, "High"), (25, "Excellent"))


class RiskandOpportunity(Document):
	def validate(self):
		self.compute_score()

	def compute_score(self):
		"""Score is arithmetic, never typed: Severity × Probability for a risk,
		Benefit × Probability for an opportunity, with the priority read off the
		methodology's bands. The source spreadsheets carried seven rows where a
		hand-typed score disagreed with its own factors -- this is why."""
		base = cint(self.severity) if self.entry_type == "Risk" else cint(self.benefit)
		probability = cint(self.probability)
		if not (base and probability):
			self.score = 0
			self.priority = None
			return
		self.score = base * probability
		bands = RISK_BANDS if self.entry_type == "Risk" else OPPORTUNITY_BANDS
		self.priority = next(label for limit, label in bands if self.score <= limit)
