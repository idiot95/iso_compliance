"""The techno-commercial review gate on Quotation and Sales Order (overrides/sales_order.py).

Plain unittest with the database mocked:
    cd sites && ../env/bin/python -m unittest iso_compliance.overrides.test_review_gate
"""

import unittest
from unittest import mock

import frappe

from iso_compliance.overrides import sales_order as gate


class Stop(Exception):
	pass


def review(docstatus=1, tier="Standard", outcome="Accept", name="TCR-1"):
	return frappe._dict(name=name, docstatus=docstatus, review_tier=tier, outcome=outcome)


def order(value, quotation=None, amended_from=None):
	return frappe._dict(
		name="SO-1", base_grand_total=value, company="HCC", amended_from=amended_from,
		items=[frappe._dict(prevdoc_docname=quotation)],
	)


class TestReviewGate(unittest.TestCase):
	def run_gate(self, fn, doc, reviews):
		get_all = mock.Mock(return_value=reviews)
		with mock.patch.object(gate.frappe, "get_all", get_all), \
				mock.patch.object(gate.frappe, "throw", side_effect=Stop), \
				mock.patch.object(gate.frappe, "get_cached_value", return_value="INR"), \
				mock.patch.object(gate.frappe.utils, "get_link_to_form", lambda dt, n: n, create=True), \
				mock.patch.object(gate, "_progress_text", lambda name: "1 of 7 done"), \
				mock.patch.object(gate, "fmt_money", lambda v, currency=None: str(v)):
			fn(doc)
		return get_all.call_args.kwargs["or_filters"]

	def test_quotation_in_the_slabs_needs_a_review(self):
		doc = frappe._dict(name="QTN-1", base_grand_total=600000, company="HCC")
		with self.assertRaises(Stop):
			self.run_gate(gate.enforce_quotation_review, doc, [])

	def test_quotation_with_an_approved_review_submits(self):
		doc = frappe._dict(name="QTN-1", base_grand_total=600000, company="HCC")
		filters = self.run_gate(gate.enforce_quotation_review, doc, [review()])
		self.assertEqual(filters, {"quotation": ("in", ["QTN-1"])})

	def test_quotation_below_the_slabs_submits_without_one(self):
		doc = frappe._dict(name="QTN-1", base_grand_total=100000, company="HCC")
		self.run_gate(gate.enforce_quotation_review, doc, [])

	def test_rejected_or_open_review_blocks_a_quotation(self):
		doc = frappe._dict(name="QTN-1", base_grand_total=100000, company="HCC")
		for reviews in ([review(outcome="Reject")], [review(docstatus=0, outcome=None)]):
			with self.assertRaises(Stop):
				self.run_gate(gate.enforce_quotation_review, doc, reviews)

	def test_order_looks_at_its_quotations_review_too(self):
		filters = self.run_gate(gate.enforce_techno_commercial_review, order(600000, "QTN-1"), [review()])
		self.assertEqual(filters, {"sales_order": ("in", ["SO-1"]), "quotation": ("in", ["QTN-1"])})

	def test_order_without_a_quotation_still_needs_its_own_review(self):
		with self.assertRaises(Stop):
			filters = self.run_gate(gate.enforce_techno_commercial_review, order(600000), [])
			self.assertNotIn("quotation", filters)

	def test_quotation_review_of_a_lower_tier_does_not_cover_a_bigger_order(self):
		with self.assertRaises(Stop):
			self.run_gate(gate.enforce_techno_commercial_review, order(1200000, "QTN-1"), [review(tier="Standard")])
		self.run_gate(gate.enforce_techno_commercial_review, order(1200000, "QTN-1"), [review(tier="Detailed")])
