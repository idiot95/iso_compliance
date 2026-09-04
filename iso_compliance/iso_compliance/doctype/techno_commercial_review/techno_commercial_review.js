// Progressive review form: the order header and criticality factors stay
// constant; each review section appears only once the review reaches its
// stage, and completed stages stay visible (permission levels keep them
// read-only for everyone but their own reviewer). The chain itself is
// enforced server-side by the workflow -- this file only declutters.

frappe.ui.form.on("Techno Commercial Review", {
	refresh(frm) {
		const chain = ["Draft", "Technical Review", "Costing Review", "Commercial Review", "Approved"];
		let stage = chain.indexOf(frm.doc.workflow_state || "Draft");
		if (stage < 0 || frm.doc.docstatus === 1) stage = chain.length - 1;

		const sections = [
			{
				from: 1,
				fields: ["section_technical", "technical_parameters", "key_technical_conditions"],
			},
			{
				from: 2,
				fields: [
					"section_costing",
					"costing_parameters",
					"section_costing_eval",
					"estimated_material_cost",
					"estimated_labour_cost",
					"estimated_overhead_cost",
					"logistics_cost",
					"other_direct_cost",
					"total_estimated_cost",
					"proposed_selling_price",
					"expected_gross_margin",
					"expected_margin_pct",
				],
			},
			{
				from: 3,
				fields: [
					"section_commercial",
					"commercial_parameters",
					"payment_terms",
					"proposed_delivery_period",
					"warranty_period",
					"key_commercial_conditions",
					"section_overall",
					"overall_parameters",
					"major_risks",
					"mitigation_controls",
					"deviations_exclusions",
					"customer_clarifications",
					"section_outcome",
					"outcome",
					"outcome_remarks",
				],
			},
		];
		sections.forEach((s) => frm.toggle_display(s.fields, stage >= s.from));

		if (frm.doc.docstatus !== 0) return;
		if (stage === 0) {
			frm.set_intro(
				__(
					"Check the order details and criticality factors, then Actions → Send for Technical Review."
				),
				"blue"
			);
		} else {
			const turn = {
				1: [__("Technical Reviewer"), __("Technical Review")],
				2: [__("Costing Reviewer"), __("Costing Review")],
				3: [__("Commercial Reviewer"), __("Commercial Review and Outcome")],
			}[stage];
			if (turn) {
				frm.set_intro(
					__("Awaiting {0}: complete the {1} section, then pass it on via Actions.", turn),
					"blue"
				);
			}
		}
	},
});
