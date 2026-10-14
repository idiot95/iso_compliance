// What waits in Inspection Required, oldest first: Engineering inspects,
// Stores racks and posts the transfer. "Next step" opens the right document.

frappe.query_reports["Inspection Status"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["Open", "To inspect", "To rack", "Done", ""],
			default: "Open",
		},
		{
			fieldname: "stage",
			label: __("Stage"),
			fieldtype: "Select",
			options: ["", "Incoming", "Final"],
		},
		{
			fieldname: "from_date",
			label: __("Posted since"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		const html = default_formatter(value, row, column, data);
		if (!data) return html;
		if (column.fieldname === "status") {
			const colour = { "To inspect": "orange", "To rack": "blue", Done: "green" }[data.status] || "gray";
			return `<span class="indicator-pill ${colour}">${__(data.status)}</span>`;
		}
		if (column.fieldname === "waiting" && data.waiting > 2) {
			return `<span class="text-danger">${html}</span>`;
		}
		return html;
	},
};
