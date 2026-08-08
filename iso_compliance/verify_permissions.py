"""Throwaway: prove the role scheme using real users on the clone.

shyamal.adhikari has Employee and operational roles but not Quality Manager;
bidhan.dutta has Quality Manager. Checks are read-only -- has_permission and a
print render -- so running this changes nothing.
"""

import frappe

EMPLOYEE = "shyamal.adhikari@hatimcarbon.com"
QM = "bidhan.dutta@hatimcarbon.com"


def ok(label, cond):
	print(("PASS  " if cond else "FAIL  ") + label)


def run():
	frappe.set_user(EMPLOYEE)
	ok("employee reads Controlled Document", frappe.has_permission("Controlled Document", "read"))
	ok("employee cannot write Controlled Document", not frappe.has_permission("Controlled Document", "write"))
	ok("employee cannot submit DCR", not frappe.has_permission("Document Change Request", "submit"))
	ok("employee can create DCR", frappe.has_permission("Document Change Request", "create"))
	ok("employee reads Legal Requirement", frappe.has_permission("Legal Requirement", "read"))
	try:
		html = frappe.get_print("Controlled Document", "HCCPL/QMS/SOP-001", "Controlled Document")
		ok("employee renders the SOP print", "HCCPL/QMS/SOP-001" in html and "Procedure" in html)
	except Exception as e:
		ok(f"employee renders the SOP print -> {str(e)[:60]}", False)

	frappe.set_user(QM)
	ok("quality manager writes Controlled Document", frappe.has_permission("Controlled Document", "write"))
	ok("quality manager submits DCR", frappe.has_permission("Document Change Request", "submit"))
	ok("quality manager writes Legal Requirement", frappe.has_permission("Legal Requirement", "write"))

	frappe.set_user("Administrator")
