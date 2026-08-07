# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class InternalAudit(Document):
	def validate(self):
		# The audit register's "No. of NCs" column. Counted, never typed, so the
		# register cannot disagree with the findings it summarises.
		self.nc_count = len(
			[f for f in self.findings or [] if "Nonconformity" in (f.finding_type or "")]
		)
