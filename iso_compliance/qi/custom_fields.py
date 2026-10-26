# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Phase A custom fields on Quality Inspection Template and its rows
(EXTERNAL_CHANGES.md §3, approved 2026-10-12).

They ship as fixtures (module "ISO Compliance"); this module is how they were
first created on the site and how a developer re-creates them:

    bench --site <site> execute iso_compliance.qi.custom_fields.create_phase_a
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from iso_compliance.qi import tolerance as T

MODULE = "ISO Compliance"
PROPERTY_SETTER = "BOM-quality_inspection_template-allow_on_submit"
STAGE_FIELDS = (
	("custom_stage_incoming", "Incoming"),
	("custom_stage_in_process", "In Process"),
	("custom_stage_final", "Final"),
	("custom_stage_fai", "FAI"),
	("custom_stage_type_test", "Type Test"),
)
GDT_SYMBOLS = (
	"Flatness", "Straightness", "Circularity", "Cylindricity", "Perpendicularity", "Parallelism",
	"Angularity", "Position", "Concentricity", "Symmetry", "Circular runout", "Total runout",
	"Profile of a line", "Profile of a surface",
)

DIM = 'eval:doc.custom_row_type=="Dimension" || doc.custom_row_type=="Test"'


def _tt(*types):
	return "eval:[" + ",".join(f'"{t}"' for t in types) + "].includes(doc.custom_tolerance_type)"


TEMPLATE_FIELDS = [
	# folded once the plan has characteristics: open while it is being set up
	dict(fieldname="custom_drawing_section", fieldtype="Section Break", label="Item and drawing",
	     insert_after="quality_inspection_template_name", collapsible=1,
	     collapsible_depends_on="eval:doc.__islocal || !doc.custom_item || !(doc.item_quality_inspection_parameter || []).some((r) => r.custom_row_type)"),
	dict(fieldname="custom_item", fieldtype="Link", options="Item", label="Item",
	     insert_after="custom_drawing_section",
	     description="The drawing is picked from this item's BOMs and attachments."),
	dict(fieldname="custom_drawing", fieldtype="Attach", label="Drawing", insert_after="custom_item"),
	dict(fieldname="custom_drawing_hash", fieldtype="Data", label="Drawing hash", hidden=1,
	     read_only=1, no_copy=1, insert_after="custom_drawing"),
	dict(fieldname="custom_drawing_pages", fieldtype="Long Text", label="Drawing pages", hidden=1,
	     read_only=1, no_copy=1, insert_after="custom_drawing_hash"),
	dict(fieldname="custom_drawing_source", fieldtype="Select", label="Drawing source",
	     options="\nCustomer\nIn-house\nNone", insert_after="custom_drawing_pages"),
	dict(fieldname="custom_customer", fieldtype="Link", options="Customer", label="Customer",
	     depends_on='eval:doc.custom_drawing_source=="Customer"', insert_after="custom_drawing_source"),
	dict(fieldname="custom_drawing_cb", fieldtype="Column Break", insert_after="custom_customer"),
	dict(fieldname="custom_drawing_no", fieldtype="Data", label="Drawing number", insert_after="custom_drawing_cb"),
	dict(fieldname="custom_drawing_revision", fieldtype="Data", label="Revision", insert_after="custom_drawing_no"),
	dict(fieldname="custom_general_tolerance", fieldtype="Select", label="General tolerance, linear and angular (ISO 2768-1)",
	     options="None\nISO 2768-f\nISO 2768-m\nISO 2768-c\nISO 2768-v", default="None",
	     insert_after="custom_drawing_revision",
	     description="From the drawing's title block. Applies to dimensions with no tolerance of their own."),
	dict(fieldname="custom_general_geometric", fieldtype="Select", label="General tolerance, geometric (ISO 2768-2)",
	     options="None\nH\nK\nL", default="None", insert_after="custom_general_tolerance"),
	dict(fieldname="custom_product_wi", fieldtype="Link", options="Controlled Document",
	     label="Product work instruction", insert_after="custom_general_geometric"),
	dict(fieldname="custom_locked", fieldtype="Check", label="Locked", read_only=1, no_copy=1,
	     insert_after="custom_product_wi",
	     description="Set when the first inspection on this template is submitted. Drawing, balloons, limits and stages can then only change through New Revision."),
	dict(fieldname="custom_superseded_by", fieldtype="Link", options="Quality Inspection Template",
	     label="Superseded by", read_only=1, no_copy=1, insert_after="custom_locked"),
	dict(fieldname="custom_one_off", fieldtype="Check", label="One-off plan", read_only=1, no_copy=1,
	     insert_after="custom_superseded_by",
	     description="Begun in an inspection of an item that had no plan, with its characteristics added there. "
	                 "Save it against the item or its item group from the inspection to use it again."),
	dict(fieldname="custom_used_by", fieldtype="HTML", label="Used by", insert_after="custom_one_off"),
]

