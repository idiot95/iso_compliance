"""Throwaway: prove the ten-changes-per-issue numbering rule on the clone.

Restores itself by purging and re-importing the seed at the end.
"""

import frappe

PREP = "bidhan.dutta@hatimcarbon.com"
DOC = "HCCPL/QMS/SOP-001"


def ok(label, cond):
	print(("PASS  " if cond else "FAIL  ") + label)


def _approved_dcr():
	frappe.set_user(PREP)
	dcr = frappe.get_doc(
		{
			"doctype": "Document Change Request",
			"controlled_document": DOC,
			"change_type": "Revision",
			"request_date": frappe.utils.nowdate(),
			"clause_section_affected": "1. Purpose",
			"reason_for_change": "Numbering rule smoke test.",
		}
	).insert(ignore_permissions=True)
	frappe.set_user("Administrator")
	dcr.reload()
	dcr.submit()
	return dcr


def run():
	# --- ordinary change: 01/00 -> 01/01, row appended, DCR consumed ----------
	dcr = _approved_dcr()
	doc = frappe.get_doc("Controlled Document", DOC)
	rows_before = len(doc.revisions)
	doc.change_request = dcr.name
	doc.title = doc.title + " (numbering test)"
	doc.save(ignore_permissions=True)
	doc.reload()
	dcr.reload()
	ok(f"revision auto-advances to 01 (got {doc.issue_number}/{doc.revision_number})",
		(doc.issue_number, doc.revision_number) == ("01", "01"))
	ok("change history row appended from the DCR",
		len(doc.revisions) == rows_before + 1 and dcr.name in (doc.revisions[-1].description_of_change or ""))
	ok(f"DCR consumed (status={dcr.status})", dcr.status == "Implemented")

	# --- tenth change: 01/09 -> 02/00 (re-issue) ------------------------------
	frappe.db.set_value("Controlled Document", DOC, "revision_number", "09", update_modified=False)
	dcr2 = _approved_dcr()
	doc = frappe.get_doc("Controlled Document", DOC)
	doc.change_request = dcr2.name
	doc.title = doc.title + " again"
	doc.save(ignore_permissions=True)
	doc.reload()
	ok(f"tenth change re-issues (got {doc.issue_number}/{doc.revision_number})",
		(doc.issue_number, doc.revision_number) == ("02", "00"))
	ok("issue date moved on re-issue", str(doc.issue_date) == frappe.utils.nowdate())

	# --- manual wrong number is refused ---------------------------------------
	dcr3 = _approved_dcr()
	doc = frappe.get_doc("Controlled Document", DOC)
	doc.change_request = dcr3.name
	doc.title = doc.title + " third"
	doc.revision_number = "07"
	try:
		doc.save(ignore_permissions=True)
		ok("manual off-rule number refused", False)
	except frappe.ValidationError as e:
		ok(f"manual off-rule number refused -> {str(e)[:60]}", "must be Issue" in str(e))

	# --- restore --------------------------------------------------------------
	frappe.set_user("Administrator")
	for d in (dcr3, dcr2, dcr):
		d.reload()
		if d.docstatus == 1:
			d.cancel()
		d.delete(ignore_permissions=True, force=True)
	from iso_compliance.seed.controlled_documents import import_seed, purge_seed

	purge_seed()
	import_seed()
	print("restored: seed purged and re-imported")
