// The supplier's QMS standing as a card at the top of the form, with the one
// next step that applies: evaluate, continue the open evaluation, or
// re-evaluate. State is written only by submitted FRM-005 evaluations
// (SOP-005 / REG-007), so the card is the place to act, not the fields.

const HCC_STATUS_COLOUR = {
	Approved: "green",
	Provisional: "orange",
	"Not Approved": "red",
	Suspended: "gray",
};

function hcc_supplier_card(frm) {
	if (frm.doc.__islocal) return;
	Promise.all([
		frappe.db.get_list("Supplier Evaluation", {
			filters: { supplier: frm.doc.name, docstatus: 1 },
			fields: ["name", "evaluation_date", "owner", "overall_score", "approval_status"],
			order_by: "evaluation_date desc, creation desc",
			limit: 1,
		}),
		frappe.db.get_list("Supplier Evaluation", {
			filters: { supplier: frm.doc.name, docstatus: 0 },
			fields: ["name"],
			limit: 1,
		}),
	]).then(([done, open]) => {
		const last = done && done[0];
		const draft = open && open[0];
		const status = frm.doc.custom_approval_status;
		const colour = HCC_STATUS_COLOUR[status] || "orange";
		const score = frm.doc.custom_score;
		const stars = score ? "★".repeat(Math.round(score / 20)) + "☆".repeat(5 - Math.round(score / 20)) : "";
		const due = frm.doc.custom_reapproval_due;
		const overdue = due && due < frappe.datetime.get_today();

		const facts = [
			[__("Category"), frm.doc.custom_category ? __(frm.doc.custom_category) : __("not set")],
			[
				__("Last evaluated"),
				last
					? `<a href="/app/supplier-evaluation/${encodeURIComponent(last.name)}">${frappe.datetime.str_to_user(last.evaluation_date)}</a> · ${frappe.utils.escape_html(frappe.user.full_name(last.owner))}`
					: __("never"),
			],
			[
				__("Next review"),
				due
					? `<span class="${overdue ? "text-danger" : ""}">${frappe.datetime.str_to_user(due)}${overdue ? " · " + __("overdue") : ""}</span>`
					: "—",
			],
		]
			.map(([k, v]) => `<div class="hcc-sc__fact"><span>${k}</span><b>${v}</b></div>`)
			.join("");

		const can_evaluate = frappe.model.can_create("Supplier Evaluation");
		let action = "";
		if (draft) {
			action = `<button class="btn btn-primary btn-sm hcc-sc__go" data-open="${encodeURIComponent(draft.name)}">${__("Continue evaluation")}</button>`;
		} else if (can_evaluate) {
			const label = last ? __("Re-evaluate") : __("Evaluate supplier");
			action = `<button class="btn btn-primary btn-sm hcc-sc__go">${label}</button>`;
		}
		const note =
			status === "Approved"
				? __("Purchase Orders can be placed.")
				: status === "Suspended"
				? __("No Purchase Orders can be placed.")
				: __("Purchase Orders need a manager's override until this supplier is Approved.");

		const html = `
			<div class="hcc-sc">
				<div class="hcc-sc__main">
					<span class="indicator-pill ${colour}">${status ? __(status) : __("Not evaluated")}</span>
					${stars ? `<span class="hcc-sc__stars" title="${Math.round(score)}%">${stars}</span>` : ""}
					<span class="hcc-sc__note">${note}</span>
				</div>
				<div class="hcc-sc__facts">${facts}</div>
				<div class="hcc-sc__action">${action}</div>
			</div>`;

		frm.dashboard.clear_headline();
		frm.dashboard.set_headline_alert(html);
		// The headline sits outside frm.dashboard.wrapper, so listen on the
		// whole form; namespaced so a refresh doesn't stack handlers.
		$(frm.wrapper)
			.off("click.hcc_sc")
			.on("click.hcc_sc", ".hcc-sc__go", function () {
				const open_name = $(this).attr("data-open");
				if (open_name) {
					frappe.set_route("Form", "Supplier Evaluation", decodeURIComponent(open_name));
					return;
				}
				frappe.route_options = {
					supplier: frm.doc.name,
					evaluation_type: last ? "Periodic" : "Initial",
				};
				frappe.new_doc("Supplier Evaluation");
			});
	});
}

function hcc_inject_supplier_styles() {
	if (document.getElementById("hcc-sc-styles")) return;
	const css = `
	.hcc-sc { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 24px; width: 100%; }
	.hcc-sc__main { display: flex; align-items: center; gap: 10px; flex: 1 1 260px; }
	.hcc-sc__stars { color: var(--yellow-500); font-size: var(--text-lg); letter-spacing: 1px; }
	.hcc-sc__note { color: var(--text-muted); font-size: var(--text-sm); }
	.hcc-sc__facts { display: flex; gap: 20px; flex-wrap: wrap; }
	.hcc-sc__fact { display: flex; flex-direction: column; font-size: var(--text-sm); }
	.hcc-sc__fact span { color: var(--text-muted); }
	`;
	$("<style>").attr("id", "hcc-sc-styles").text(css).appendTo("head");
}

frappe.ui.form.on("Supplier", {
	setup() {
		hcc_inject_supplier_styles();
	},
	refresh(frm) {
		hcc_supplier_card(frm);
	},
});
