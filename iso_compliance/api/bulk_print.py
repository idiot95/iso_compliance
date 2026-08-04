# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Print the controlled document set as one PDF, each document at its current revision.

"Latest version" is not a version-history lookup: a Controlled Document record *is*
the current revision, and superseded editions are separate records marked as such.
So the current set is simply the documents that are not superseded or obsolete, and
the Change History sheet inside each one carries the editions that came before it.

Ordering is explicit everywhere. Frappe v16 defaults list ordering to `creation`,
which would put a compiled QMS manual in the order someone happened to type it in.
"""

import frappe
from frappe import _

#: Documents in these states are not part of the current controlled set.
RETIRED_STATES = ("Superseded", "Obsolete")

PRINT_FORMAT = "Controlled Document"


def get_current_documents(
	document_type: str | None = None,
	include_retired: bool = False,
	include_drafts: bool = True,
) -> list[str]:
	"""Return controlled document numbers in document-number order."""
	filters = {}
	if document_type:
		filters["document_type"] = document_type
	if not include_retired:
		filters["workflow_state"] = ("not in", RETIRED_STATES)
	if not include_drafts:
		filters["workflow_state"] = ("=", "Active")

	return frappe.get_all(
		"Controlled Document",
		filters=filters,
		pluck="name",
		# Explicit. Never rely on the framework default for an evidentiary compile.
		order_by="document_type asc, name asc",
		limit_page_length=0,
	)


@frappe.whitelist()
def print_all(
	document_type: str | None = None,
	include_retired: int | str = 0,
	include_drafts: int | str = 1,
	letterhead: str | None = None,
):
	"""Stream one PDF containing every current controlled document.

	Called from the Controlled Document list view, or directly:
	    /api/method/iso_compliance.api.bulk_print.print_all
	    /api/method/iso_compliance.api.bulk_print.print_all?document_type=SOP
	"""
	frappe.has_permission("Controlled Document", "print", throw=True)

	names = get_current_documents(
		document_type=document_type,
		include_retired=bool(int(include_retired)),
		include_drafts=bool(int(include_drafts)),
	)
	if not names:
		frappe.throw(_("No controlled documents matched."), title=_("Nothing to Print"))

	from frappe.utils.print_format import _download_multi_pdf

	return _download_multi_pdf(
		doctype={"Controlled Document": names},
		name=_filename(document_type),
		format=PRINT_FORMAT,
		letterhead=letterhead,
	)


def _filename(document_type: str | None) -> str:
	stamp = frappe.utils.now_datetime().strftime("%Y-%m-%d")
	scope = document_type or "QMS"
	return f"HCCPL-{scope}-Controlled-Documents-{stamp}"


@frappe.whitelist()
def preview_selection(document_type: str | None = None, include_retired: int | str = 0):
	"""What print_all would produce, without building the PDF."""
	names = get_current_documents(
		document_type=document_type, include_retired=bool(int(include_retired))
	)
	rows = frappe.get_all(
		"Controlled Document",
		filters={"name": ("in", names)} if names else {"name": ("is", "not set")},
		fields=["name", "title", "document_type", "issue_number", "revision_number", "workflow_state"],
		order_by="document_type asc, name asc",
		limit_page_length=0,
	)
	return {"count": len(rows), "documents": rows}
