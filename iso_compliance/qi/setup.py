# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Starter records for drawing-based inspection. Idempotent: anything that
already exists belongs to Quality and is never touched."""

import frappe

#: (method, unit, material property). Conditions and instruments are left for
#: Quality to fill: the set values differ by grade and customer.
STARTER_TEST_METHODS = (
	("Contact voltage drop (mV drop)", "mV", 0),
	("Shunt pull-out force", "N", 0),
	("Hardness", "", 1),
	("Specific electrical resistivity", "µΩ·m", 1),
	("Apparent density", "g/cm³", 1),
	("Flexural strength", "MPa", 1),
	("Insulation resistance", "MΩ", 0),
	("High-voltage withstand", "kV", 0),
	("Spring force at working length", "N", 0),
	("Spring permanent set", "mm", 0),
	("Holder spring pressure", "", 0),
)

#: Units as they are printed on drawings and certificates. Rows and Test
#: Methods link to UOM, so these must exist; ERPNext ships only the long names.
INSPECTION_UOMS = (
	"mm", "µm", "°", "N", "kV", "V", "mV", "A", "Ω", "mΩ", "MΩ", "µΩ·m", "MPa", "g/cm³",
	"MS/m", "% IACS", "HRB", "HRC", "Shore A", "Shore D", "kg", "g", "%",
)

#: Stage → work instruction, as SOP-006/WI numbering has them.
STAGE_WI = (
	("Incoming", "HCCPL/QMS/WI-002"),
	("In Process", "HCCPL/QMS/WI-008"),
	("Final", "HCCPL/QMS/WI-009"),
)


def ensure_qi_setup():
	ensure_uoms()
	ensure_test_methods()
	ensure_stage_wi()
	# after fixtures: the Inspection Plan tab must exist before fields move into it
	from iso_compliance.qi.custom_fields import ensure_layout_order

	ensure_layout_order()


def ensure_uoms():
	for name in INSPECTION_UOMS:
		if not frappe.db.exists("UOM", name):
			frappe.get_doc({"doctype": "UOM", "uom_name": name, "enabled": 1}).insert(ignore_permissions=True)


def ensure_test_methods():
	for name, unit, material in STARTER_TEST_METHODS:
		if frappe.db.exists("Test Method", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Test Method",
				"method_name": name,
				"result_unit": unit,
				"material_property": material,
			}
		).insert(ignore_permissions=True)


def ensure_stage_wi():
	settings = frappe.get_single("Inspection Settings")
	if settings.stage_wi:
		return
	for stage, wi in STAGE_WI:
		if frappe.db.exists("Controlled Document", wi):
			settings.append("stage_wi", {"stage": stage, "controlled_document": wi})
	if not settings.default_sample_percent:
		settings.default_sample_percent = 5
	if not settings.calibration_overdue_policy:
		settings.calibration_overdue_policy = "Warn"
	settings.save(ignore_permissions=True)