ROW_FIELDS = [
	dict(fieldname="custom_row_type", fieldtype="Select", label="Row type",
	     options="\nDimension\nTest\nVisual\nMaterial", insert_after="parameter_group", in_list_view=1, columns=1,
	     description="Leave blank on templates that are not drawing templates."),
	dict(fieldname="custom_balloon_no", fieldtype="Data", label="No.", insert_after="custom_row_type",
	     in_list_view=1, columns=1, depends_on="custom_row_type"),
	dict(fieldname="custom_spec_text", fieldtype="Data", label="As printed", insert_after="custom_balloon_no",
	     depends_on="custom_row_type"),
	dict(fieldname="custom_class", fieldtype="Select", label="Class", options="\nCTQ\nMajor\nMinor",
	     insert_after="custom_spec_text", depends_on="custom_row_type"),
	dict(fieldname="custom_unit", fieldtype="Link", options="UOM", label="Unit", insert_after="custom_class",
	     depends_on="custom_row_type"),
	# tolerance
	dict(fieldname="custom_tolerance_section", fieldtype="Section Break", label="Tolerance",
	     insert_after="custom_unit", depends_on=DIM),
	dict(fieldname="custom_tolerance_type", fieldtype="Select", label="Tolerance type",
	     options="\n" + "\n".join(T.TYPES), insert_after="custom_tolerance_section",
	     description="Limits, Maximum only and Minimum only use Min/Max Value directly."),
	dict(fieldname="custom_nominal", fieldtype="Float", label="Nominal", precision="6",
	     insert_after="custom_tolerance_type",
	     depends_on=_tt(T.SYMMETRIC, T.DEVIATIONS, T.ISO_FIT, T.GENERAL, T.ANGLE, T.REFERENCE)),
	dict(fieldname="custom_tol", fieldtype="Float", label="± Tolerance / zone", precision="6",
	     insert_after="custom_nominal", depends_on=_tt(T.SYMMETRIC, T.ANGLE, T.GEOMETRIC),
	     description="Angles in decimal degrees. Geometric: the tolerance zone."),
	dict(fieldname="custom_upper_dev", fieldtype="Float", label="Upper deviation", precision="6",
	     insert_after="custom_tol", depends_on=_tt(T.DEVIATIONS)),
	dict(fieldname="custom_lower_dev", fieldtype="Float", label="Lower deviation", precision="6",
	     insert_after="custom_upper_dev", depends_on=_tt(T.DEVIATIONS)),
	dict(fieldname="custom_fit_class", fieldtype="Data", label="Fit class", insert_after="custom_lower_dev",
	     depends_on=_tt(T.ISO_FIT), description="e.g. H11, h9, js7"),
	dict(fieldname="custom_tolerance_cb", fieldtype="Column Break", insert_after="custom_fit_class"),
	dict(fieldname="custom_gdt_symbol", fieldtype="Select", label="GD&T symbol",
	     options="\n" + "\n".join(GDT_SYMBOLS), insert_after="custom_tolerance_cb", depends_on=_tt(T.GEOMETRIC)),
	dict(fieldname="custom_datums", fieldtype="Data", label="Datums", insert_after="custom_gdt_symbol",
	     depends_on=_tt(T.GEOMETRIC)),
	dict(fieldname="custom_bonus_tol", fieldtype="Float", label="MMC bonus", precision="6",
	     insert_after="custom_datums", depends_on=_tt(T.GEOMETRIC),
	     description="Recorded; not yet added to the zone."),
	dict(fieldname="custom_test_method", fieldtype="Link", options="Test Method", label="Test method",
	     insert_after="custom_bonus_tol", depends_on='eval:doc.custom_row_type=="Test"'),
	dict(fieldname="custom_conditions", fieldtype="Code", options="JSON", label="Condition overrides",
	     insert_after="custom_test_method", depends_on='eval:doc.custom_row_type=="Test"',
	     description='Per-part set values, e.g. {"Current density": 12}'),
	dict(fieldname="custom_instruments", fieldtype="Small Text", label="Instruments",
	     insert_after="custom_conditions", depends_on="custom_row_type",
	     description="Measuring instrument Assets the inspector may choose from, one per line."),
	# when
	dict(fieldname="custom_when_section", fieldtype="Section Break", label="When and how many",
	     insert_after="custom_instruments", depends_on="custom_row_type"),
	*[
		dict(fieldname=f, fieldtype="Check", label=lbl, insert_after=prev)
		for (f, lbl), prev in zip(STAGE_FIELDS, ["custom_when_section"] + [s[0] for s in STAGE_FIELDS[:-1]])
	],
	dict(fieldname="custom_when_cb", fieldtype="Column Break", insert_after="custom_stage_type_test"),
	dict(fieldname="custom_frequency", fieldtype="Select", label="Frequency",
	     options="Every lot\nFirst article only\nEvery N lots\nEvery N months", default="Every lot",
	     insert_after="custom_when_cb"),
	dict(fieldname="custom_frequency_n", fieldtype="Int", label="N", insert_after="custom_frequency",
	     depends_on='eval:["Every N lots","Every N months"].includes(doc.custom_frequency)'),
	dict(fieldname="custom_sampling", fieldtype="Select", label="Sampling",
	     options="Lot sample\nFixed number", default="Lot sample", insert_after="custom_frequency_n"),
	dict(fieldname="custom_fixed_count", fieldtype="Int", label="Pieces", insert_after="custom_sampling",
	     depends_on='eval:doc.custom_sampling=="Fixed number"'),
	dict(fieldname="custom_position", fieldtype="Data", label="Position on drawing", hidden=1,
	     insert_after="custom_fixed_count"),
]


