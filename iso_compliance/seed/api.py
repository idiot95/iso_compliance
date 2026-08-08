# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Seed loading without a shell, for benches where there is no bench console.

On a shared Frappe Cloud bench nobody can run `bench execute`, so the explicit
import step the seed design insists on needs another explicit door. These two
methods are it: whitelisted POST, System Manager only, called from the desk
(browser console or a client script):

    frappe.call({method: "iso_compliance.seed.api.import_all"})
        .then(r => console.log(r.message))

Still deliberately not a migrate hook, and still POST-only: seeding must be an
action somebody takes, never a side effect of an upgrade or of visiting a URL.
"""

import frappe

from iso_compliance.seed import controlled_documents, qms_registers


@frappe.whitelist(methods=["POST"])
def import_all() -> dict:
	"""Load the document set and the register content. Idempotent: existing
	records are skipped, so calling this twice creates nothing the second time."""
	frappe.only_for("System Manager")
	documents = controlled_documents.import_seed()
	registers = qms_registers.import_registers()
	return {"documents": documents, "registers": registers}


@frappe.whitelist(methods=["POST"])
def purge_all() -> dict:
	"""Remove everything the imports created, by batch token. Records created
	by hand are untouched. Registers purge first, then documents, mirroring the
	install guide's order."""
	frappe.only_for("System Manager")
	registers = qms_registers.purge_registers()
	documents = controlled_documents.purge_seed()
	return {"documents": documents, "registers": registers}
