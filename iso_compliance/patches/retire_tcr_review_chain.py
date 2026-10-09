# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""FRM-036 becomes one form filled by assigned reviewers (2026-10-09).

The sequential workflow (Draft -> Technical -> Costing -> Commercial ->
Approved) and the five bell notifications that followed it are removed;
reviewers are now notified by ERPNext's own assignment. A review that was
mid-chain becomes a plain draft with its answers intact. A draft nobody has
answered yet is reloaded with the new, shorter checklist.

The Technical/Costing/Commercial Reviewer roles are left in place: users
may hold them and deleting a role is not this patch's call.
"""

import frappe

NOTIFICATIONS = (
	"Techno-Commercial Review: Technical stage",
	"Techno-Commercial Review: Costing stage",
	"Techno-Commercial Review: Commercial stage",
	"Techno-Commercial Review: sent back",
	"Techno-Commercial Review: approved",
)

CHECKLISTS = ("technical_parameters", "costing_parameters", "commercial_parameters", "overall_parameters")


def execute():
	if frappe.db.exists("Workflow", "Techno-Commercial Review"):
		frappe.delete_doc("Workflow", "Techno-Commercial Review", ignore_permissions=True, force=True)
	frappe.db.delete("Workflow Action", {"reference_doctype": "Techno Commercial Review", "status": "Open"})

	for name in NOTIFICATIONS:
		if frappe.db.exists("Notification", name):
			frappe.delete_doc("Notification", name, ignore_permissions=True, force=True)

	if not frappe.db.table_exists("Techno Commercial Review"):
		return
	for name in frappe.get_all("Techno Commercial Review", filters={"docstatus": 0}, pluck="name"):
		answered = frappe.db.exists(
			"Techno Commercial Review Parameter",
			{"parent": name, "parenttype": "Techno Commercial Review", "response": ("is", "set")},
		)
		if answered:
			continue
		frappe.db.delete(
			"Techno Commercial Review Parameter",
			{"parent": name, "parenttype": "Techno Commercial Review", "parentfield": ("in", CHECKLISTS)},
		)
		doc = frappe.get_doc("Techno Commercial Review", name)
		doc.flags.ignore_permissions = True
		doc.save()
