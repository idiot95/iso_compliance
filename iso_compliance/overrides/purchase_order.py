# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-005's supplier-approval lock, run when a Purchase Order is submitted.

Only an Approved supplier can be ordered from. An urgent order to anyone
else needs an override: the order is ticked, a reason is written, and a
Purchase Manager or Quality Manager submits it -- their name is stamped on
the order and the reason goes on its timeline, so every exception is
evidence rather than a quiet workaround. A Suspended supplier is never
overridden: suspension is a deliberate decision, reversed only by a new
evaluation (FRM-005).
"""

import frappe
from frappe import _

#: Who may submit an order to a supplier that is not Approved.
OVERRIDE_ROLES = ("Purchase Manager", "Quality Manager", "System Manager")


def check_supplier_approval(doc, method=None):
	status = frappe.db.get_value("Supplier", doc.supplier, "custom_approval_status")
	supplier = frappe.bold(doc.supplier_name or doc.supplier)
	if status == "Approved":
		return

	if status == "Suspended":
		frappe.throw(
			_(
				"Supplier {0} is <b>Suspended</b> on the Approved Suppliers Register "
				"(REG-007). No order can be placed, override or not, until a new "
				"evaluation (FRM-005) restores approval."
			).format(supplier),
			title=_("Supplier Suspended"),
		)

	label = _(status) if status else _("not yet evaluated")
	if not doc.get("custom_supplier_override"):
		frappe.throw(
			_(
				"Supplier {0} is <b>{1}</b>, not Approved, on the Approved Suppliers "
				"Register (REG-007). Record a Supplier Evaluation (FRM-005) to approve them. "
				"For an urgent order, tick <b>Override supplier approval</b>, write the "
				"reason, and have a Purchase Manager or Quality Manager submit it."
			).format(supplier, label),
			title=_("Supplier Not Approved"),
		)

	if not set(OVERRIDE_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only a Purchase Manager or Quality Manager can submit an order with the supplier approval overridden."),
			title=_("Override Not Permitted"),
		)
	reason = (doc.get("custom_supplier_override_reason") or "").strip()
	if not reason:
		frappe.throw(_("Write the reason for the override."), title=_("Override Reason Missing"))

	doc.custom_supplier_override_by = frappe.session.user
	doc.add_comment(
		"Comment",
		_("Supplier approval overridden ({0} supplier): {1}").format(label, reason),
	)
