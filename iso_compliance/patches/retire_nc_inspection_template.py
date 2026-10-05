# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Retire the Quality Inspection Template that was really a nonconformance form.

Someone built "Non-Confirmative Material Report & CAPA" as an inspection
template, with three readings standing in for form fields:

    Nonconformance Description   numeric, min 0, max 0
    CA/PA Disposition            numeric, min 0, max 0
    Quantity Received            numeric, min 0, max 0

As an inspection template it cannot work -- every parameter is numeric with a
zero-width acceptable range, so any reading other than 0 fails -- and the job it
was reaching for now belongs to FRM-020 (Non Conformance) and FRM-021 (Quality
Action), which carry a description, a disposition from SOP-013 and a quantity as
real fields.

Deleted rather than hidden: Quality Inspection Template has no disabled flag, so
a template that stays on the site stays in every template dropdown.

Safe to run: the template is referenced by nothing. Checked before deleting
against all five link fields that point at it (Item, Item Group's default,
Quality Inspection, Job Card, Operation, BOM), and against readings recorded
under its parameter names. If anything references it by the time this runs, the
patch leaves it alone and says so -- a surprise reference means the assumption
has changed and that deserves a look, not a cascade.

The definition is recorded above so the template can be recreated by hand if
retiring it turns out to be wrong.
"""

import frappe

TEMPLATE = "Non-Confirmative Material Report & CAPA"

#: Every link field pointing at Quality Inspection Template, as a (doctype, field)
#: pair. Listed rather than discovered, so a new reference added upstream shows up
#: as a failed assumption here instead of being silently skipped.
REFERENCES = (
	("Item", "quality_inspection_template"),
	("Item Group", "custom_default_qi_template"),
	("Quality Inspection", "quality_inspection_template"),
	("Job Card", "quality_inspection_template"),
	("Operation", "quality_inspection_template"),
	("BOM", "quality_inspection_template"),
)


def execute():
	if not frappe.db.exists("Quality Inspection Template", TEMPLATE):
		return

	in_use = []
	for doctype, fieldname in REFERENCES:
		if not frappe.db.has_column(doctype, fieldname):
			continue
		count = frappe.db.count(doctype, {fieldname: TEMPLATE})
		if count:
			in_use.append(f"{doctype}.{fieldname}: {count}")

	if in_use:
		print(
			f"iso_compliance: kept Quality Inspection Template {TEMPLATE!r} -- "
			f"still referenced by {', '.join(in_use)}"
		)
		return

	frappe.delete_doc(
		"Quality Inspection Template",
		TEMPLATE,
		ignore_permissions=True,
		# Nothing points at it, so a link check is a query with a known answer.
		ignore_missing=True,
		delete_permanently=True,
	)
	print(
		f"iso_compliance: retired Quality Inspection Template {TEMPLATE!r} "
		f"(its job belongs to FRM-020 and FRM-021)"
	)
