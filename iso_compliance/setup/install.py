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

from iso_compliance.overrides.purchase_receipt import REJECTED_WAREHOUSE_NAME
from iso_compliance.seed.controlled_documents import WORKFLOW_STATES


def after_install():
	ensure_workflow_states()
	ensure_desk_registration()
	ensure_naming_rules()
	ensure_review_notifications()
	ensure_purchase_terms()
	ensure_supplier_evaluation_templates()
	ensure_rejected_warehouse()
	ensure_incoming_rejection_notification()


def after_migrate():
	ensure_workflow_states()
	ensure_desk_registration()
	ensure_naming_rules()
	ensure_review_notifications()
	ensure_purchase_terms()
	ensure_supplier_evaluation_templates()
	ensure_rejected_warehouse()
	ensure_incoming_rejection_notification()


#: The two FRM-005 templates a new site starts with: the nine weighted criteria
#: of the Supplier Evaluation Form (F-PUR-01) for Critical suppliers, a
#: condensed five for Non-Critical. Seeded once; Quality edits them afterwards.
SUPPLIER_EVALUATION_TEMPLATES = {
	"Critical": (
		12,
		(
			("Quality of supplied product / service", 25, "Acceptance % from receipts"),
			("On-time delivery / service", 20, "On-time % from receipts"),
			("Technical capability", 15, None),
			("Price / commercial competitiveness", 10, None),
			("Capacity / resource availability", 10, None),
			("Statutory / regulatory compliance", 5, None),
			("Management system / certifications", 5, None),
			("Communication & responsiveness", 5, None),
			("Corrective action effectiveness", 5, None),
		),
	),
	"Non-Critical": (
		24,
		(
			("Quality of supplied product / service", 30, "Acceptance % from receipts"),
			("On-time delivery / service", 25, "On-time % from receipts"),
			("Price / commercial competitiveness", 20, None),
			("Communication & responsiveness", 15, None),
			("Statutory / regulatory compliance", 10, None),
		),
	),
}


def ensure_supplier_evaluation_templates():
	"""Create the Critical and Non-Critical templates if missing. An existing
	template is never touched: once created it belongs to Quality."""
	created = []
	for category, (months, criteria) in SUPPLIER_EVALUATION_TEMPLATES.items():
		if frappe.db.exists("Supplier Evaluation Template", category):
			continue
		frappe.get_doc(
			{
				"doctype": "Supplier Evaluation Template",
				"category": category,
				"review_months": months,
				"criteria": [
					{"criterion": criterion, "weight": weight, "auto_rate": auto}
					for criterion, weight, auto in criteria
				],
			}
		).insert(ignore_permissions=True)
		created.append(category)
	if created:
		frappe.db.commit()
		print(f"iso_compliance: created supplier evaluation templates ({', '.join(created)})")


