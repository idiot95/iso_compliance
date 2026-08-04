# Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Configuration this app needs in order to work, created automatically.

Everything here is idempotent and additive, so it can run on every migrate. It
exists so that installing the app on production requires no manual setup: the
alternative is a checklist of records somebody has to create by hand, which is
exactly the kind of undocumented drift this app was written to stop.

Note what is *not* here. Controlled Document Types and the document set itself
are seed data, loaded by an explicit command, because putting them in a migrate
hook would mean a routine upgrade silently writing 93 documents into production.
"""

import frappe

from iso_compliance.seed.controlled_documents import WORKFLOW_STATES


def after_install():
	ensure_workflow_states()


def after_migrate():
	ensure_workflow_states()


def ensure_workflow_states():
	"""Create the document lifecycle states.

	Frappe ships only Open, Rejected, Approved and Pending. Controlled Document
	links its status to Workflow State, so the rest have to exist before a
	document can carry a status.
	"""
	created = []
	for state, style in WORKFLOW_STATES:
		if frappe.db.exists("Workflow State", state):
			continue
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
		).insert(ignore_permissions=True)
		created.append(state)

	if created:
		frappe.db.commit()
		print(f"iso_compliance: created workflow states {', '.join(created)}")

	return created
