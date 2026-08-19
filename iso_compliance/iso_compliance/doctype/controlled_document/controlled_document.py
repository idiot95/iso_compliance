# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, now_datetime, nowdate

#: Fields of a Document Revision row that constitute the audit record. Once a row
#: exists, none of these may change.
#: States in which a document's content is under change control. Draft and
#: Under Review documents are still being authored and edit freely.
GUARDED_STATES = ("Approved", "Active", "Superseded", "Obsolete")

#: Fields the system writes itself, or that record the change process rather
#: than the document's content. Everything else changing on a guarded document
#: requires an approved Document Change Request.
UNCONTROLLED_FIELDS = {
	"workflow_state", "change_request", "seed_batch", "revisions",
	"prepared_by", "prepared_by_name", "prepared_on",
	"reviewed_by", "reviewed_by_name", "reviewed_on",
	"approved_by", "approved_by_name", "approved_on",
	"next_review_date", "superseded_by", "body_mode",
}

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
		self.enforce_change_control()

	def on_update(self):
		self._stamp_implemented_change_request()

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
	# Change control
	# ------------------------------------------------------------------

	def enforce_change_control(self):
		"""No change to a controlled document without an approved change request.

		This is SOP-001's own rule ("changes shall be reviewed, approved and
		recorded") made mechanical. It guards content, not process: workflow
		transitions, authority stamps and review scheduling pass freely, but any
		edit to what the document *says* -- or to its issue and revision numbers --
		on an Approved or Active document requires a submitted Document Change
		Request raised against this document. The DCR is consumed when the
		revision number moves, so one request authorises one revision.
		"""
		if (
			frappe.flags.in_import
			or frappe.flags.in_patch
			or frappe.flags.in_migrate
			or frappe.flags.in_install
		):
			return

		previous = self.get_doc_before_save()
		if not previous or (previous.workflow_state or "") not in GUARDED_STATES:
			return

		changed = self._controlled_changes(previous)
		if not changed:
			return

		self._require_change_request(changed, previous)
		self._advance_numbers(previous)

	def _next_numbers(self, previous) -> tuple[str, str]:
		"""The numbering rule: revisions 01 to 09 amend an issue; the tenth change
		does not become revision 10 -- it re-issues the document, issue number up,
		revision back to 00. The eleventh change is then revision 01 of the new
		issue. Ten changes per edition, the way the paper headers already count."""
		rev = cint(previous.revision_number) + 1
		if rev >= 10:
			return f"{cint(previous.issue_number) + 1:02d}", "00"
		return (previous.issue_number or "01"), f"{rev:02d}"

	def _advance_numbers(self, previous):
		"""Move the control block for an authorised change, or verify a manual move.

		Runs only after the change request has been validated. If the author left
		the numbers alone, the system advances them by the rule and writes the
		Change History row from the request itself; if the author moved them by
		hand, anything other than the rule's next value is refused, so the
		numbering cannot drift however it is edited.
		"""
		next_issue, next_rev = self._next_numbers(previous)
		user_moved = (
			self.revision_number != previous.revision_number
			or self.issue_number != previous.issue_number
		)

		if user_moved and (self.issue_number, self.revision_number) != (next_issue, next_rev):
			frappe.throw(
				_(
					"The next change to {0} must be Issue {1} / Revision {2} (ten changes per "
					"issue, then a re-issue). Leave the numbers unchanged and the system will "
					"set them."
				).format(frappe.bold(self.name), next_issue, next_rev),
				title=_("Issue / Revision Numbering"),
			)

		self.issue_number, self.revision_number = next_issue, next_rev
		today = nowdate()
		self.revision_date = today
		if next_rev == "00":
			self.issue_date = today

		# The Change History row comes from the request, unless the author already
		# wrote one in this save.
		if len(self.revisions or []) <= len(previous.revisions or []):
			dcr = frappe.db.get_value(
				"Document Change Request",
				self.change_request,
				["reason_for_change", "clause_section_affected"],
				as_dict=True,
			)
			description = (dcr.reason_for_change or "").strip() or _("Authorised change")
			self.append_revision(
				_("{0} (via {1})").format(description, self.change_request),
				dcr.clause_section_affected,
			)

	def _controlled_changes(self, previous) -> list[str]:
		changed = []
		for field in self.meta.fields:
			if field.fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML", "Button"):
				continue
			if field.fieldname in UNCONTROLLED_FIELDS:
				continue
			if field.fieldtype in ("Table", "Table MultiSelect"):
				if self._table_changed(previous, field.fieldname):
					changed.append(field.fieldname)
			elif (self.get(field.fieldname) or "") != (previous.get(field.fieldname) or ""):
				changed.append(field.fieldname)
		return changed

	def _table_changed(self, previous, fieldname) -> bool:
		meta_fields = {
			"name", "owner", "creation", "modified", "modified_by", "docstatus",
			"parent", "parentfield", "parenttype", "doctype", "__islocal", "__unsaved",
		}

		def snapshot(doc):
			return [
				{k: v for k, v in row.as_dict().items() if k not in meta_fields}
				for row in doc.get(fieldname) or []
			]

		return snapshot(self) != snapshot(previous)

	def _require_change_request(self, changed: list[str], previous):
		labels = ", ".join(_(self.meta.get_label(f)) for f in changed[:6])
		if not self.change_request:
			frappe.throw(
				_(
					"{0} is {1} and under change control. Raise a Document Change Request, "
					"have it approved, and set it in the Change Request field before changing: {2}."
				).format(frappe.bold(self.name), frappe.bold(previous.workflow_state), labels),
				title=_("Change Control"),
			)

		dcr = frappe.db.get_value(
			"Document Change Request",
			self.change_request,
			["controlled_document", "docstatus", "status"],
			as_dict=True,
		)
		if not dcr:
			frappe.throw(_("Change Request {0} does not exist.").format(self.change_request), title=_("Change Control"))
		if dcr.controlled_document != self.name:
			frappe.throw(
				_("Change Request {0} was raised against {1}, not this document.").format(
					self.change_request, frappe.bold(dcr.controlled_document)
				),
				title=_("Change Control"),
			)
		if dcr.docstatus != 1:
			frappe.throw(
				_("Change Request {0} has not been approved. Submit it first.").format(self.change_request),
				title=_("Change Control"),
			)
		if (dcr.status or "") == "Implemented":
			frappe.throw(
				_(
					"Change Request {0} has already been implemented. One request authorises one "
					"revision; raise a new one for a further change."
				).format(self.change_request),
				title=_("Change Control"),
			)

	def _stamp_implemented_change_request(self):
		"""Mark the DCR implemented once the revision it authorised is recorded."""
		previous = self.get_doc_before_save()
		if not previous or not self.change_request:
			return
		if (
			self.revision_number != previous.revision_number
			or self.issue_number != previous.issue_number
		):
			frappe.db.set_value(
				"Document Change Request",
				self.change_request,
				{"status": "Implemented", "resulting_revision": self.revision_number},
				update_modified=False,
			)

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

		A register whose content is not a flat list of one DocType declares a report
		instead. That is what lets a register be derived from what the system already
		recorded -- an amendment register is a comparison between two orders plus the
		framework's own change log -- rather than re-entered into a second form.
		"""
		if self.static_table:
			return self.get_static_rows()

		if self.mapped_report:
			return self.get_report_rows(limit=limit)

		if not self.mapped_doctype:
			return {"columns": [], "rows": [], "total": 0}

		if not frappe.db.exists("DocType", self.mapped_doctype):
			return {"columns": [], "rows": [], "total": 0, "error": _("Mapped DocType no longer exists.")}

		meta = frappe.get_meta(self.mapped_doctype)

		# A child table has no permissions of its own -- has_permission on one is
		# False for everybody except Administrator. Its access question is the
		# parent's, which _child_table_rows asks before reading anything.
		if not meta.istable and not frappe.has_permission(self.mapped_doctype, "read"):
			return {"columns": [], "rows": [], "total": 0, "error": _("Not permitted to read the mapped DocType.")}
		columns = self._declared_columns(meta) or self._default_columns(meta)

		# A child row's name is a hash, which is not a register column. The row's
		# identity in print is whatever the declared columns say it is.
		if meta.istable and len(columns) > 1:
			columns = [c for c in columns if c["fieldname"] != "name"]

		filters = {}
		if self.mapped_filters:
			try:
				filters = json.loads(self.mapped_filters)
			except ValueError:
				return {"columns": [], "rows": [], "total": 0, "error": _("Mapped Filters is not valid JSON.")}

		if meta.istable:
			return self._child_table_rows(columns, filters, limit)

		total = frappe.db.count(self.mapped_doctype, filters)
		rows = frappe.get_all(
			self.mapped_doctype,
			filters=filters,
			fields=[c["fieldname"] for c in columns if c["fieldname"]],
			order_by="creation asc",
			limit_page_length=limit,
		)
		return {"columns": columns, "rows": _shape(rows), "total": total, "shown": len(rows), "limit": limit}

	def get_static_rows(self) -> dict:
		"""A register whose rows are part of the controlled document itself.

		The retention register is policy: its rows change when the policy does,
		through a change request, not when a transaction happens. Held as JSON
		{"columns": [...], "rows": [[...]]} in the static_table field, which is
		content and therefore guarded by change control like the rest.
		"""
		try:
			spec = json.loads(self.static_table) if isinstance(self.static_table, str) else self.static_table
		except ValueError:
			return {"columns": [], "rows": [], "total": 0, "error": _("Static Table is not valid JSON.")}

		columns = []
		for item in spec.get("columns") or []:
			if isinstance(item, dict):
				columns.append({"fieldname": item.get("fieldname"), "label": _(item.get("label") or ""),
					**{k: item[k] for k in ("width", "group") if item.get(k)}})
			else:
				columns.append({"fieldname": None, "label": _(str(item))})
		rows = [
			{columns[i]["fieldname"] or f"c{i}": v for i, v in enumerate(row) if i < len(columns)}
			for row in spec.get("rows") or []
		]
		for i, c in enumerate(columns):
			c["fieldname"] = c["fieldname"] or f"c{i}"
		return {"columns": columns, "rows": rows, "total": len(rows), "shown": len(rows), "static": True}

	def _declared_columns(self, meta) -> list | None:
		"""The columns this document says its print should carry.

		Declared per document because the generic fallback prints whatever is in
		list view, which is chosen for screen browsing, not for evidence. A
		dispatch register needs the transport receipt; an inspection register
		needs what was inspected against and who inspected it. Unknown fieldnames
		are skipped rather than raised: a schema change must not break printing.

		A column entry is either a `[fieldname, label]` pair or a dict adding
		`width` (CSS width of the column), `group` (spans a two-row header, so
		Make / Model / Serial can sit under one "Machine Description" band the
		way the source register draws it), or no fieldname at all -- a blank
		column, printed empty under its source heading until the field it is
		waiting on exists. The blank keeps the printed page identical to the
		template people already fill by hand.
		"""
		if not self.print_columns:
			return None
		try:
			spec = json.loads(self.print_columns) if isinstance(self.print_columns, str) else self.print_columns
		except ValueError:
			return None

		std = {"creation", "modified", "owner", "parent"}
		columns = [{"fieldname": "name", "label": _("ID")}]
		for item in spec or []:
			extra = {}
			if isinstance(item, (list, tuple)) and item:
				fieldname, label = item[0], (item[1] if len(item) > 1 else item[0])
			elif isinstance(item, dict):
				fieldname, label = item.get("fieldname"), item.get("label")
				extra = {k: item[k] for k in ("width", "group") if item.get(k)}
			else:
				continue
			if fieldname == "name":
				continue
			if not fieldname:
				if label:  # blank column: heading with nothing to fetch
					columns.append({"fieldname": None, "label": _(label), **extra})
				continue
			if fieldname in std or meta.get_field(fieldname):
				columns.append({"fieldname": fieldname, "label": _(label or fieldname), **extra})
			if len(columns) >= 15:
				break
		return columns if len(columns) > 1 else None

	def _default_columns(self, meta) -> list:
		skip = {"Section Break", "Column Break", "Tab Break", "Table", "HTML", "Button", "Attach", "Text Editor"}
		columns = [{"fieldname": "name", "label": _("ID")}]
		for field in meta.fields:
			if len(columns) >= 7:
				break
			if field.in_list_view and field.fieldtype not in skip:
				columns.append({"fieldname": field.fieldname, "label": _(field.label or field.fieldname)})
		return columns

	def _child_table_rows(self, columns, filters, limit) -> dict:
		"""A register can live in a child table -- the training register is the
		attendee rows under Training Event, not the events. Permission is checked
		against the parent DocType, which is where child rows get theirs from."""
		parent_dt = frappe.db.get_value(
			"DocField", {"fieldtype": ("in", ["Table", "Table MultiSelect"]), "options": self.mapped_doctype}, "parent"
		)
		if parent_dt and not frappe.has_permission(parent_dt, "read"):
			return {"columns": [], "rows": [], "total": 0, "error": _("Not permitted to read the mapped DocType.")}

		filters = dict(filters or {})
		if parent_dt:
			filters["parenttype"] = parent_dt

		total = frappe.db.count(self.mapped_doctype, filters)
		rows = frappe.get_all(
			self.mapped_doctype,
			filters=filters,
			fields=[c["fieldname"] for c in columns if c["fieldname"]],
			order_by="creation asc",
			limit_page_length=limit,
			parent_doctype=parent_dt,
		)
		return {"columns": columns, "rows": _shape(rows), "total": total, "shown": len(rows), "limit": limit}

	def get_report_rows(self, limit: int = 200) -> dict:
		"""Run the declared report and shape it like register content."""
		if not frappe.db.exists("Report", self.mapped_report):
			return {"columns": [], "rows": [], "total": 0, "error": _("Mapped Report no longer exists.")}

		report = frappe.get_doc("Report", self.mapped_report)
		if not frappe.has_permission(report.ref_doctype, "read"):
			return {"columns": [], "rows": [], "total": 0, "error": _("Not permitted to read the report's data.")}

		filters = {}
		if self.mapped_filters:
			try:
				filters = json.loads(self.mapped_filters)
			except ValueError:
				return {"columns": [], "rows": [], "total": 0, "error": _("Mapped Filters is not valid JSON.")}

		result = report.execute_script_report(frappe._dict(filters))
		columns = result[0] or []
		rows = result[1] or []

		# Reports return column dicts; normalise to the same shape the DocType path
		# produces so the print macro does not care which kind of register this is.
		norm_columns = [
			{"fieldname": c.get("fieldname"), "label": c.get("label")}
			for c in columns
			if isinstance(c, dict) and c.get("fieldname")
		][:14]

		# The document's declared columns override the report's own: same
		# fieldnames, but the register's headings, widths, header groups and
		# ordering -- and blank columns the report cannot fill.
		if self.print_columns:
			try:
				spec = json.loads(self.print_columns) if isinstance(self.print_columns, str) else self.print_columns
			except ValueError:
				spec = None
			if spec:
				known = {c["fieldname"] for c in norm_columns}
				declared = []
				for item in spec:
					if isinstance(item, (list, tuple)) and item:
						item = {"fieldname": item[0], "label": item[1] if len(item) > 1 else item[0]}
					if not isinstance(item, dict):
						continue
					fieldname = item.get("fieldname")
					if fieldname and fieldname not in known:
						continue
					declared.append({"fieldname": fieldname or None, "label": _(item.get("label") or fieldname),
						**{k: item[k] for k in ("width", "group") if item.get(k)}})
				if declared:
					norm_columns = declared

		return {
			"columns": norm_columns,
			"rows": rows[:limit],
			"total": len(rows),
			"shown": min(len(rows), limit),
			"limit": limit,
			"source": self.mapped_report,
		}

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


def _shape(rows: list) -> list:
	"""Make raw values printable: datetimes trimmed to the minute, rich-text
	fields stripped to their text. A register column carrying microseconds or
	HTML tags reads like a database dump, not a record."""
	import datetime

	from frappe.utils import strip_html

	for row in rows:
		for key, value in list(row.items()):
			if isinstance(value, datetime.datetime):
				row[key] = str(value)[:16]
			elif isinstance(value, str) and "<" in value and ">" in value:
				row[key] = strip_html(value).strip()
	return rows


def pad_control_number(value, label: str) -> str:
	"""Return a two-digit zero-padded control number, e.g. '0' -> '00', '1' -> '01'."""
	value = (str(value) if value is not None else "").strip()
	if not value:
		frappe.throw(_("{0} is required.").format(label))

	if not value.isdigit():
		# Non-numeric editions such as 'A' are left untouched rather than mangled.
		return value

	return value.zfill(2)