def ensure_purchase_terms():
	"""The standard quality requirements communicated to suppliers (8.4.3).

	One Terms and Conditions record, selectable on any Purchase Order, carrying
	the nine requirement lines of the Purchase Order source form (F-PUR-02
	Section C). A record, not schema -- deleting it reverts the site untouched.
	"""
	title = "Purchase Quality Requirements"
	if frappe.db.exists("Terms and Conditions", title):
		return
	terms = (
		"<p>The supplier shall comply with the following, as applicable to this order:</p>"
		"<ol>"
		"<li>Supply strictly to the quality specification and acceptance criteria stated against each item.</li>"
		"<li>Manufacture to the applicable drawing / technical specification revision referenced in this order.</li>"
		"<li>Carry out the inspection and testing required before despatch.</li>"
		"<li>Provide a certificate of conformity / test certificate with each consignment.</li>"
		"<li>Pack and preserve the goods to prevent damage or deterioration in transit and storage.</li>"
		"<li>Identify every package and item for traceability (batch / heat / lot numbers).</li>"
		"<li>Comply with all statutory and regulatory requirements applicable to the goods.</li>"
		"<li>Use qualified personnel and controlled processes for any special process.</li>"
		"<li>Honour the warranty / service requirements stated in this order.</li>"
		"</ol>"
		"<p>Goods are subject to inspection at receipt; nonconforming supply may be returned at the "
		"supplier's cost and affects approval status on the Approved Suppliers Register (REG-007).</p>"
	)
	frappe.get_doc(
		{"doctype": "Terms and Conditions", "title": title, "terms": terms, "buying": 1, "selling": 0}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	print("iso_compliance: created Terms and Conditions 'Purchase Quality Requirements'")


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


def ensure_review_notifications():
	"""In-app (bell) notifications this app's records need.

	FRM-036 needs none of its own: its reviewers are notified by ERPNext's
	assignment. Records, not schema -- deleting them reverts the site.
	"""
	created = []

	# SOP-005: when the scheduler (or anyone) drafts a supplier evaluation,
	# Purchase and Quality see it in the bell.
	due_name = "Supplier Evaluation Due"
	if not frappe.db.exists("Notification", due_name):
		frappe.get_doc(
			{
				"doctype": "Notification",
				"enabled": 1,
				"channel": "System Notification",
				"document_type": "Supplier Evaluation",
				"event": "New",
				"subject": "Supplier evaluation due: {{ doc.supplier_name or doc.supplier }}",
				"message": (
					"A {{ doc.evaluation_type }} evaluation (FRM-005) has been drafted for "
					"{{ doc.supplier_name or doc.supplier }}. Complete it to keep the "
					"Approved Suppliers Register (REG-007) current."
				),
				"recipients": [
					{"receiver_by_role": "Purchase Manager"},
					{"receiver_by_role": "Quality Manager"},
				],
			}
		).insert(ignore_permissions=True, set_name=due_name)
		created.append(due_name)

	if created:
		frappe.db.commit()
		print(f"iso_compliance: created notifications ({len(created)})")


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


def ensure_rejected_warehouse():
	"""One warehouse that holds rejected material, incoming and from production (SOP-006 step 5).

	Segregation is the step auditors test: rejected material must be kept where it
	cannot be issued by mistake. ERPNext models it with `rejected_warehouse` on the
	receipt, but with no such warehouse on the site the field stayed empty, and the
	eleven rejections on record went to Goods In Transit -- and twice straight back
	into Stores, beside the accepted stock.

	Created per company, under the company's warehouse root so it inherits the tree.
	A record, not schema: deleting it reverts the site untouched, and the receipt
	hook simply stops defaulting.
	"""
	created = []
	for company in frappe.get_all("Company", fields=["name", "abbr"]):
		name = f"{REJECTED_WAREHOUSE_NAME} - {company.abbr}"
		if frappe.db.exists("Warehouse", name):
			continue
		# Nest under the company's group root where there is one, so the warehouse
		# appears in the tree rather than beside it.
		root = frappe.db.get_value(
			"Warehouse", {"company": company.name, "is_group": 1, "parent_warehouse": ("in", (None, ""))}, "name"
		)
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": REJECTED_WAREHOUSE_NAME,
				"company": company.name,
				"is_group": 0,
				"parent_warehouse": root,
				"warehouse_type": None,
			}
		)
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	if created:
		frappe.db.commit()
		print(f"iso_compliance: created warehouse(s) {', '.join(created)}")


def ensure_incoming_rejection_notification():
	"""SOP-006 step 5: a rejection at receipt is reported to Purchase.

	The SOP makes Purchase responsible for taking a rejection up with the supplier,
	which until now depended on somebody walking over to say so. Fires on a
	submitted incoming inspection whose status is Rejected. A record, not schema.
	"""
	name = "Incoming Material Rejected"
	if frappe.db.exists("Notification", name):
		return
	frappe.get_doc(
		{
			"doctype": "Notification",
			"enabled": 1,
			"channel": "System Notification",
			"document_type": "Quality Inspection",
			"event": "Submit",
			"condition": 'doc.inspection_type == "Incoming" and doc.status == "Rejected"',
			"subject": "Incoming material rejected: {{ doc.item_code }}",
			"message": (
				"Inspection {{ doc.name }} rejected {{ doc.item_code }} received against "
				"{{ doc.reference_name }}. The rejected quantity is segregated in the Rejected "
				"warehouse. Raise a Non Conformance (FRM-020) from the inspection, and take the "
				"matter up with the supplier -- it affects their standing on REG-007."
			),
			"recipients": [
				{"receiver_by_role": "Purchase Manager"},
				{"receiver_by_role": "Quality Manager"},
			],
		}
	).insert(ignore_permissions=True, set_name=name)
	frappe.db.commit()
	print(f"iso_compliance: created Notification '{name}'")
