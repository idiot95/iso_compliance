// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Submitting is approving (by someone other than the requester). Once approved,
// the next step is on the document itself: Start revision.

frappe.ui.form.on("Document Change Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.dashboard.set_headline_alert(
				frm.doc.requested_by === frappe.session.user
					? __("Another user approves this request by submitting it.")
					: __("Submit to approve this change."),
				"gray"
			);
		}
		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved" && frm.doc.controlled_document) {
			frm.add_custom_button(__("Revise the document"), () => {
				frappe.set_route("Form", "Controlled Document", frm.doc.controlled_document);
			}).addClass("btn-primary");
		}
	},
});
