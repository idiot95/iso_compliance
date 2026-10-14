// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// The way into a revision. An Approved or Active document is edited in place,
// never cancelled and amended: raise a Document Change Request, have someone
// else approve it, then start the revision here. Saving moves the revision
// number, writes the history row and marks the request Implemented.

const CD_GUARDED = ["Approved", "Active", "Superseded", "Obsolete"];

frappe.ui.form.on("Controlled Document", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0 || !CD_GUARDED.includes(frm.doc.workflow_state)) return;

		if (frm.doc.change_request) {
			frm.dashboard.set_headline_alert(
				__("Revising under {0}. Make the changes and save; the revision number moves on save.", [
					`<a href="/app/document-change-request/${encodeURIComponent(frm.doc.change_request)}">${frm.doc.change_request}</a>`,
				]),
				"blue"
			);
			return;
		}

		frappe.db
			.get_list("Document Change Request", {
				filters: { controlled_document: frm.doc.name, docstatus: 1, status: "Approved" },
				fields: ["name"],
				order_by: "creation desc",
				limit: 1,
			})
			.then((approved) => {
				const dcr = approved && approved[0];
				if (dcr) {
					frm.add_custom_button(__("Start revision"), () => {
						frm.set_value("change_request", dcr.name);
						frm.refresh();
					}).addClass("btn-primary");
					frm.dashboard.set_headline_alert(
						__("Change request {0} is approved. Press Start revision to edit.", [dcr.name]),
						"green"
					);
				} else {
					frm.add_custom_button(__("Request a change"), () => {
						frappe.new_doc("Document Change Request", {
							controlled_document: frm.doc.name,
							document_title: frm.doc.title,
							change_type: "Revision",
						});
					});
					frm.dashboard.set_headline_alert(
						__("Under change control. To change it, press Request a change; a different user approves the request."),
						"gray"
					);
				}
			});
	},
});
