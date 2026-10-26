# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The certificates the Shipment email attaches are the "(QI)" formats'
twins. No site needed:

    python -m unittest iso_compliance.qi.test_print_formats

The email (hcc_erp_edits, OVERLAPS.md #12) prints the Delivery Note formats
named in certificate_readiness. Each must draw the same certificate, from the
same builder, as the Quality Inspection format of the same EN 10204 type, so a
customer gets what Quality printed from the inspection.
"""

import ast
import json
import re
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
FORMATS = APP / "iso_compliance" / "print_format"
MACRO = '{%- from "iso_compliance/templates/includes/en10204.html" import styles, certificate -%}'


def _constants():
	"""The format names certificates.py hands the email, read without Frappe."""
	tree = ast.parse((APP / "qi" / "certificates.py").read_text())
	return {
		t.id: node.value.value
		for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
		for t in node.targets if isinstance(t, ast.Name) and t.id.endswith("_FORMAT")
	}


def _formats():
	out = {}
	for f in FORMATS.glob("*/*.json"):
		d = json.loads(f.read_text())
		out[d["name"]] = d
	return out


class TestEmailedCertificates(unittest.TestCase):
	# EN 10204 type -> the constant certificate_readiness gives the email for it
	EMAILED = {"2.1": "COC_FORMAT", "2.2": "TEST_REPORT_FORMAT", "3.1": "MTC_FORMAT"}

	def setUp(self):
		self.names, self.formats = _constants(), _formats()

	def test_same_certificate_as_the_qi_format(self):
		for doc_type, const in self.EMAILED.items():
			name = self.names[const]
			dn, qi = self.formats.get(name), self.formats.get(f"{name} (QI)")
			with self.subTest(doc_type=doc_type, format=name):
				self.assertIsNotNone(dn, f"{name} is not shipped")
				self.assertIsNotNone(qi, f"{name} (QI) is not shipped")
				self.assertEqual((dn["doc_type"], qi["doc_type"]), ("Delivery Note", "Quality Inspection"))
				self.assertEqual((dn["disabled"], qi["disabled"]), (0, 0))
				for d in (dn, qi):
					self.assertTrue(d["html"].startswith(MACRO), f"{d['name']} does not use en10204.html")
					self.assertEqual(d["pdf_generator"], "chrome", f"{d['name']} renders with another PDF engine")
				self.assertIn(f'{{{{ certificate(en10204(doc, "{doc_type}")) }}}}', dn["html"])
				self.assertIn(f'{{{{ certificate(qi_en10204(doc.name, "{doc_type}")) }}}}', qi["html"])

	def test_qi_format_prints_the_delivery_notes_certificate(self):
		"""qi_en10204 hands a connected inspection to en10204 -- the email's builder."""
		src = (APP / "qi" / "certificates.py").read_text()
		body = re.search(r"\ndef qi_en10204\(.*?(?=\n\ndef |\Z)", src, re.S).group(0)
		self.assertIn("return en10204(dn, doc_type,", body)

	def test_no_retired_format_is_emailed(self):
		for const, name in self.names.items():
			with self.subTest(const=const):
				self.assertNotEqual(name, "Declaration of Compliance 2.1")
				self.assertEqual(self.formats[name]["disabled"], 0, f"{name} is disabled but still emailed")


if __name__ == "__main__":
	unittest.main()
