// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Quality Inspection Template list: start a drawing template from an item's
// drawing (same dialog as BOM / Item › Create › Inspection template).

frappe.listview_settings["Quality Inspection Template"] = Object.assign(
	frappe.listview_settings["Quality Inspection Template"] || {},
	{
		onload(listview) {
			if (!frappe.user.has_role(["Quality Manager", "System Manager"])) return;
			listview.page.add_inner_button(__("New from drawing"), () => {
				const d = new frappe.ui.Dialog({
					title: __("New drawing template"),
					fields: [
						{
							fieldname: "item",
							fieldtype: "Link",
							options: "Item",
							label: __("Item"),
							reqd: 1,
							description: __("Its BOMs' drawings are offered next."),
						},
					],
					primary_action_label: __("Next"),
					primary_action: async (v) => {
						d.hide();
						await frappe.require("/assets/iso_compliance/js/qi_start_template.js");
						iso_qi.start_template(v.item);
					},
				});
				d.show();
			});
		},
	}
);
