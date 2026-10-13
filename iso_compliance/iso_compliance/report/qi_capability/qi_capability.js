// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["QI Capability"] = {
	filters: [
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item", reqd: 1 },
		{
			fieldname: "template",
			label: __("Inspection template"),
			fieldtype: "Link",
			options: "Quality Inspection Template",
			get_query: () => ({ filters: { custom_item: frappe.query_report.get_filter_value("item_code") || "" } }),
		},
		{ fieldname: "stage", label: __("Stage"), fieldtype: "Select", options: "\nIncoming\nIn Process\nFinal", default: "Final" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "ctq_only", label: __("CTQ only"), fieldtype: "Check", default: 0 },
		{ fieldname: "chart_balloon", label: __("Chart balloon"), fieldtype: "Data", description: __("Blank = the first CTQ") },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "cpk" && data && data.cpk != null) {
			const colour = data.cpk >= 1.33 ? "green" : data.cpk >= 1.0 ? "orange" : "red";
			value = `<span style="color:var(--${colour}-600);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
