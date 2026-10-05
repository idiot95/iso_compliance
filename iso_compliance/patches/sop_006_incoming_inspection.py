# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The one-time data work behind SOP-006.

Four corrections, each idempotent, each leaving a trail in the bench log:

1. **Adopt `Purchase Receipt.custom_recevied_by`.** Created by hand with `module`
   unset, so it belonged to no app and shipped in no fixture -- while holding the
   only record of who received goods, on all 415 receipts. The typo in the
   fieldname is kept: renaming it would orphan every one of those rows.

2. **Let a rejection be recorded.** `action_if_quality_inspection_is_rejected` was
   "Stop", which makes a receipt carrying a rejected inspection unsubmittable. In
   372 incoming inspections not one was ever marked Rejected -- the path was shut,
   so nobody used it. Applied once here rather than from an ensure hook, so the
   setting stays the site's to change afterwards.

3. **Backfill `Batch.supplier`.** 355 batches came from Purchase Receipts and none
   recorded a supplier, breaking traceability at its first link.

4. **Backfill `Item.quality_inspection_template`.** 521 items require inspection at
   receipt and 2 named a template, so the inspector picked one by hand every time.
   Each item's own inspection history is the best evidence of the right template;
   the item group default covers items with no history.
"""

import frappe

RECEIVED_BY = "Purchase Receipt-custom_recevied_by"


def execute():
	# Migrate syncs fixtures *after* post_model_sync patches, so the Item Group and
	# Batch fields this patch reads do not exist yet on the run that introduces
	# them. Syncing here is idempotent -- migrate's own pass later finds nothing to
	# do -- and is cheaper than splitting the patch across two releases.
	from frappe.utils.fixtures import sync_fixtures

	sync_fixtures("iso_compliance")

	seed_item_group_requirements()
	adopt_received_by()
	allow_rejection_to_be_recorded()
	backfill_batch_suppliers()
	backfill_inspection_templates()


def adopt_received_by():
	"""Bring the hand-made Received By field into the app so it ships."""
	if not frappe.db.exists("Custom Field", RECEIVED_BY):
		return
	if frappe.db.get_value("Custom Field", RECEIVED_BY, "module") == "ISO Compliance":
		return
	frappe.db.set_value("Custom Field", RECEIVED_BY, "module", "ISO Compliance", update_modified=False)
	print(f"iso_compliance: adopted {RECEIVED_BY} into module 'ISO Compliance'")


def allow_rejection_to_be_recorded():
	"""Stop -> Warn, so a receipt can post with its rejected quantity segregated."""
	current = frappe.db.get_single_value("Stock Settings", "action_if_quality_inspection_is_rejected")
	if current != "Stop":
		return
	frappe.db.set_single_value("Stock Settings", "action_if_quality_inspection_is_rejected", "Warn")
	print(
		"iso_compliance: Stock Settings action_if_quality_inspection_is_rejected "
		"Stop -> Warn (SOP-006 step 5 needs the rejection to be recordable)"
	)


def backfill_batch_suppliers():
	"""Fill Batch.supplier from the receipt each batch already points at."""
	rows = frappe.get_all(
		"Batch",
		filters={
			"reference_doctype": "Purchase Receipt",
			# "is set" / "is not set", not an IN list: `reference_name NOT IN (NULL, '')`
			# is NULL for every row, so an IN-list exclusion silently matches nothing.
			"supplier": ("is", "not set"),
			"reference_name": ("is", "set"),
		},
		fields=["name", "reference_name"],
		limit_page_length=0,
	)
	if not rows:
		return

	suppliers = dict(
		frappe.get_all(
			"Purchase Receipt",
			filters={"name": ("in", {r.reference_name for r in rows})},
			fields=["name", "supplier"],
			as_list=True,
			limit_page_length=0,
		)
	)
	filled = 0
	for row in rows:
		supplier = suppliers.get(row.reference_name)
		if not supplier:
			continue
		frappe.db.set_value("Batch", row.name, "supplier", supplier, update_modified=False)
		filled += 1
	print(f"iso_compliance: set supplier on {filled} of {len(rows)} receipt-born batches")


def backfill_inspection_templates():
	"""Give every inspected item a standing template: its own history first, then its group.

	An item that has been inspected before tells us what was measured; the most
	frequently used template on its own submitted inspections is a better default
	than anything a group-level rule could infer. Only items that name no template
	are touched, so a deliberate choice is never overwritten.
	"""
	items = frappe.get_all(
		"Item",
		filters={
			"disabled": 0,
			"inspection_required_before_purchase": 1,
			"quality_inspection_template": ("in", (None, "")),
		},
		fields=["name", "item_group"],
		limit_page_length=0,
	)
	if not items:
		return

	# Most-used template per item across its submitted inspections.
	history: dict[str, str] = {}
	for row in frappe.db.sql(
		"""
		select item_code, quality_inspection_template, count(*) as n
		from `tabQuality Inspection`
		where docstatus = 1
		  and quality_inspection_template is not null and quality_inspection_template != ''
		group by item_code, quality_inspection_template
		order by item_code, n desc
		""",
		as_dict=True,
	):
		history.setdefault(row.item_code, row.quality_inspection_template)

	from iso_compliance.overrides.purchase_receipt import default_inspection_template

	group_default: dict[str, str | None] = {}
	from_history = from_group = 0
	for item in items:
		template = history.get(item.name)
		if template:
			from_history += 1
		else:
			if item.item_group not in group_default:
				group_default[item.item_group] = default_inspection_template(item.item_group)
			template = group_default[item.item_group]
			if template:
				from_group += 1
		if not template or not frappe.db.exists("Quality Inspection Template", template):
			continue
		frappe.db.set_value(
			"Item", item.name, "quality_inspection_template", template, update_modified=False
		)

	print(
		f"iso_compliance: inspection template set on {from_history + from_group} of {len(items)} items "
		f"({from_history} from the item's own history, {from_group} from its item group); "
		f"{len(items) - from_history - from_group} still unmapped"
	)


#: Item groups whose consignments are expected to arrive with a Material Test
#: Certificate: raw and bought-out *material*, where the supplier's mill or batch
#: certificate is the evidence of grade. Tools, packaging, lubricants, dies and
#: measuring equipment are left out -- a certificate means nothing for a grinding
#: wheel. A starting position for the developer to correct, not a fixed rule: the
#: flag is a field on the Item Group and changing it needs no code.
MTC_REQUIRED_GROUPS = (
	"Carbon Block",
	"Copper Wire",
	"Sheet Metal",
	"Tubes & Rods",
	"Rubberized Insulation Sheet",
	"Raw Insulation Sheet",
	"Tamping Powder",
	"Sleeving",
	"Chemicals",
	"Adhesives & Resins",
)

#: Default inspection template per item group, set only where one template clearly
#: serves the whole group. Four groups are deliberately absent because several
#: templates serve them and the material decides which -- Copper Wire has five
#: (Bare Cu Wire, Tinned Copper Wire, Flat Wire, Wire, Teflon Coated Wire), and
#: Sheet Metal, Tubes & Rods and Clamps have three each. For those the per-item
#: backfill from inspection history is the accurate source; the group default here
#: is only a fallback for an item nobody has inspected yet.
GROUP_DEFAULT_TEMPLATES = {
	"Carbon Block": "Carbon Block",
	"Rubberized Insulation Sheet": "Rubberized Insulation Sheet",
	"Sheet Metal": "Sheet Metal",
	"Tubes & Rods": "Tubes",
	"Copper Wire": "Wire",
	"Terminal": "Terminal",
	"Brush Holder": "Brush Holder",
	"Slipring Unit": "Slipring Unit",
	"Spring Assemblies": "Spring",
	"Carbon Brush": "Carbon Brush",
	"Clamps": "Clamps",
	"Fasteners": "Rivet",
}


def seed_item_group_requirements():
	"""Write the opening position for SOP-006's per-group rules.

	Only ever fills a blank: a group the developer has already judged is left alone,
	so re-running this never argues with a decision made on the site.
	"""
	flagged = templated = 0
	for group in MTC_REQUIRED_GROUPS:
		if not frappe.db.exists("Item Group", group):
			continue
		if frappe.db.get_value("Item Group", group, "custom_mtc_required"):
			continue
		frappe.db.set_value("Item Group", group, "custom_mtc_required", 1, update_modified=False)
		flagged += 1

	for group, template in GROUP_DEFAULT_TEMPLATES.items():
		if not frappe.db.exists("Item Group", group):
			continue
		if not frappe.db.exists("Quality Inspection Template", template):
			continue
		if frappe.db.get_value("Item Group", group, "custom_default_qi_template"):
			continue
		frappe.db.set_value(
			"Item Group", group, "custom_default_qi_template", template, update_modified=False
		)
		templated += 1

	if flagged or templated:
		print(
			f"iso_compliance: item groups -- MTC required on {flagged}, default template on {templated}"
		)
