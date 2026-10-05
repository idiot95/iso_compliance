# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-006 step 3: a batch of incoming material knows who supplied it.

ERPNext ships `Batch.supplier` and creates the batch itself during the goods
receipt, but never fills the field: of 355 batches born from Purchase Receipts,
not one recorded a supplier. The batch is how identity travels into production --
it is what a Stock Entry selects and what a traceability question starts from --
so a batch that cannot name its supplier breaks the chain at its first link.

The field is ERPNext's own; this only populates it, from the receipt the batch
already points at.
"""

import frappe


def before_insert(doc, method=None):
	set_supplier_from_source(doc)


def set_supplier_from_source(doc) -> bool:
	"""Copy the supplier off the source receipt. Returns True if it set anything."""
	if doc.get("supplier") or doc.get("reference_doctype") != "Purchase Receipt":
		return False
	if not doc.get("reference_name"):
		return False

	supplier = frappe.db.get_value("Purchase Receipt", doc.reference_name, "supplier")
	if not supplier:
		return False

	doc.supplier = supplier
	return True
