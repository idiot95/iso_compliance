// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// An item with no inspection plan is inspected on a one-off plan: each
// characteristic is added during the inspection (no drawing needed), and
// Quality then saves them as the plan of the item or an item group. Used by
// the inspector screen and the Quality Inspection form. `d` is what
// iso_compliance.qi.inspector.get_inspection returns.

window.iso_qi_one_off = (() => {
	const API = "iso_compliance.qi.inspector";

	// then(balloon) once it is on the inspection
	function add(d, then) {
		const tol = (...types) => `eval:doc.row_type!=="Visual" && ${JSON.stringify(types)}.includes(doc.tolerance_type)`;
		const dlg = new frappe.ui.Dialog({
			title: __("Add characteristic"),
			fields: [
				{
					fieldname: "row_type", fieldtype: "Select", label: __("Kind"), reqd: 1, default: "Dimension",
					options: [
						{ value: "Dimension", label: __("Dimension") },
						{ value: "Visual", label: __("Visual (OK / NG)") },
						{ value: "Test", label: __("Operational test") },
						// read off the supplier's certificate, so at receipt only
						...(d.stage === "Incoming" ? [{ value: "Material", label: __("Material, from the supplier's 3.1") }] : []),
					],
					onchange: () => dlg.set_value("tolerance_type", dlg.get_value("row_type") === "Dimension" ? "Symmetric" : "Limits"),
				},
				{ fieldname: "specification", fieldtype: "Data", label: __("Characteristic"), reqd: 1, description: __("e.g. Length, Hardness, Surface finish") },
				{ fieldname: "spec_text", fieldtype: "Data", label: __("As specified"), description: __("Optional: as the customer or catalogue states it, e.g. 25 ±0.1") },
				{ fieldname: "test_method", fieldtype: "Link", options: "Test Method", label: __("Test method"), depends_on: 'eval:doc.row_type==="Test"', mandatory_depends_on: 'eval:doc.row_type==="Test"' },
				{ fieldtype: "Column Break" },
				{ fieldname: "class", fieldtype: "Select", label: __("Class"), options: ["", "CTQ", "Major", "Minor"] },
				{ fieldname: "unit", fieldtype: "Link", options: "UOM", label: __("Unit"), depends_on: 'eval:doc.row_type!=="Visual"' },
				{ fieldtype: "Section Break", label: __("Tolerance"), depends_on: 'eval:doc.row_type!=="Visual"' },
				{
					// General (ISO 2768) needs a title block and Reference is not inspected: neither is offered
					fieldname: "tolerance_type", fieldtype: "Select", label: __("Tolerance type"), default: "Symmetric",
					options: ["Symmetric", "Deviations", "Limits", "Maximum only", "Minimum only", "ISO fit (ISO 286)", "Angle", "Geometric (GD&T)"],
				},
				{ fieldname: "nominal", fieldtype: "Float", label: __("Nominal"), depends_on: tol("Symmetric", "Deviations", "ISO fit (ISO 286)", "Angle") },
				{ fieldname: "tol", fieldtype: "Float", label: __("± Tolerance / zone"), depends_on: tol("Symmetric", "Angle", "Geometric (GD&T)") },
				{ fieldname: "fit_class", fieldtype: "Data", label: __("Fit class"), description: __("e.g. H11, h9"), depends_on: tol("ISO fit (ISO 286)") },
				{ fieldtype: "Column Break" },
				{ fieldname: "upper_dev", fieldtype: "Float", label: __("Upper deviation"), depends_on: tol("Deviations") },
				{ fieldname: "lower_dev", fieldtype: "Float", label: __("Lower deviation"), depends_on: tol("Deviations") },
				{ fieldname: "min", fieldtype: "Float", label: __("Min"), depends_on: tol("Limits", "Minimum only") },
				{ fieldname: "max", fieldtype: "Float", label: __("Max"), depends_on: tol("Limits", "Maximum only") },
			],
			primary_action_label: __("Add"),
			primary_action: async (v) => {
				const { message: balloon } = await frappe.call({ method: `${API}.add_characteristic`, args: { qi: d.name, characteristic: v }, freeze: true });
				dlg.hide();
				then && then(balloon);
			},
		});
		dlg.show();
	}

	// then(holder) once saved
	function save(d, then) {
		const dlg = new frappe.ui.Dialog({
			title: __("Save as inspection plan"),
			fields: [
				{
					fieldname: "intro", fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"Later inspections load these {0} characteristics without asking. Quality can add a drawing and more stages to the plan afterwards.",
						[d.rows.length]
					)}</p>`,
				},
				{
					fieldname: "target", fieldtype: "Select", label: __("Save against"), reqd: 1, default: "Item",
					options: [
						{ value: "Item", label: __("This item only ({0})", [d.item_code]) },
						...(d.plan_groups.length ? [{ value: "Item Group", label: __("An item group: every item in it with no plan of its own") }] : []),
					],
				},
				{
					fieldname: "item_group", fieldtype: "Select", label: __("Item group"), options: d.plan_groups, default: d.plan_groups[0],
					depends_on: 'eval:doc.target==="Item Group"', description: __("The item's own group, or one above it"),
				},
			],
			primary_action_label: __("Save plan"),
			primary_action: async (v) => {
				const { message: holder } = await frappe.call({
					method: `${API}.save_as_plan`,
					args: { qi: d.name, target: v.target, item_group: v.target === "Item Group" ? v.item_group : null },
					freeze: true,
				});
				dlg.hide();
				frappe.show_alert({ message: __("Saved as the inspection plan of {0}", [holder]), indicator: "green" });
				then && then(holder);
			},
		});
		dlg.show();
	}

	return { add, save };
})();
