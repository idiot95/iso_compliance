// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.listview_settings["Controlled Document"] = {
	add_fields: ["workflow_state", "issue_number", "revision_number", "document_type"],

	get_indicator(doc) {
		const colours = {
			Draft: "red",
			"Under Review": "orange",
			Approved: "blue",
			Active: "green",
			Superseded: "gray",
			Obsolete: "gray",
		};
		if (!doc.workflow_state) return [__("No Status"), "gray", "workflow_state,is,not set"];
		return [
			__(doc.workflow_state),
			colours[doc.workflow_state] || "gray",
			"workflow_state,=," + doc.workflow_state,
		];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Print Controlled Set"), () => {
			print_controlled_set();
		});

		listview.page.add_inner_button(__("Print Set by Type"), () => {
			frappe.prompt(
				[
					{
						fieldname: "document_type",
						fieldtype: "Link",
						options: "Controlled Document Type",
						label: __("Document Type"),
						reqd: 1,
					},
					{
						fieldname: "include_retired",
						fieldtype: "Check",
						label: __("Include Superseded and Obsolete"),
						default: 0,
					},
				],
				(values) => print_controlled_set(values.document_type, values.include_retired),
				__("Print Controlled Set"),
				__("Print")
			);
		});
	},
};

function print_controlled_set(document_type, include_retired) {
	const params = new URLSearchParams();
	if (document_type) params.set("document_type", document_type);
	params.set("include_retired", include_retired ? 1 : 0);

	// Tell the user how many documents are coming before spending time on the PDF.
	frappe.call({
		method: "iso_compliance.api.bulk_print.preview_selection",
		args: { document_type: document_type || null, include_retired: include_retired ? 1 : 0 },
		callback(r) {
			if (!r.message || !r.message.count) {
				frappe.msgprint(__("No controlled documents matched."));
				return;
			}
			const count = r.message.count;
			// Each document is rendered by its own headless Chrome, so a large set
			// has to go to a worker rather than the web process.
			const queue = count > 25;
			frappe.confirm(
				queue
					? __(
							"Compile {0} controlled documents in the background? A download link appears when it is ready.",
							[count]
					  )
					: __("Compile {0} controlled documents into a single PDF?", [count]),
				() => {
					if (!queue) {
						window.open(
							`/api/method/iso_compliance.api.bulk_print.print_all?${params.toString()}`
						);
						return;
					}
					frappe.call({
						method: "iso_compliance.api.bulk_print.queue_print_all",
						args: {
							document_type: document_type || null,
							include_retired: include_retired ? 1 : 0,
						},
						callback() {
							frappe.show_alert({
								message: __("Compiling {0} documents. The download will start when ready.", [count]),
								indicator: "blue",
							});
						},
					});
				}
			);
		},
	});
}
