# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""EN 10204 type 2.1 is printed as the Certificate of Conformity (2026-10-25),
so the separate "Declaration of Compliance 2.1" is switched off. Frappe keeps a
print format's disabled flag when it loads the file, hence a patch."""

import frappe


def execute():
	if frappe.db.exists("Print Format", "Declaration of Compliance 2.1"):
		frappe.db.set_value("Print Format", "Declaration of Compliance 2.1", "disabled", 1)
