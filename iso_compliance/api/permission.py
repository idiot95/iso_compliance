# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def has_app_permission():
	"""Whether to show ISO Compliance on the desk apps screen.

	Anyone who can read a controlled document has a reason to open the dashboard;
	it is where they find what is outstanding.
	"""
	if frappe.session.user == "Administrator":
		return True
	return bool(frappe.has_permission("Controlled Document", "read"))
