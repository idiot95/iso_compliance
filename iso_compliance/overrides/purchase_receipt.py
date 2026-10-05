# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-006, Incoming Material Inspection & Material Identification.

Two things happen on a goods receipt that ERPNext does not do by itself.

**The Material Test Certificate.** SOP-006 asks Stores to verify it on receipt and
Quality to review it at inspection, and the Purchase Quality Requirements that ship
with every Purchase Order demand one with each consignment. ERPNext has nowhere to
put it, so it arrived as an unlabelled attachment or not at all. It is now a field
on the receipt, expected wherever the item group says so -- and the check *warns*.
Blocking a consignment that is physically on site, over a document the supplier
failed to send, would only teach Stores to leave the receipt unposted; the warning
plus REG-015's certificate column is what makes the omission visible instead.

**Segregation.** Step 5 wants rejected material kept away from accepted stock. The
rejected warehouse is where ERPNext intends it to go, but the field was left empty,
so the eleven rejections this site has recorded went to Goods In Transit, and twice
back into Stores alongside the accepted material. Any line with a rejected quantity
now defaults to the segregation warehouse if nobody chose one.
"""

import frappe
from frappe import _

#: The warehouse that holds rejected material, incoming and from production alike.
#: Created per company by setup/install.py.
REJECTED_WAREHOUSE_NAME = "Rejected"


def validate(doc, method=None):
	set_rejected_warehouse(doc)


def before_submit(doc, method=None):
	warn_missing_test_certificate(doc)


def set_rejected_warehouse(doc):
	"""Point rejected quantities at the segregation warehouse when nothing else is set."""
	if not any((row.rejected_qty or 0) > 0 for row in doc.get("items") or []):
		return

	warehouse = _rejected_warehouse(doc.company)
	if not warehouse:
		return

	if not doc.rejected_warehouse:
		doc.rejected_warehouse = warehouse
	for row in doc.get("items") or []:
		if (row.rejected_qty or 0) > 0 and not row.rejected_warehouse:
			row.rejected_warehouse = warehouse


def _rejected_warehouse(company: str | None) -> str | None:
	if not company:
		return None
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"{REJECTED_WAREHOUSE_NAME} - {abbr}"
	return name if frappe.db.exists("Warehouse", name) else None


def warn_missing_test_certificate(doc):
	"""Warn -- never block -- when a consignment that should carry an MTC has none."""
	if doc.get("custom_material_test_certificate"):
		return

	groups = {
		row.item_group or frappe.get_cached_value("Item", row.item_code, "item_group")
		for row in doc.get("items") or []
		if row.item_code
	}
	expecting = sorted(g for g in groups if g and item_group_requires_mtc(g))
	if not expecting:
		return

	frappe.msgprint(
		_("No Material Test Certificate is attached. {0} requires one with each consignment (SOP-006).").format(
			frappe.bold(", ".join(expecting))
		),
		title=_("Test Certificate Expected"),
		indicator="orange",
	)


def item_group_requires_mtc(item_group: str) -> bool:
	"""True if the group or any group above it demands a certificate.

	The flag is set on the material group and inherited, so marking "Sheet Metal"
	covers every group nested under it without restating the rule.
	"""
	for group in _group_and_ancestors(item_group):
		if frappe.get_cached_value("Item Group", group, "custom_mtc_required"):
			return True
	return False


def default_inspection_template(item_group: str) -> str | None:
	"""The nearest default inspection template at or above this group."""
	for group in _group_and_ancestors(item_group):
		template = frappe.get_cached_value("Item Group", group, "custom_default_qi_template")
		if template:
			return template
	return None


def _group_and_ancestors(item_group: str | None) -> list[str]:
	"""The group itself, then each parent up to the root.

	Walked by `parent_item_group` rather than by lft/rgt: the chain is three deep
	here, and a nested-set query would read every group to answer a question about
	one. Guarded against a cycle in the tree, which would otherwise hang the submit.
	"""
	chain, seen, current = [], set(), item_group
	while current and current not in seen:
		seen.add(current)
		chain.append(current)
		current = frappe.get_cached_value("Item Group", current, "parent_item_group")
	return chain
