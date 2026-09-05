# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-005's supplier-approval check, run when a Purchase Order is submitted.

Warn-first by design: 943 of the site's suppliers have no approval status
yet, and hard-blocking every order on day one would stop purchasing dead.
A Suspended supplier always blocks -- suspension is a deliberate decision,
not a data gap. Flip SUPPLIER_GATE to "block" once the supplier base is
classified, and Not Approved suppliers block too.
"""

import frappe
from frappe import _

SUPPLIER_GATE = "warn"  # "block": Not Approved / unclassified suppliers also block


def check_supplier_approval(doc, method=None):
	status = frappe.db.get_value("Supplier", doc.supplier, "custom_approval_status")
	if status == "Approved":
		return
	if status == "Suspended":
		frappe.throw(
			_(
				"Supplier {0} is <b>Suspended</b> on the Approved Suppliers Register "
				"(REG-007). Orders cannot be placed until a new evaluation (FRM-005) "
				"restores approval."
			).format(frappe.bold(doc.supplier_name or doc.supplier)),
			title=_("Supplier Suspended"),
		)
	label = _(status) if status else _("not yet classified")
	message = _(
		"Supplier {0} is <b>{1}</b> on the Approved Suppliers Register (REG-007). "
		"SOP-005 expects purchases from Approved suppliers; record a Supplier "
		"Evaluation (FRM-005) to classify them."
	).format(frappe.bold(doc.supplier_name or doc.supplier), label)
	if SUPPLIER_GATE == "block":
		frappe.throw(message, title=_("Supplier Not Approved"))
	frappe.msgprint(message, title=_("Supplier Approval"), indicator="orange")
