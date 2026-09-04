// Progressive review form: the order header and criticality factors stay
// constant; each review section appears only once the review reaches its
// stage, and completed stages stay visible (permission levels keep them
// read-only for everyone but their own reviewer). The chain itself is
// enforced server-side by the workflow -- this file declutters the form and
// mirrors the server's tier/costing arithmetic so the figures are visible
// before the first save (the server recomputes them authoritatively).

const TCR_DETAILED_FROM = 1000000;

const TCR_CRITICALITY = [
	"new_or_first_time_product",
	"customer_drawings_design_inputs",
	"special_contract_conditions",
	"special_statutory_requirements",
];

const TCR_COSTS = [
	"estimated_material_cost",
	"estimated_labour_cost",
	"estimated_overhead_cost",
	"logistics_cost",
	"other_direct_cost",
];

function tcr_compute_tier(frm) {
	const critical = TCR_CRITICALITY.some((f) => frm.doc[f]);
	const tier =
		critical || (frm.doc.order_value || 0) >= TCR_DETAILED_FROM ? "Detailed" : "Standard";
	if (frm.doc.review_tier !== tier) frm.set_value("review_tier", tier);
}

function tcr_fetch_order(frm) {
	if (!frm.doc.sales_order) return;
	frappe.db
		.get_value("Sales Order", frm.doc.sales_order, [
			"customer",
			"customer_name",
			"base_grand_total",
			"po_no",
		])
		.then((r) => {
			const so = r && r.message;
			if (!so) return;
			if (!frm.doc.customer) frm.set_value("customer", so.customer);
			frm.set_value("order_value", so.base_grand_total);
			if (!frm.doc.enquiry_reference && so.po_no) {
				frm.set_value("enquiry_reference", so.po_no);
			}
			tcr_compute_tier(frm);
		});
}

function tcr_compute_costing(frm) {
	const total = TCR_COSTS.reduce((sum, f) => sum + (frm.doc[f] || 0), 0);
	frm.set_value("total_estimated_cost", total);
	const selling = frm.doc.proposed_selling_price || 0;
	frm.set_value("expected_gross_margin", selling ? selling - total : 0);
	frm.set_value("expected_margin_pct", selling ? ((selling - total) / selling) * 100 : 0);
}

const tcr_handlers = {
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

		// Collapse everything but the stage being worked on; on a completed
		// review leave all sections open for reading.
		if (frm.doc.docstatus === 0) {
			const owning_stage = {
				section_technical: 1,
				section_costing: 2,
				section_costing_eval: 2,
				section_commercial: 3,
				section_overall: 3,
				section_outcome: 3,
			};
			Object.entries(owning_stage).forEach(([fieldname, at]) => {
				const field = frm.get_field(fieldname);
				if (field && field.collapse && stage >= at) field.collapse(at !== stage);
			});
		}

		// On a brand-new form the server has not run yet: pull the order's
		// company-currency value now so the header is right before saving.
		if (frm.is_new() && frm.doc.sales_order && !frm.doc.order_value) {
			tcr_fetch_order(frm);
		}

		if (frm.doc.docstatus !== 0) return;
		// Clear before setting: stacked intros around a save show twice.
		frm.set_intro("");
		if (frm.is_new()) {
			frm.set_intro(
				__("Order details load from the Sales Order. Save to load the parameter checklist for the computed tier."),
				"blue"
			);
		} else if (stage === 0) {
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

	before_workflow_action(frm) {
		// Send Back demands a reason; it lands on both the review's and the
		// Sales Order's comment timeline before the state moves.
		if (frm.selected_workflow_action !== "Send Back") return;
		return new Promise((resolve, reject) => {
			frappe.prompt(
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Why is this review being sent back?"),
					reqd: 1,
				},
				(values) => {
					frappe
						.call({
							method: "iso_compliance.iso_compliance.doctype.techno_commercial_review.techno_commercial_review.record_send_back",
							args: { review: frm.doc.name, reason: values.reason },
						})
						.then(() => resolve())
						.catch(reject);
				},
				__("Send Back"),
				__("Send Back")
			);
		});
	},

	sales_order(frm) {
		tcr_fetch_order(frm);
	},

	order_value(frm) {
		tcr_compute_tier(frm);
	},

	proposed_selling_price(frm) {
		tcr_compute_costing(frm);
	},
};

TCR_CRITICALITY.forEach((f) => (tcr_handlers[f] = tcr_compute_tier));
TCR_COSTS.forEach((f) => (tcr_handlers[f] = tcr_compute_costing));

frappe.ui.form.on("Techno Commercial Review", tcr_handlers);
