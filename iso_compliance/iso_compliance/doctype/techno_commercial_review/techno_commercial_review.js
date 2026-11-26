// One form, three reviewers, laid out as steps (the Report Issue screens'
// pattern): each step is a tab, numbered, with a tick once done; the current
// step's number is dark and its name bold; a line above the tabs says whose turn it is. Sales
// fills the Order tab and picks who fills Technical, Costing and Commercial;
// the server assigns them and lets them edit. Sales records the Decision.
// The tier mirrors the server so it is right before the first save.

const TCR_DETAILED_FROM = 1000000;

const TCR_CRITICALITY = [
	"new_or_first_time_product",
	"customer_drawings_design_inputs",
	"special_contract_conditions",
	"special_statutory_requirements",
];

// Must match SECTIONS in techno_commercial_review.py.
const TCR_SECTIONS = [
	{ key: "technical", assignee: "technical_assignee", table: "technical_parameters", label: __("Technical"), section: "section_technical", tab: "tab_technical" },
	{ key: "costing", assignee: "costing_assignee", table: "costing_parameters", label: __("Costing"), section: "section_costing", tab: "tab_costing" },
	{ key: "commercial", assignee: "commercial_assignee", table: "commercial_parameters", label: __("Commercial"), section: "section_commercial", tab: "tab_commercial" },
];

function tcr_compute_tier(frm) {
	const critical = TCR_CRITICALITY.some((f) => frm.doc[f]);
	const tier =
		critical || (frm.doc.order_value || 0) >= TCR_DETAILED_FROM ? "Detailed" : "Standard";
	if (frm.doc.review_tier !== tier) frm.set_value("review_tier", tier);
}

