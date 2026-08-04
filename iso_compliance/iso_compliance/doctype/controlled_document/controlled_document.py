# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import now_datetime

#: Fields of a Document Revision row that constitute the audit record. Once a row
#: exists, none of these may change.
REVISION_EVIDENCE_FIELDS = (
	"issue_number",
	"issue_date",
	"revision_number",
	"revision_date",
	"clause_section_affected",
	"description_of_change",
	"prepared_by",
	"prepared_on",
	"reviewed_by",
	"reviewed_on",
	"approved_by",
	"approved_on",
)


class ControlledDocument(Document):
	def autoname(self):
		"""Name the document from its type's configured prefix.

		The numbering convention lives on Controlled Document Type, so changing it
		is a data change rather than a schema change.

		Migrated documents must keep the numbers they were issued under, including
		any gaps in the historical sequence, because those numbers are cited by
		documents already in circulation. To preserve an explicit name, the caller
		sets ``frappe.flags.in_import``: naming.set_new_name only leaves a supplied
		name in place under that flag, and this method is then never reached.

		Note that the same flag also skips ``_set_defaults``, so an importing
		caller must supply issue_number and revision_number itself.
		"""
		doc_type = frappe.get_cached_doc("Controlled Document Type", self.document_type)
		self.name = make_autoname(doc_type.get_naming_series(), doc=self)

	def validate(self):
		self.normalise_control_numbers()
		self.validate_segregation_of_duty()
		self.validate_revision_history_is_immutable()

	def before_submit(self):
		self.stamp_review_and_approval()
		self.validate_segregation_of_duty()

	# ------------------------------------------------------------------
	# Control block
	# ------------------------------------------------------------------

	def normalise_control_numbers(self):
		"""Issue and revision numbers are zero-padded strings, not integers.

		"Rev 00" is a meaningful value on a controlled document and must survive a
		round trip through the database and onto the printed header unchanged.
		"""
		self.issue_number = pad_control_number(self.issue_number, _("Issue No."))
		self.revision_number = pad_control_number(self.revision_number, _("Revision No."))

	# ------------------------------------------------------------------
	# Authority
	# ------------------------------------------------------------------

	def validate_segregation_of_duty(self):
		"""The approver may also be the reviewer, but never the preparer.

		This is the rule that makes the Prepared/Reviewed/Approved stamps evidence
		of independent approval rather than three copies of one signature.
		"""
		if not (self.prepared_by and self.approved_by):
			return

		if self.approved_by == self.prepared_by:
			frappe.throw(
				_(
					"{0} cannot approve a document they prepared. Approval must be recorded by a "
					"different user so that review and approval are independently evidenced."
				).format(frappe.bold(self.prepared_by_name or self.prepared_by)),
				title=_("Segregation of Duty"),
			)

	def stamp_prepared(self, user: str | None = None):
		"""Record authorship. Called when the author routes the document for review."""
		user = user or frappe.session.user
		self.prepared_by = user
		self.prepared_by_name = frappe.db.get_value("User", user, "full_name")
		self.prepared_on = now_datetime()

	def stamp_review_and_approval(self, user: str | None = None):
		"""Record review and approval.

		Today one person performs both. The fields are kept separate so that
		splitting them into two people later is a workflow change, not a schema
		change.
		"""
		user = user or frappe.session.user
		full_name = frappe.db.get_value("User", user, "full_name")

		if not self.reviewed_by:
			self.reviewed_by = user
			self.reviewed_by_name = full_name
			self.reviewed_on = now_datetime()

		if not self.approved_by:
			self.approved_by = user
			self.approved_by_name = full_name
			self.approved_on = now_datetime()

	# ------------------------------------------------------------------
	# Change history
	# ------------------------------------------------------------------

	def validate_revision_history_is_immutable(self):
		"""Existing Change History rows may not be edited, reordered or removed.

		The assessor's finding was that no revision history was maintained. A
		history that can be rewritten after the fact would not answer it, so rows
		are append-only: the only permitted change is a new row at the end.
		"""
		previous = self.get_doc_before_save()
		if not previous:
			return

		old_rows = {row.name: row for row in previous.get("revisions", [])}
		new_rows = {row.name: row for row in self.get("revisions", []) if row.name}

		removed = set(old_rows) - set(new_rows)
		if removed:
			frappe.throw(
				_("Change History rows cannot be deleted. Attempted to remove {0} row(s).").format(len(removed)),
				title=_("Immutable Revision History"),
			)

		for row_name, old_row in old_rows.items():
			new_row = new_rows[row_name]
			for fieldname in REVISION_EVIDENCE_FIELDS:
				if old_row.get(fieldname) != new_row.get(fieldname):
					frappe.throw(
						_("Change History row {0} cannot be modified. {1} was changed from {2} to {3}.").format(
							old_row.idx,
							frappe.bold(_(fieldname.replace("_", " ").title())),
							frappe.bold(old_row.get(fieldname) or _("empty")),
							frappe.bold(new_row.get(fieldname) or _("empty")),
						),
						title=_("Immutable Revision History"),
					)

			if old_row.idx != new_row.idx:
				frappe.throw(
					_("Change History rows cannot be reordered. Row {0} moved to position {1}.").format(
						old_row.idx, new_row.idx
					),
					title=_("Immutable Revision History"),
				)

	# ------------------------------------------------------------------
	# Live register content
	# ------------------------------------------------------------------

	def get_register_rows(self, limit: int = 200) -> dict:
		"""Return the live ERPNext rows this document is a controlled cover for.

		A Form or Register declares the DocType it is filled in through, so the
		printed register is the current data rather than a transcription of it.
		Ordering is explicit: v16 lists default to `creation`, which is not a
		defensible order for an evidentiary record.
		"""
		if not self.mapped_doctype:
			return {"columns": [], "rows": [], "total": 0}

		if not frappe.db.exists("DocType", self.mapped_doctype):
			return {"columns": [], "rows": [], "total": 0, "error": _("Mapped DocType no longer exists.")}

		if not frappe.has_permission(self.mapped_doctype, "read"):
			return {"columns": [], "rows": [], "total": 0, "error": _("Not permitted to read the mapped DocType.")}

		meta = frappe.get_meta(self.mapped_doctype)
		skip = {"Section Break", "Column Break", "Tab Break", "Table", "HTML", "Button", "Attach", "Text Editor"}
		columns = [{"fieldname": "name", "label": _("ID")}]
		for field in meta.fields:
			if len(columns) >= 7:
				break
			if field.in_list_view and field.fieldtype not in skip:
				columns.append({"fieldname": field.fieldname, "label": _(field.label or field.fieldname)})

		filters = {}
		if self.mapped_filters:
			try:
				filters = json.loads(self.mapped_filters)
			except ValueError:
				return {"columns": [], "rows": [], "total": 0, "error": _("Mapped Filters is not valid JSON.")}

		total = frappe.db.count(self.mapped_doctype, filters)
		rows = frappe.get_all(
			self.mapped_doctype,
			filters=filters,
			fields=[c["fieldname"] for c in columns],
			order_by="creation asc",
			limit_page_length=limit,
		)
		return {"columns": columns, "rows": rows, "total": total, "shown": len(rows), "limit": limit}

	def append_revision(self, description_of_change: str, clause_section_affected: str | None = None):
		"""Freeze the current control block and authority stamps as a history row."""
		self.append(
			"revisions",
			{
				"issue_number": self.issue_number,
				"issue_date": self.issue_date,
				"revision_number": self.revision_number,
				"revision_date": self.revision_date,
				"clause_section_affected": clause_section_affected or self.clause_reference,
				"description_of_change": description_of_change,
				"prepared_by": self.prepared_by,
				"prepared_by_name": self.prepared_by_name,
				"prepared_on": self.prepared_on,
				"reviewed_by": self.reviewed_by,
				"reviewed_by_name": self.reviewed_by_name,
				"reviewed_on": self.reviewed_on,
				"approved_by": self.approved_by,
				"approved_by_name": self.approved_by_name,
				"approved_on": self.approved_on,
			},
		)


def pad_control_number(value, label: str) -> str:
	"""Return a two-digit zero-padded control number, e.g. '0' -> '00', '1' -> '01'."""
	value = (str(value) if value is not None else "").strip()
	if not value:
		frappe.throw(_("{0} is required.").format(label))

	if not value.isdigit():
		# Non-numeric editions such as 'A' are left untouched rather than mangled.
		return value

	return value.zfill(2)
