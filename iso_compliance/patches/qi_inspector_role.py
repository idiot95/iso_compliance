# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Drawing-based inspection, Phase B (EXTERNAL_CHANGES.md §4): the Quality
Inspector role, and who may record inspections.

Permissions go through frappe.permissions.add_permission, which copies a
doctype's standard DocPerms into Custom DocPerm before adding a row. Writing
Custom DocPerm rows directly would make Frappe ignore the standard rows and
silently take Quality Manager's rights away -- so the patch checks they
survived and raises if not.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

ROLE = "Quality Inspector"

#: doctype -> rights for Quality Inspector and Stock User
GRANTS = {
	"Quality Inspection": ("read", "write", "create", "submit", "print", "report"),
	"Quality Inspection Template": ("read", "report"),
	"Test Method": ("read",),
	"Inspection Settings": ("read",),
	"QI Measurement": ("read", "report"),
	"Asset": ("read",),
	"Asset Maintenance": ("read",),
	"Asset Maintenance Task": ("read",),
}

#: (doctype, role, right) that must still hold afterwards
MUST_KEEP = (
	("Quality Inspection", "Quality Manager", "create"),
	("Quality Inspection", "Quality Manager", "write"),
	("Quality Inspection", "Quality Manager", "submit"),
	("Quality Inspection", "Quality Manager", "cancel"),
)


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)

	before = {k: _has(*k) for k in MUST_KEEP}
	for doctype, rights in GRANTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for role in (ROLE, "Stock User"):
			if doctype == "Asset Maintenance Task" and frappe.get_meta(doctype).istable:
				continue  # child table: read comes with its parent
			add_permission(doctype, role, 0)
			for right in rights:
				update_permission_property(doctype, role, 0, right, 1)
	frappe.clear_cache()

	lost = [k for k, had in before.items() if had and not _has(*k)]
	if lost:
		raise frappe.ValidationError(f"qi_inspector_role: permissions lost {lost}")


def _has(doctype, role, right) -> bool:
	table = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"
	return bool(frappe.db.get_value(table, {"parent": doctype, "role": role, "permlevel": 0, right: 1}))
