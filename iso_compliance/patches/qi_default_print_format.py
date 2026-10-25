# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Quality Inspection prints the inspection report by default (2026-10-25).
ERPNext's own "Quality Inspection" format has no readings, drawing or numbered
boxes, so printing a new-format inspection gave the wrong document. An old-
format inspection printed with the report says to use the standard print."""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

FORMAT = "Sampling and Inspection Record (QI)"


def execute():
	if frappe.db.exists("Print Format", FORMAT):
		make_property_setter("Quality Inspection", None, "default_print_format", FORMAT, "Data",
		                     for_doctype=True, validate_fields_for_doctype=False)
