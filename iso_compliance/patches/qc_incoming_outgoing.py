# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""SOP-006: the Item Group inspection tick becomes two (developer, 2026-11-26).

"Incoming inspection required" (the existing field) covers purchase receipts;
"Outgoing (final) inspection required" covers finished production. Every group
ticked today gets both, so nothing changes until Quality unticks one.
"""

import frappe

from iso_compliance.overrides.inspection_flow import INCOMING, OUTGOING, create_fields


def execute():
	create_fields()
	frappe.clear_cache(doctype="Item Group")
	if frappe.get_all("Item Group", filters={OUTGOING: 1}, limit=1):
		return  # already decided on this site
	groups = frappe.get_all("Item Group", filters={INCOMING: 1}, pluck="name")
	for g in groups:
		frappe.db.set_value("Item Group", g, OUTGOING, 1, update_modified=False)
	print(f"iso_compliance: outgoing inspection ticked on item groups {', '.join(groups)}")
