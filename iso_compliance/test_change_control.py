"""Throwaway: prove the DCR gate, landscape output and new columns on the clone."""

import frappe

PREP = "bidhan.dutta@hatimcarbon.com"


def ok(label, cond):
	print(("PASS  " if cond else "FAIL  ") + label)


def throws(label, fn, needle=""):
	try:
		fn()
	except frappe.ValidationError as e:
		hit = needle.lower() in str(e).lower() if needle else True
		print(("PASS  " if hit else "FAIL  ") + f"{label}  -> {str(e)[:80]}")
		return
	print(f"FAIL  {label}  -> no exception raised")


def run():
	# --- landscape ---------------------------------------------------------
	from pypdf import PdfReader
	import io

	pdf = frappe.get_print("Controlled Document", "HCCPL/QMS/REG-024", "Controlled Document", as_pdf=True)
	page = PdfReader(io.BytesIO(pdf)).pages[0]
	w, h = float(page.mediabox.width), float(page.mediabox.height)
	ok(f"REG-024 prints landscape ({w:.0f} x {h:.0f})", w > h)
	with open("/tmp/REG-024.pdf", "wb") as fh:
		fh.write(pdf)

	# --- required-not-filled columns --------------------------------------
	reg9 = frappe.get_doc("Controlled Document", "HCCPL/QMS/REG-009")
	data = reg9.get_register_rows(limit=3)
	labels = [c["label"] for c in data["columns"]]
	ok(f"REG-009 shows Action Taken column ({labels})", "Action Taken" in labels)
	sample = data["rows"][0] if data["rows"] else {}
	ok("rich text stripped in rows", "<" not in str(sample.get("corrective_action") or ""))

	# --- change control ----------------------------------------------------
	name = "HCCPL/QMS/SOP-001"

	def edit_without_dcr():
		doc = frappe.get_doc("Controlled Document", name)
		doc.title = doc.title + " (rev)"
		doc.save(ignore_permissions=True)

	throws("editing an Active document without a DCR is blocked", edit_without_dcr, "Change Request")

	# Raise a DCR as the preparer, approve as a different user.
	frappe.set_user(PREP)
	dcr = frappe.get_doc(
		{
			"doctype": "Document Change Request",
			"controlled_document": name,
			"change_type": "Revision",
			"request_date": frappe.utils.nowdate(),
			"clause_section_affected": "1. Purpose",
			"reason_for_change": "Change-control smoke test.",
		}
	).insert(ignore_permissions=True)
	ok(f"DCR raised by preparer ({dcr.name}, requested_by={dcr.requested_by})", dcr.requested_by == PREP)

	def self_approve():
		dcr.submit()

	throws("requester cannot approve their own DCR", self_approve, "Segregation")

	frappe.set_user("Administrator")
	dcr.reload()
	dcr.submit()
	ok(f"DCR approved by second person (status={dcr.status})", dcr.status == "Approved" and dcr.docstatus == 1)

	def edit_with_wrong_doc():
		doc = frappe.get_doc("Controlled Document", "HCCPL/QMS/SOP-002")
		doc.change_request = dcr.name
		doc.title = doc.title + " (rev)"
		doc.save(ignore_permissions=True)

	throws("a DCR cannot authorise a change to a different document", edit_with_wrong_doc, "not this document")

	doc = frappe.get_doc("Controlled Document", name)
	doc.change_request = dcr.name
	doc.title = doc.title + " (rev)"
	doc.save(ignore_permissions=True)
	ok("content edit passes with an approved DCR", True)

	doc.reload()
	doc.revision_number = "01"
	doc.revision_date = frappe.utils.nowdate()
	doc.append_revision("Smoke test revision via " + dcr.name, "1. Purpose")
	doc.save(ignore_permissions=True)
	dcr.reload()
	ok(
		f"revision bump consumes the DCR (status={dcr.status}, resulting={dcr.resulting_revision})",
		dcr.status == "Implemented" and dcr.resulting_revision == "01",
	)

	def reuse():
		d2 = frappe.get_doc("Controlled Document", name)
		d2.title = d2.title + " again"
		d2.save(ignore_permissions=True)

	throws("an implemented DCR cannot be reused", reuse, "already been implemented")

	# --- restore -----------------------------------------------------------
	dcr.reload()
	dcr.cancel()
	dcr.delete(ignore_permissions=True, force=True)
	from iso_compliance.seed.controlled_documents import purge_seed, import_seed

	purge_seed()
	import_seed()
	print("restored: seed purged and re-imported")
