# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-006, post first and inspect after (developer, 2026-10-14). One-time setup
for iso_compliance.overrides.inspection_flow; every step is idempotent.

1. The fields (Item Group QC flag, receiving checks, accepted / rejected
   quantities, warehouse after inspection, release link).
2. An "Inspection Required" warehouse per company, beside Rejected.
3. Stock Settings: allow the inspection after the receipt is posted.
4. The Item Group QC flag, seeded from what the site already inspects: groups
   where most stock items were flagged for inspection before purchase, the
   groups that must carry a supplier certificate, and Finished Goods (so a
   Work Order's finished output is inspected). It is a tick on Item Group,
   for Quality to change.
5. Each stock item's "Inspection Required before Purchase" follows its group.
6. Items without batches get their item code as a barcode, so labels scan.
"""

import frappe

from iso_compliance.overrides.inspection_flow import INSPECTION_WAREHOUSE, create_fields

SEED_EXTRA = ("Finished Goods",)


def execute():
	create_fields()
	frappe.clear_cache(doctype="Item Group")
	ensure_warehouse()
	frappe.db.set_single_value("Stock Settings", "allow_to_make_quality_inspection_after_purchase_or_delivery", 1)
	seed_groups()
	sync_items()
	item_barcodes()


def ensure_warehouse():
	for company in frappe.get_all("Company", fields=["name", "abbr"]):
		name = f"{INSPECTION_WAREHOUSE} - {company.abbr}"
		if frappe.db.exists("Warehouse", name):
			continue
		root = frappe.db.get_value(
			"Warehouse", {"company": company.name, "is_group": 1, "parent_warehouse": ("in", (None, ""))}, "name")
		frappe.get_doc({"doctype": "Warehouse", "warehouse_name": INSPECTION_WAREHOUSE, "company": company.name,
		                "is_group": 0, "parent_warehouse": root}).insert(ignore_permissions=True)
		print(f"iso_compliance: created warehouse {name}")


def seed_groups():
	if frappe.get_all("Item Group", filters={"custom_qc_required": 1}, limit=1):
		return  # already decided on this site
	mostly_inspected = [
		g for g, flagged, n in frappe.db.sql(
			"""select item_group, sum(inspection_required_before_purchase), count(*) from tabItem
			where disabled = 0 and is_stock_item = 1 group by item_group""")
		if n and flagged / n >= 0.5
	]
	certificate = frappe.get_all("Item Group", filters={"custom_mtc_required": 1}, pluck="name")
	groups = sorted({*mostly_inspected, *certificate, *(g for g in SEED_EXTRA if frappe.db.exists("Item Group", g))})
	for g in groups:
		frappe.db.set_value("Item Group", g, "custom_qc_required", 1, update_modified=False)
	print(f"iso_compliance: quality inspection required on item groups {', '.join(groups)}")


def _qc_groups() -> set[str]:
	"""Every group whose own flag or an ancestor's is set."""
	flagged = frappe.get_all("Item Group", filters={"custom_qc_required": 1}, fields=["lft", "rgt"])
	out = set()
	for f in flagged:
		out.update(frappe.get_all("Item Group", filters={"lft": (">=", f.lft), "rgt": ("<=", f.rgt)}, pluck="name"))
	return out


def sync_items():
	groups = _qc_groups()
	items = frappe.get_all("Item", filters={"is_stock_item": 1}, fields=["name", "item_group", "inspection_required_before_purchase"])
	on = [i.name for i in items if i.item_group in groups and not i.inspection_required_before_purchase]
	off = [i.name for i in items if i.item_group not in groups and i.inspection_required_before_purchase]
	for names, value in ((on, 1), (off, 0)):
		if names:
			frappe.db.sql("update tabItem set inspection_required_before_purchase = %s where name in %s", (value, tuple(names)))
	print(f"iso_compliance: inspection before purchase switched on for {len(on)} item(s), off for {len(off)}")


def item_barcodes():
	taken = set(frappe.get_all("Item Barcode", pluck="barcode"))
	added = 0
	for item in frappe.get_all("Item", filters={"has_batch_no": 0, "is_stock_item": 1, "disabled": 0}, pluck="name"):
		if item in taken:
			continue
		row = frappe.get_doc({"doctype": "Item Barcode", "name": frappe.generate_hash(length=10), "parent": item,
		                      "parenttype": "Item", "parentfield": "barcodes", "barcode": item, "idx": 99})
		row.db_insert()
		added += 1
	print(f"iso_compliance: item-code barcode added to {added} item(s) without batches")