function tcr_fetch_order(frm) {
	if (!frm.doc.sales_order) return;
	// From a Sales Order it is a contract review; the stage is then read-only.
	if (!frm.doc.quotation && frm.doc.review_stage !== "Contract Review") frm.set_value("review_stage", "Contract Review");
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

// An enquiry-stage review raised on a Quotation: same header, from the quotation.
function tcr_fetch_quotation(frm) {
	if (!frm.doc.quotation || frm.doc.sales_order) return;
	// Before any order it is an enquiry review; the stage is then read-only.
	if (frm.doc.review_stage !== "Enquiry Review") frm.set_value("review_stage", "Enquiry Review");
	frappe.db
		.get_value("Quotation", frm.doc.quotation, ["quotation_to", "party_name", "base_grand_total"])
		.then((r) => {
			const q = r && r.message;
			if (!q) return;
			if (!frm.doc.customer && q.quotation_to === "Customer") frm.set_value("customer", q.party_name);
			frm.set_value("order_value", q.base_grand_total);
			tcr_compute_tier(frm);
		});
}

// The five steps in order: whose each is, and how far along.
function tcr_steps(frm) {
	const d = frm.doc;
	const named = TCR_SECTIONS.every((s) => d[s.assignee]);
	const steps = [
		{ label: __("Order"), tab: "tab_order", user: d.owner, left: 0, done: !frm.is_new() && named },
		...TCR_SECTIONS.map((s) => {
			const rows = d[s.table] || [];
			const answered = rows.filter((r) => r.response).length;
			return {
				...s,
				user: d[s.assignee],
				answered,
				total: rows.length,
				left: rows.length - answered,
				done: !frm.is_new() && rows.length > 0 && answered === rows.length,
			};
		}),
		{ label: __("Decision"), tab: "tab_decision", user: d.owner, left: 0, done: d.docstatus === 1 },
	];
	return { steps, k: steps.findIndex((s) => !s.done) };
}

function tcr_name(user) {
	return user ? frappe.utils.escape_html(frappe.user.full_name(user)) : "";
}

// The line above the tabs: whose turn it is.
function tcr_headline(frm, steps, k) {
	const n = steps.length;
	if (frm.is_new()) return [__("Save to load the checklist. Then pick the reviewers."), "blue"];
	if (frm.doc.docstatus === 1) return [__("Review complete: {0}. All {1} steps are done.", [__(frm.doc.outcome || ""), n]), "green"];
	if (frm.doc.docstatus === 2) return [__("This review was cancelled."), "red"];
	const cur = steps[k];
	const left = (s) => (s.left ? " · " + __("{0} left", [s.left]) : "");
	// The reviewers work side by side, so a later review step can be yours while an earlier one is open.
	const mine = steps.filter((s, i) => !s.done && s.user === frappe.session.user && (s.table || i === k));
	if (mine.length) return [__("Step {0} of {1} · Your turn: {2}", [k + 1, n, mine.map((s) => s.label + left(s)).join(", ")]), "orange"];
	if (!cur.user) return [__("Step {0} of {1} · {2}: no reviewer picked yet. Pick one on the Order tab.", [k + 1, n, cur.label]), "orange"];
	return [__("Step {0} of {1} · With {2}: {3}{4}. Nothing for you to do.", [k + 1, n, tcr_name(cur.user), cur.label, left(cur)]), "blue"];
}

function tcr_render_steps(frm) {
	if (!frm.layout || !frm.layout.tabs) return;
	const { steps, k } = tcr_steps(frm);
	const [text, color] = tcr_headline(frm, steps, k);
	frm.layout.show_message(); // clears the previous line
	frm.layout.show_message(`<div>${text}</div>`, color, true);

	const closed = frm.doc.docstatus === 1;
	steps.forEach((s, i) => {
		const tab = frm.layout.tabs.find((t) => t.df.fieldname === s.tab);
		if (!tab) return;
		const state = s.done || closed ? "done" : i === k ? "now" : "todo";
		tab.tab_link
			.find(".nav-link")
			.removeClass("tcr-step--done tcr-step--now tcr-step--todo")
			.addClass(`tcr-step--${state}`)
			.html(`<span class="tcr-step"><span class="tcr-step__dot">${state === "done" ? "✓" : i + 1}</span>${s.label}</span>`);

		// A reviewer's section says who fills it and how far they are.
		if (s.table && !frm.is_new()) {
			const who = s.user ? tcr_name(s.user) : __("the {0} reviewer (not picked yet)", [s.label]);
			const head =
				state === "done" ? __("Filled by {0}", [who]) : state === "now" ? __("To be filled by {0}", [who]) : __("Will be filled by {0}", [who]);
			const section = frm.get_field(s.section);
			section.set_label(head);
			section.description_wrapper && section.description_wrapper.text(__("{0} of {1} answered", [s.answered, s.total]));
		}
	});

	// Opens on the current step the first time this review is shown.
	if (!frm.is_new() && frm.__tcr_opened !== frm.doc.name) {
		frm.__tcr_opened = frm.doc.name;
		frm.layout.select_tab(k >= 0 ? steps[k].tab : "tab_decision");
	}
}

// The reviewers by name, not email: Frappe's own link titles, on these three fields only.
// User links have no title on the server, so the names come from the desk's user list.
// Frappe's own lookup answers with the email, so these fields ask for the full name instead.
function tcr_show_names(frm) {
	TCR_SECTIONS.forEach((s) => {
		const field = frm.fields_dict[s.assignee];
		if (!field || field.__tcr_names) return;
		field.__tcr_names = true;
		field.set_link_title = async (user) => {
			let name = frappe.utils.get_link_title("User", user);
			if (!name || name === user) {
				const r = await frappe.db.get_value("User", user, "full_name").catch(() => null);
				name = (r && r.message && r.message.full_name) || user;
				frappe.utils.add_link_title("User", user, name);
			}
			if (field.value === user) field.translate_and_set_input_value(name, user); // not if changed meanwhile
		};
		field.set_formatted_input(frm.doc[s.assignee]);
	});
}

function tcr_inject_styles() {
	if (document.getElementById("tcr-form-styles")) return;
	const css = `
	.tcr-form .form-tabs .tcr-step { display: inline-flex; align-items: center; gap: 6px; padding: 2px 0; border-radius: 999px; }
	.tcr-form .form-tabs .tcr-step__dot { width: 18px; height: 18px; border-radius: 50%; display: inline-flex; align-items: center;
		justify-content: center; font-size: 11px; font-weight: 600; background: var(--gray-200); color: var(--text-muted); }
	.tcr-form .form-tabs .tcr-step--done .tcr-step__dot { background: var(--green-500); color: var(--white); }
	.tcr-form .form-tabs .tcr-step--now .tcr-step { font-weight: 600; color: var(--text-color); }
	.tcr-form .form-tabs .tcr-step--now .tcr-step__dot { background: var(--text-color); color: var(--bg-color); }
	.tcr-form .form-tabs .tcr-step--todo { color: var(--text-muted); }
	`;
	$("<style>").attr("id", "tcr-form-styles").text(css).appendTo("head");
}

const tcr_handlers = {
	setup(frm) {
		tcr_inject_styles();
	},

	refresh(frm) {
		$(frm.wrapper).addClass("tcr-form");

		tcr_show_names(frm);

		// On a brand-new form the server has not run yet: pull the order's
		// company-currency value now so the header is right before saving.
		if (frm.is_new() && frm.doc.sales_order && !frm.doc.order_value) {
			tcr_fetch_order(frm);
		}
		if (frm.is_new() && frm.doc.quotation && !frm.doc.order_value) {
			tcr_fetch_quotation(frm);
		}
		tcr_render_steps(frm);
	},

	sales_order(frm) {
		tcr_fetch_order(frm);
	},

	quotation(frm) {
		tcr_fetch_quotation(frm);
	},

	order_value(frm) {
		tcr_compute_tier(frm);
	},
};

TCR_CRITICALITY.forEach((f) => (tcr_handlers[f] = tcr_compute_tier));
TCR_SECTIONS.forEach((s) => (tcr_handlers[s.assignee] = tcr_render_steps));

frappe.ui.form.on("Techno Commercial Review", tcr_handlers);

frappe.ui.form.on("Techno Commercial Review Parameter", {
	response(frm) {
		tcr_render_steps(frm);
	},
});
