# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class DocumentRevision(Document):
	"""One immutable line of a controlled document's Change History.

	Columns follow the format specified by the SQA assessor exactly:
	Issue No. | Issue Date | Revision No. | Revision Date | Clause/Section Affected |
	Description of Change | Prepared By | Reviewed By | Approved By.

	The stamp timestamps are additional evidence and are not part of the printed
	Change History table.

	Rows are written by the parent Controlled Document on workflow transitions.
	Immutability is enforced by the parent, not here: every field is read-only in
	the UI, and the parent compares the submitted rows against what is stored
	before saving. See ControlledDocument.validate_revision_history_is_immutable.
	"""

	pass
