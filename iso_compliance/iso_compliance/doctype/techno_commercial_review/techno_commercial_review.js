// One form, three reviewers. Sales picks who fills Technical, Costing and
// Commercial and saves; the server assigns them and lets them edit. A
// progress bar on top says what is left in each section, and a click on a
// section jumps there. Section headings are enlarged so an assignee can find
// theirs at a glance. The tier and costing arithmetic mirror the server so
// the figures are right before the first save (the server recomputes them).

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

// Must match REQUIRED_COST_FIELDS and SECTIONS in techno_commercial_review.py.
const TCR_REQUIRED_COSTS = ["estimated_material_cost", "proposed_selling_price"];

const TCR_SECTIONS = [
	{ key: "technical", assignee: "technical_assignee", table: "technical_parameters", label: __("Technical"), section: "section_technical" },
	{ key: "costing", assignee: "costing_assignee", table: "costing_parameters", label: __("Costing"), section: "section_costing" },
	{ key: "commercial", assignee: "commercial_assignee", table: "commercial_parameters", label: __("Commercial"), section: "section_commercial" },
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
	tcr_render_progress(frm);
}

function tcr_progress(frm) {
	const sections = TCR_SECTIONS.map((s) => {
		const rows = frm.doc[s.table] || [];
		let done = rows.filter((r) => r.response).length;
		let total = rows.length;
		if (s.key === "costing" && frm.doc.review_tier === "Detailed") {
			total += TCR_REQUIRED_COSTS.length;
			done += TCR_REQUIRED_COSTS.filter((f) => frm.doc[f]).length;
		}
		return { ...s, user: frm.doc[s.assignee], done, total };
	});
	sections.push({
		key: "outcome",
		label: __("Decision"),
		section: "section_outcome",
		user: frm.doc.owner,
		done: frm.doc.outcome ? 1 : 0,
		total: 1,
	});
	const done = sections.reduce((n, s) => n + s.done, 0);
	const total = sections.reduce((n, s) => n + s.total, 0);
	return { sections, done, total };
}

function tcr_render_progress(frm) {
	const field = frm.get_field("progress_html");
	if (!field) return;
	if (frm.is_new()) {
		field.$wrapper.html(
			`<div class="tcr-progress tcr-progress--hint">${__(
				"Save to load the checklist. Then pick the reviewers."
			)}</div>`
		);
		return;
	}
	const p = tcr_progress(frm);
	const pct = p.total ? Math.round((p.done / p.total) * 100) : 0;
	const left = p.total - p.done;
	const headline =
		frm.doc.docstatus === 1
			? __("Review complete: {0}", [__(frm.doc.outcome || "")])
			: left
			? __("{0} of {1} done · {2} left", [p.done, p.total, left])
			: __("All done. Submit to complete the review.");

	const chips = p.sections
		.map((s) => {
			const complete = s.total && s.done >= s.total;
			const who = s.user
				? frappe.utils.escape_html(frappe.user.full_name(s.user))
				: `<span class="tcr-chip__unassigned">${__("not assigned")}</span>`;
			return `<button type="button" class="tcr-chip ${complete ? "tcr-chip--done" : ""}" data-section="${s.section}">
				<span class="tcr-chip__label">${complete ? "✓ " : ""}${s.label}</span>
				<span class="tcr-chip__count">${s.done}/${s.total}</span>
				<span class="tcr-chip__who">${who}</span>
			</button>`;
		})
		.join("");

	field.$wrapper.html(`
		<div class="tcr-progress">
			<div class="tcr-progress__head">
				<span>${headline}</span><span>${pct}%</span>
			</div>
			<div class="tcr-progress__bar"><div style="width:${pct}%"></div></div>
			<div class="tcr-progress__chips">${chips}</div>
		</div>`);
	field.$wrapper.find(".tcr-chip").on("click", function () {
		frm.scroll_to_field($(this).attr("data-section"));
	});
}

function tcr_inject_styles() {
	if (document.getElementById("tcr-form-styles")) return;
	const css = `
	.tcr-form .form-section .section-head {
		font-size: 1.35rem; font-weight: 700; color: var(--heading-color);
		padding-top: var(--padding-md); padding-bottom: var(--padding-sm);
	}
	.tcr-form .form-section .section-head + .section-body .section-description,
	.tcr-form .form-section .section-description { font-size: var(--text-sm); }
	.tcr-progress { padding: var(--padding-sm) 0; }
	.tcr-progress--hint { color: var(--text-muted); }
	.tcr-progress__head { display: flex; justify-content: space-between; font-weight: 600; font-size: var(--text-lg); margin-bottom: 6px; }
	.tcr-progress__bar { height: 10px; border-radius: 5px; background: var(--gray-200); overflow: hidden; }
	.tcr-progress__bar > div { height: 100%; background: var(--primary); transition: width .2s; }
	.tcr-progress__chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
	.tcr-chip { display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
		min-width: 150px; padding: 8px 12px; border: 1px solid var(--border-color);
		border-radius: var(--border-radius-md); background: var(--card-bg); text-align: left; cursor: pointer; }
	.tcr-chip:hover { border-color: var(--primary); }
	.tcr-chip--done { border-color: var(--green-500); background: var(--green-50); }
	.tcr-chip__label { font-weight: 600; }
	.tcr-chip__count { font-size: var(--text-lg); font-weight: 700; }
	.tcr-chip__who { font-size: var(--text-sm); color: var(--text-muted); }
	.tcr-chip__unassigned { color: var(--orange-600); }
	`;
	$("<style>").attr("id", "tcr-form-styles").text(css).appendTo("head");
}

const tcr_handlers = {
	setup(frm) {
		tcr_inject_styles();
	},

	refresh(frm) {
		$(frm.wrapper).addClass("tcr-form");

		// On a brand-new form the server has not run yet: pull the order's
		// company-currency value now so the header is right before saving.
		if (frm.is_new() && frm.doc.sales_order && !frm.doc.order_value) {
			tcr_fetch_order(frm);
		}
		tcr_render_progress(frm);
	},

	sales_order(frm) {
		tcr_fetch_order(frm);
	},

	order_value(frm) {
		tcr_compute_tier(frm);
	},

	review_tier(frm) {
		tcr_render_progress(frm);
	},

	proposed_selling_price(frm) {
		tcr_compute_costing(frm);
	},

	outcome(frm) {
		tcr_render_progress(frm);
	},
};

TCR_CRITICALITY.forEach((f) => (tcr_handlers[f] = tcr_compute_tier));
TCR_COSTS.forEach((f) => (tcr_handlers[f] = tcr_compute_costing));
TCR_SECTIONS.forEach((s) => (tcr_handlers[s.assignee] = tcr_render_progress));

frappe.ui.form.on("Techno Commercial Review", tcr_handlers);

frappe.ui.form.on("Techno Commercial Review Parameter", {
	response(frm) {
		tcr_render_progress(frm);
	},
});