def create_phase_a():
	fields = {
		"Quality Inspection Template": TEMPLATE_FIELDS,
		"Item Quality Inspection Parameter": ROW_FIELDS,
	}
	for rows in fields.values():
		for f in rows:
			f["module"] = MODULE
	create_custom_fields(fields, update=True)
	if not frappe.db.exists("Property Setter", PROPERTY_SETTER):
		make_property_setter(
			"BOM", "quality_inspection_template", "allow_on_submit", 1, "Check",
			validate_fields_for_doctype=False, is_system_generated=False,
		)
	frappe.db.commit()


# ---- Phase B (EXTERNAL_CHANGES.md §4, approved 2026-10-12) ----

STAGES = "Incoming\nIn Process\nFinal\nFAI\nType Test"
DISPOSITIONS = "\nAccepted\nAccept under Concession\nRework\nRejected"

INSPECTION_FIELDS = [
	dict(fieldname="custom_inspection_section", fieldtype="Section Break", label="Drawing inspection",
	     insert_after="manual_inspection", collapsible=1,
	     collapsible_depends_on="eval:doc.custom_stage || doc.custom_disposition"),
	dict(fieldname="custom_stage", fieldtype="Select", label="Stage", options="\n" + STAGES,
	     insert_after="custom_inspection_section"),
	dict(fieldname="custom_lot_qty", fieldtype="Float", label="Lot quantity", insert_after="custom_stage"),
	dict(fieldname="custom_work_order", fieldtype="Link", options="Work Order", label="Work Order",
	     read_only=1, insert_after="custom_lot_qty"),
	dict(fieldname="custom_customer", fieldtype="Link", options="Customer", label="Customer",
	     read_only=1, insert_after="custom_work_order"),
	dict(fieldname="custom_inspection_cb", fieldtype="Column Break", insert_after="custom_customer"),
	dict(fieldname="custom_drawing_no", fieldtype="Data", label="Drawing no.", read_only=1,
	     insert_after="custom_inspection_cb"),
	dict(fieldname="custom_drawing_revision", fieldtype="Data", label="Drawing revision", read_only=1,
	     insert_after="custom_drawing_no"),
	dict(fieldname="custom_drawing", fieldtype="Attach", label="Drawing", read_only=1,
	     insert_after="custom_drawing_revision"),
	dict(fieldname="custom_disposition_section", fieldtype="Section Break", label="Disposition",
	     insert_after="custom_drawing", depends_on="custom_stage"),
	dict(fieldname="custom_disposition", fieldtype="Select", label="Disposition", options=DISPOSITIONS,
	     insert_after="custom_disposition_section",
	     description="Accept under Concession is recorded with a warning; it needs no approval."),
	dict(fieldname="custom_concession_no", fieldtype="Data", label="Concession no.",
	     insert_after="custom_disposition", depends_on='eval:doc.custom_disposition=="Accept under Concession"'),
	dict(fieldname="custom_non_conformance", fieldtype="Link", options="Non Conformance",
	     label="Non Conformance", insert_after="custom_concession_no"),
	dict(fieldname="custom_measurements_section", fieldtype="Section Break", label="Measurements",
	     insert_after="custom_non_conformance", depends_on="custom_stage", collapsible=1),
	dict(fieldname="custom_measurements_html", fieldtype="HTML", label="Measurements",
	     insert_after="custom_measurements_section"),
	dict(fieldname="custom_conditions", fieldtype="Table", options="QI Condition", label="Test conditions",
	     insert_after="custom_measurements_html"),
	dict(fieldname="custom_work_instructions", fieldtype="Table", options="QI Work Instruction",
	     label="Work instructions", read_only=1, insert_after="custom_conditions"),
	dict(fieldname="custom_created_entry", fieldtype="Data", label="Created Stock Entry", hidden=1,
	     read_only=1, no_copy=1, insert_after="custom_work_instructions"),
]

