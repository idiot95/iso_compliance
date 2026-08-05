# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class DocumentChangeRequest(Document):
	"""The gate in front of every change to a controlled document.

	A revision must originate from a request that was reviewed, not from someone
	editing a file. Controlled Document enforces the other half: an Approved or
	Active document refuses content changes unless a submitted request raised
	against it is set in its Change Request field, and the request is consumed
	when the revision number moves.
	"""

	def before_insert(self):
		self.requested_by = frappe.session.user
		self.requested_by_name = frappe.db.get_value("User", self.requested_by, "full_name")
		self.status = "Draft"

	def before_submit(self):
		"""Submitting is approving. The same segregation rule as the documents
		themselves: the person who asked for the change cannot approve it."""
		user = frappe.session.user
		if user == self.requested_by:
			frappe.throw(
				_(
					"{0} cannot approve a change they requested. A different user must submit "
					"this request so that review and approval are independently evidenced."
				).format(frappe.bold(self.requested_by_name or self.requested_by)),
				title=_("Segregation of Duty"),
			)
		stamp = now_datetime()
		self.reviewed_by = user
		self.reviewed_on = stamp
		self.approved_by = user
		self.approved_on = stamp
		self.status = "Approved"

	def on_cancel(self):
		self.db_set("status", "Rejected", update_modified=False)
