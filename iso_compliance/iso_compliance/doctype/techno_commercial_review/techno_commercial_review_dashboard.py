# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Connections tab: the Sales Order or Quotation this review is about."""

from frappe import _


def get_data():
	return {
		"fieldname": "techno_commercial_review",
		"internal_links": {"Sales Order": "sales_order", "Quotation": "quotation"},
		"transactions": [{"label": _("Reviewed"), "items": ["Sales Order", "Quotation"]}],
	}
