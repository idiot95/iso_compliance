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
	ensure_desk_registration()
	ensure_naming_rules()


def after_migrate():
	ensure_workflow_states()
	ensure_desk_registration()
	ensure_naming_rules()


def ensure_naming_rules():
	"""A record that fills a controlled form is numbered as that form.

	Management Review minutes are Quality Meetings; the master document
	register knows the minutes as FRM-024, so the meeting records carry that
	identity: HCCPL/QMS/FRM-024-0001, 0002... A Document Naming Rule is
	additive site configuration -- deleting it reverts naming untouched.
	"""
	if frappe.db.exists("Document Naming Rule", {"document_type": "Quality Meeting", "disabled": 0}):
		return
	frappe.get_doc(
		{
			"doctype": "Document Naming Rule",
			"document_type": "Quality Meeting",
			"prefix": "HCCPL/QMS/FRM-024-",
			"prefix_digits": 4,
			"priority": 10,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	print("iso_compliance: naming rule created for Quality Meeting (FRM-024)")


def ensure_desk_registration():
	"""Put ISO Compliance in the ERPNext desk, and keep it there.

	Frappe 16 builds the desk grid and the workspace switcher from Desktop Icon
	and Workspace Sidebar records, grouped by their `app` field. For this module
	to be listed alongside Assets or Quality -- rather than in a separate app
	silo the way v16 files third-party apps -- those records must say
	`app: "erpnext"`. But migrate's orphan sweep looks for each record's source
	file in the app it *claims* (frappe.get_app_path(record.app)), finds nothing
	of ours in erpnext/, and deletes both records on every migrate.

	So this hook runs after that sweep and re-imports the two files this app
	ships. Idempotent, self-healing, and entirely contained in the app.
	"""
	import os

	from frappe.modules.import_file import import_file_by_path

	for folder, filename in (
		("workspace_sidebar", "iso_compliance.json"),
		("desktop_icon", "iso_compliance.json"),
	):
		path = os.path.join(frappe.get_app_path("iso_compliance"), folder, filename)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True)
	frappe.db.commit()


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
