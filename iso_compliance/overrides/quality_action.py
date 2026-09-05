# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-014: a corrective action closes only after effectiveness verification.

Without this rule the requirement is words on a page; with it, marking a
Quality Action Completed demands that somebody verified the fix worked (or
explicitly found it didn't -- "No" still closes honestly, and should spawn a
fresh action).
"""

import frappe
from frappe import _
from frappe.utils import today


def enforce_effectiveness_before_closure(doc, method=None):
	if doc.status != "Completed":
		return
	if (doc.get("custom_effectiveness_verified") or "Pending") == "Pending":
		frappe.throw(
			_(
				"SOP-014: a corrective action can be Completed only after its "
				"effectiveness is verified. Set <b>Effectiveness Verified</b> to "
				"Yes (or No, with a follow-up action) first."
			),
			title=_("Effectiveness Not Verified"),
		)
	if not doc.get("custom_completion_date"):
		doc.custom_completion_date = today()
	if not doc.get("custom_verification_date"):
		doc.custom_verification_date = today()
	if not doc.get("custom_verified_by"):
		doc.custom_verified_by = frappe.session.user
