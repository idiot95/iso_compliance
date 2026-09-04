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
	ensure_review_chain()


def after_migrate():
	ensure_workflow_states()
	ensure_desk_registration()
	ensure_naming_rules()
	ensure_review_chain()


#: The sequential review chain on FRM-036 (SOP-004): who may clear each stage.
REVIEW_CHAIN_ROLES = ("Technical Reviewer", "Costing Reviewer", "Commercial Reviewer")

REVIEW_CHAIN_STATES = (
	("Technical Review", "Warning"),
	("Costing Review", "Warning"),
	("Commercial Review", "Primary"),
)


def ensure_review_chain():
	"""The Techno-Commercial Review workflow: roles, states, transitions.

	Draft -> Technical Review -> Costing Review -> Commercial Review ->
	Approved (submitted). Each forward step belongs to one reviewer role, so
	the workflow history is the signature block of the paper form; Quality
	Manager can drive any step, because a small organisation cannot stall an
	order on an unfilled seat. Send Back returns to Draft from any stage.
	"""
	for role in REVIEW_CHAIN_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)

	for state, style in REVIEW_CHAIN_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)

	for action in (
		"Send for Technical Review",
		"Clear Technical Review",
		"Clear Costing Review",
		"Complete Review",
		"Send Back",
	):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", "Techno-Commercial Review"):
		# Keep the alert on for sites that created the workflow before it
		# defaulted on: each transition mails whoever holds the next stage.
		frappe.db.set_value("Workflow", "Techno-Commercial Review", "send_email_alert", 1)
		frappe.db.commit()
		return

	forward = (
		("Draft", "Send for Technical Review", "Technical Review", "Sales User"),
		("Technical Review", "Clear Technical Review", "Costing Review", "Technical Reviewer"),
		("Costing Review", "Clear Costing Review", "Commercial Review", "Costing Reviewer"),
		("Commercial Review", "Complete Review", "Approved", "Commercial Reviewer"),
	)
	send_back = (
		("Technical Review", "Technical Reviewer"),
		("Costing Review", "Costing Reviewer"),
		("Commercial Review", "Commercial Reviewer"),
	)
	transitions = []
	for state, action, next_state, role in forward:
		for allowed in (role, "Quality Manager"):
			transitions.append(
				{"state": state, "action": action, "next_state": next_state, "allowed": allowed}
			)
	for state, role in send_back:
		for allowed in (role, "Quality Manager"):
			transitions.append(
				{"state": state, "action": "Send Back", "next_state": "Draft", "allowed": allowed}
			)

	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": "Techno-Commercial Review",
			"document_type": "Techno Commercial Review",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 1,
			"states": [
				{"state": "Draft", "doc_status": "0", "allow_edit": "Sales User"},
				{"state": "Technical Review", "doc_status": "0", "allow_edit": "Technical Reviewer"},
				{"state": "Costing Review", "doc_status": "0", "allow_edit": "Costing Reviewer"},
				{"state": "Commercial Review", "doc_status": "0", "allow_edit": "Commercial Reviewer"},
				{"state": "Approved", "doc_status": "1", "allow_edit": "Quality Manager"},
			],
			"transitions": transitions,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	print("iso_compliance: created Techno-Commercial Review workflow (sequential review chain)")


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
