# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Where each manufactured item stands on the move to drawing-based
inspection: is there a drawing on its BOMs, a drawing template, and is the
template tagged onto the BOMs inspections start from?

Nothing switches until a template is tagged (SPEC §6); this report is the
list Quality works down.
"""

from urllib.parse import quote

import frappe
from frappe import _

from iso_compliance.qi.template import DRAWING_EXTENSIONS


def execute(filters=None):
	filters = filters or {}
	return columns(), data(filters)


def columns():
	return [
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 140},
		{"label": _("Active BOMs"), "fieldname": "boms", "fieldtype": "Int", "width": 90},
		{"label": _("With drawing"), "fieldname": "boms_with_drawing", "fieldtype": "Int", "width": 100},
		{"label": _("Tagged to a drawing template"), "fieldname": "boms_tagged", "fieldtype": "Int", "width": 120},
		{"label": _("Drawing templates"), "fieldname": "templates", "fieldtype": "Data", "width": 220},
		{"label": _("Item's template"), "fieldname": "item_template", "fieldtype": "Link", "options": "Quality Inspection Template", "width": 180},
		{"label": _("BOM requires inspection"), "fieldname": "inspection_required", "fieldtype": "Int", "width": 110},
		{"label": _("Readiness"), "fieldname": "readiness", "fieldtype": "Data", "width": 190},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "HTML", "width": 150},
	]


def data(filters):
	conditions = {"docstatus": 1, "is_active": 1}
	boms = frappe.get_all("BOM", filters=conditions, fields=["name", "item", "quality_inspection_template", "inspection_required"])
	if not boms:
		return []

	drawings = set()
	for f in frappe.get_all(
		"File",
		filters={"attached_to_doctype": "BOM", "attached_to_name": ("in", [b.name for b in boms])},
		fields=["attached_to_name", "file_name"],
	):
		if (f.file_name or "").rsplit(".", 1)[-1].lower() in DRAWING_EXTENSIONS:
			drawings.add(f.attached_to_name)

	drawing_templates = set(
		frappe.get_all(
			"Item Quality Inspection Parameter",
			filters={"parenttype": "Quality Inspection Template", "custom_row_type": ("is", "set")},
			pluck="parent",
			distinct=True,
		)
	)
	templates_by_item: dict[str, list[str]] = {}
	for t in frappe.get_all(
		"Quality Inspection Template",
		filters={"name": ("in", list(drawing_templates) or [""]), "custom_superseded_by": ("is", "not set")},
		fields=["name", "custom_item"],
	):
		templates_by_item.setdefault(t.custom_item, []).append(t.name)

	per_item: dict[str, dict] = {}
	for b in boms:
		row = per_item.setdefault(b.item, {"item": b.item, "boms": 0, "boms_with_drawing": 0, "boms_tagged": 0, "inspection_required": 0})
		row["boms"] += 1
		row["boms_with_drawing"] += b.name in drawings
		row["boms_tagged"] += b.quality_inspection_template in drawing_templates
		row["inspection_required"] += bool(b.inspection_required)

	items = {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters={"name": ("in", list(per_item))},
			fields=["name", "item_name", "item_group", "quality_inspection_template", "disabled"],
		)
	}
	out = []
	for code, row in per_item.items():
		item = items.get(code)
		if not item or item.disabled:
			continue
		if filters.get("item_group") and item.item_group != filters["item_group"]:
			continue
		row.update(item_name=item.item_name, item_group=item.item_group, item_template=item.quality_inspection_template)
		row["templates"] = ", ".join(templates_by_item.get(code, []))
		if row["boms_tagged"]:
			row["readiness"] = _("Tagged")
		elif row["templates"]:
			row["readiness"] = _("Template built, not tagged")
		elif row["boms_with_drawing"]:
			row["readiness"] = _("Drawing found, no template")
		else:
			row["readiness"] = _("No drawing found")
		if filters.get("readiness") and row["readiness"] != _(filters["readiness"]):
			continue
		if row["templates"]:
			first = row["templates"].split(", ")[0]
			row["action"] = f'<a href="/app/quality-inspection-template/{quote(first)}">{_("Open template")}</a>'
		else:
			# a new template with the item filled in; the drawing is picked after the first save
			row["action"] = f'<a href="/app/quality-inspection-template/new?custom_item={quote(code)}">{_("Build template")}</a>'

		out.append(row)
	order = {_("Tagged"): 0, _("Template built, not tagged"): 1, _("Drawing found, no template"): 2, _("No drawing found"): 3}
	out.sort(key=lambda r: (order[r["readiness"]], r["item_group"] or "", r["item"]))
	return out