READING_FIELDS = [
	dict(fieldname="custom_drawing_section", fieldtype="Section Break", label="Drawing row",
	     insert_after="parameter_group", depends_on="custom_row_type", collapsible=1),
	dict(fieldname="custom_row_type", fieldtype="Data", label="Row type", read_only=1,
	     insert_after="custom_drawing_section"),
	dict(fieldname="custom_balloon_no", fieldtype="Data", label="No.", read_only=1,
	     insert_after="custom_row_type", in_list_view=1, columns=1),
	dict(fieldname="custom_class", fieldtype="Data", label="Class", read_only=1, insert_after="custom_balloon_no"),
	dict(fieldname="custom_spec_text", fieldtype="Data", label="As printed", read_only=1, insert_after="custom_class"),
	dict(fieldname="custom_tolerance_type", fieldtype="Data", label="Tolerance type", read_only=1,
	     insert_after="custom_spec_text"),
	dict(fieldname="custom_unit", fieldtype="Data", label="Unit", read_only=1, insert_after="custom_tolerance_type"),
	dict(fieldname="custom_test_method", fieldtype="Link", options="Test Method", label="Test method",
	     read_only=1, insert_after="custom_unit"),
	dict(fieldname="custom_reading_cb", fieldtype="Column Break", insert_after="custom_test_method"),
	dict(fieldname="custom_sample_count", fieldtype="Int", label="Samples required", read_only=1,
	     insert_after="custom_reading_cb"),
	dict(fieldname="custom_n", fieldtype="Int", label="Measured", read_only=1, insert_after="custom_sample_count"),
	dict(fieldname="custom_obs_min", fieldtype="Float", label="Observed min", precision="6", read_only=1,
	     insert_after="custom_n"),
	dict(fieldname="custom_obs_max", fieldtype="Float", label="Observed max", precision="6", read_only=1,
	     insert_after="custom_obs_min"),
	dict(fieldname="custom_mean", fieldtype="Float", label="Mean", precision="6", read_only=1,
	     insert_after="custom_obs_max"),
	dict(fieldname="custom_out_of_spec", fieldtype="Int", label="Out of spec", read_only=1,
	     insert_after="custom_mean"),
	dict(fieldname="custom_instrument", fieldtype="Link", options="Asset", label="Instrument", read_only=1,
	     insert_after="custom_out_of_spec"),
	dict(fieldname="custom_cal_due", fieldtype="Date", label="Calibration due", read_only=1,
	     insert_after="custom_instrument"),
	dict(fieldname="custom_cal_cert", fieldtype="Data", label="Calibration certificate", read_only=1,
	     insert_after="custom_cal_due"),
]


