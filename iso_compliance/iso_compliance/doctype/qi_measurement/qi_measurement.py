# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""One measured value: inspection × row (balloon) × sample.

Standalone rather than a child table so each tap on the inspector screen is a
single upsert -- no re-save of the inspection, no clash between two tablets
working the same lot -- and so SPC can read it directly."""

import frappe
from frappe.model.document import Document


class QIMeasurement(Document):
	pass


def on_doctype_update():
	# One value per sample per row per inspection: save_measurement upserts on this.
	frappe.db.add_unique("QI Measurement", ["quality_inspection", "row_key", "sample_no"], constraint_name="qi_row_sample")
