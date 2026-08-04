# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ControlledDocumentType(Document):
	def validate(self):
		self.abbreviation = (self.abbreviation or "").strip().upper()
		self.validate_padding()
		self.validate_prefix()

	def validate_padding(self):
		if not self.number_padding:
			self.number_padding = 3
		if not 1 <= self.number_padding <= 10:
			frappe.throw(_("Number Padding must be between 1 and 10."))

	def validate_prefix(self):
		"""A document number must be reproducible and unique per type.

		Frappe only rejects `<` and `>` in document names, so the prefix is checked
		against the naming series pattern instead, which is the narrower constraint
		that actually governs generated names.
		"""
		if not self.naming_series_prefix:
			return

		self.naming_series_prefix = self.naming_series_prefix.strip()

		if "#" in self.naming_series_prefix:
			frappe.throw(
				_("Document Number Prefix must not contain '#'. The running number is added automatically.")
			)

		from frappe.model.naming import NAMING_SERIES_PATTERN

		if not NAMING_SERIES_PATTERN.match(self.naming_series_prefix):
			frappe.throw(
				_("Document Number Prefix {0} contains characters that cannot be used in a document number.").format(
					frappe.bold(self.naming_series_prefix)
				)
			)

		duplicate = frappe.db.get_value(
			"Controlled Document Type",
			{"naming_series_prefix": self.naming_series_prefix, "name": ("!=", self.name)},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("Document Number Prefix {0} is already used by Controlled Document Type {1}.").format(
					frappe.bold(self.naming_series_prefix), frappe.bold(duplicate)
				)
			)

	def get_naming_series(self) -> str:
		"""Return the full naming series, e.g. 'HCCPL/QMS/SOP-.###'."""
		if not self.naming_series_prefix:
			frappe.throw(
				_("Controlled Document Type {0} has no Document Number Prefix, so a document number cannot be generated.").format(
					frappe.bold(self.name)
				)
			)
		return f"{self.naming_series_prefix}.{'#' * (self.number_padding or 3)}"