def create_phase_b():
	fields = {"Quality Inspection": INSPECTION_FIELDS, "Quality Inspection Reading": READING_FIELDS}
	for rows in fields.values():
		for f in rows:
			f["module"] = MODULE
	create_custom_fields(fields, update=True)
	frappe.db.commit()


# ---- Layout (developer's requests, 2026-10-13; EXTERNAL_CHANGES.md) ----

LAYOUT_TEMPLATE_FIELDS = [
	dict(fieldname="custom_bom", fieldtype="Link", options="BOM", label="BOM", insert_after="custom_item",
	     description="The drawing is picked from this BOM's attachments."),
	dict(fieldname="custom_drawing_file", fieldtype="Select", label="Drawing file", insert_after="custom_bom",
	     description="Choosing one attaches it to the template."),
	dict(fieldname="custom_rows_section", fieldtype="Section Break", label="Characteristics", insert_after="custom_used_by"),
]

#: row field -> (in_list_view, columns) on the template's grid
ROW_GRID = {
	"custom_balloon_no": (1, 1),
	"custom_row_type": (0, 1),
	"custom_spec_text": (1, 2),
	"custom_tolerance_type": (1, 1),
	"custom_class": (1, 1),
}
#: (field, property, value, type) property setters on the native row fields
ROW_PROPERTY_SETTERS = [
	("specification", "columns", "2", "Int"),
	("value", "columns", "1", "Int"),
	("min_value", "columns", "1", "Int"),
	("max_value", "columns", "1", "Int"),
	("numeric", "in_list_view", "0", "Check"),
]

BOM_PLAN_FIELDS = [
	dict(fieldname="custom_inspection_plan_tab", fieldtype="Tab Break", label="Inspection Plan"),
	dict(fieldname="custom_inspection_plan_html", fieldtype="HTML", label="Inspection plan",
	     insert_after="quality_inspection_template"),
]
ITEM_PLAN_FIELDS = [
	dict(fieldname="custom_inspection_plan_html", fieldtype="HTML", label="Inspection plan",
	     insert_after="quality_inspection_template"),
]
BOM_MOVED = ("inspection_required", "quality_inspection_template")

#: every Property Setter this layout adds (hooks.py fixture filter lists them)
LAYOUT_PROPERTY_SETTERS = (
	[f"Item Quality Inspection Parameter-{f}-{p}" for f, p, _v, _t in ROW_PROPERTY_SETTERS]
	+ ["BOM-quality_inspection_template-depends_on",
	   "Quality Inspection Template-item_quality_inspection_parameter-reqd"]
)


def _setter(doctype, field, prop, value, ptype, for_doctype=False):
	name = f"{doctype}-{'main' if for_doctype else field}-{prop}"
	if frappe.db.exists("Property Setter", name):
		frappe.db.set_value("Property Setter", name, "value", value)
	else:
		make_property_setter(doctype, field, prop, value, ptype, for_doctype=for_doctype,
		                     validate_fields_for_doctype=False, is_system_generated=False)


def create_layout():
	fields = {
		"Quality Inspection Template": LAYOUT_TEMPLATE_FIELDS,
		"BOM": [dict(BOM_PLAN_FIELDS[0], insert_after=_last_before("BOM", "connections_tab")), BOM_PLAN_FIELDS[1]],
		"Item": ITEM_PLAN_FIELDS,
	}
	for rows in fields.values():
		for f in rows:
			f["module"] = MODULE
	create_custom_fields(fields, update=True)

	for fieldname, (in_list, cols) in ROW_GRID.items():
		name = f"Item Quality Inspection Parameter-{fieldname}"
		frappe.db.set_value("Custom Field", name, {"in_list_view": in_list, "columns": cols})
	for field, prop, value, ptype in ROW_PROPERTY_SETTERS:
		_setter("Item Quality Inspection Parameter", field, prop, value, ptype)

	_setter("BOM", "quality_inspection_template", "depends_on", "", "Data")
	# A drawing template is saved with its drawing before it has rows (they come
	# from the balloons); qi.template.validate still requires rows on any
	# template without an Item, i.e. every template that isn't a drawing one.
	_setter("Quality Inspection Template", "item_quality_inspection_parameter", "reqd", "0", "Check")
	move_bom_inspection_fields()
	frappe.clear_cache()
	frappe.db.commit()


