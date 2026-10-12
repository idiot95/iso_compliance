// The suppliers that need evaluating, biggest spend first. "Next Step" opens
// the open evaluation or starts a new one for that supplier.

frappe.query_reports["Supplier Approval Queue"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Not evaluated", "Provisional", "Not Approved", "Suspended", "Approved"],
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: ["", "Critical", "Non-Critical"],
		},
	],

	formatter(value, row, column, data, default_formatter) {
		const html = default_formatter(value, row, column, data);
		if (!data) return html;
		if (column.fieldname === "status") {
			const colour = { Approved: "green", Provisional: "orange", "Not Approved": "red", Suspended: "gray" }[data.status] || "orange";
			return `<span class="indicator-pill ${colour}">${frappe.utils.escape_html(data.status)}</span>`;
		}
		if (column.fieldname === "action") {
			const target = data.open_evaluation
				? `/app/supplier-evaluation/${encodeURIComponent(data.open_evaluation)}`
				: `/app/supplier-evaluation/new?supplier=${encodeURIComponent(data.supplier)}`;
			return `<a class="btn btn-xs btn-primary" href="${target}">${frappe.utils.escape_html(data.action)}</a>`;
		}
		return html;
	},
};