#: (doctype, field, place it right after this field; None = first). Applied to
#: each site's own field order -- BOM and Item already carry a Customize Form
#: order there that no app ships -- so only these fields move.
LAYOUT_MOVES = [
	("BOM", "inspection_required", "custom_inspection_plan_tab"),
	("BOM", "quality_inspection_template", "inspection_required"),
	("BOM", "custom_inspection_plan_html", "quality_inspection_template"),
	("Item", "custom_inspection_plan_html", "quality_inspection_template"),
	# template: Drawing first, the parameter table last, under "Characteristics"
	("Quality Inspection Template", "item_quality_inspection_parameter", "custom_rows_section"),
	# rows grid: Balloon is the first column
	("Item Quality Inspection Parameter", "custom_balloon_no", None),
]


def ensure_layout_order():
	"""Idempotent: run after every migrate (qi.setup), once fixtures exist."""
	for doctype in dict.fromkeys(d for d, _f, _a in LAYOUT_MOVES):
		frappe.clear_cache(doctype=doctype)
		order = [f.fieldname for f in frappe.get_meta(doctype, cached=False).fields]
		before = list(order)
		for dt, field, after in LAYOUT_MOVES:
			if dt != doctype or field not in order or (after and after not in order):
				continue
			order.remove(field)
			order.insert(order.index(after) + 1 if after else 0, field)
		if order != before:
			_setter(doctype, None, "field_order", frappe.as_json(order), "Data", for_doctype=True)
			frappe.clear_cache(doctype=doctype)


move_bom_inspection_fields = ensure_layout_order  # earlier name


def _last_before(doctype, fieldname):
	order = [f.fieldname for f in frappe.get_meta(doctype, cached=False).fields]
	return order[order.index(fieldname) - 1]


# ---- Phase E: incoming 3.1 values, in-process check points (2026-10-13) ----

PHASE_E_ROW_FIELDS = [
	dict(fieldname="custom_in_process_at", fieldtype="Select", label="In process, check at",
	     options="Every check\nFirst Check only\nFirst and Last Check", default="Every check",
	     insert_after="custom_stage_type_test", depends_on="custom_stage_in_process",
	     description="First Check: start of the Work Order's run. Random Check: during it. Last Check: its end."),
]
PHASE_E_INSPECTION_FIELDS = [
	dict(fieldname="custom_check_point", fieldtype="Select", label="Check point",
	     options="\nFirst Check\nRandom Check\nLast Check", insert_after="custom_stage",
	     depends_on='eval:doc.custom_stage=="In Process"'),
	dict(fieldname="custom_supplier_cert", fieldtype="Attach", label="Supplier's 3.1 certificate", read_only=1,
	     insert_after="custom_drawing", depends_on='eval:doc.custom_stage=="Incoming"',
	     description="From the Purchase Receipt; Material rows are read off it."),
]


def create_phase_e():
	fields = {"Item Quality Inspection Parameter": PHASE_E_ROW_FIELDS, "Quality Inspection": PHASE_E_INSPECTION_FIELDS}
	for rows in fields.values():
		for f in rows:
			f["module"] = MODULE
	create_custom_fields(fields, update=True)
	# Material: a property from the supplier's 3.1 certificate (E1)
	frappe.db.set_value("Custom Field", "Item Quality Inspection Parameter-custom_row_type",
	                    "options", "\nDimension\nTest\nVisual\nMaterial")
	frappe.clear_cache()
	frappe.db.commit()


# ---- Phase C2: 3.1 MTC by item group (developer, 2026-10-13) ----

C2_ITEM_GROUP_FIELDS = [
	dict(fieldname="custom_issue_mtc", fieldtype="Check", label="Issue 3.1 MTC at dispatch",
	     insert_after="custom_mtc_required",
	     description="Deliveries of items in this group (and its sub-groups) carry an EN 10204 3.1 Material "
	                 "Test Certificate, traced to the supplier's certificate."),
]


def create_phase_c2():
	for f in C2_ITEM_GROUP_FIELDS:
		f["module"] = MODULE
	create_custom_fields({"Item Group": C2_ITEM_GROUP_FIELDS}, update=True)
	frappe.db.commit()
