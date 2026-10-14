// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// Stock Labels (SOP-006 step 3, identification): two jobs for Stores.
//   Scan   — what a label is, where that stock is now and where it belongs,
//            including lots waiting in Inspection Required.
//   Print  — labels for stock already on the shelves, on an A4 sheet of eight
//            or a thermal roll. Server side: iso_compliance.api.labels.

const HCC_LBL = "iso_compliance.api.labels";

frappe.pages["stock-labels"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Stock Labels"), single_column: true });
	wrapper.labels = new HccStockLabels(page);
};

frappe.pages["stock-labels"].on_page_show = function (wrapper) {
	if (wrapper.labels && wrapper.labels.tab === "scan") wrapper.labels.focus();
};

class HccStockLabels {
	constructor(page) {
		this.page = page;
		this.tab = "scan";
		this.rows = [];
		this.recent = [];
		this.$w = $(`<div class="hcc-sl">
			<style>
				.hcc-sl { max-width: 1100px; margin: 0 auto; padding: 8px 0 40px; }
				.hcc-sl-tabs { display: inline-flex; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; margin-bottom: 18px; }
				.hcc-sl-tabs button { border: 0; background: var(--fg-color); padding: 8px 18px; font-weight: 600; color: var(--text-muted); }
				.hcc-sl-tabs button.on { background: var(--primary); color: #fff; }
				.hcc-sl-scan input { font-size: 20px; height: 52px; }
				.hcc-sl-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 18px 20px; margin-top: 16px; background: var(--fg-color); }
				.hcc-sl-card h3 { margin: 0 0 2px; font-size: 18px; }
				.hcc-sl-sub { color: var(--text-muted); }
				.hcc-sl-verdict { margin: 14px 0 10px; padding: 12px 14px; border-radius: 8px; font-size: 15px; font-weight: 600; }
				.hcc-sl-verdict.ok { background: var(--green-50, #e8f5e9); color: var(--green-700, #2e7d32); }
				.hcc-sl-verdict.move { background: var(--orange-50, #fff3e0); color: var(--orange-700, #b45309); }
				.hcc-sl-verdict.wait { background: var(--blue-50, #e3f2fd); color: var(--blue-700, #1d4ed8); }
				.hcc-sl-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin-top: 10px; }
				.hcc-sl-h { font-size: 11px; text-transform: uppercase; letter-spacing: .6px; color: var(--text-muted); font-weight: 700; margin-bottom: 6px; }
				.hcc-sl-wh { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-color); }
				.hcc-sl-wh.home b::after { content: " ★"; color: var(--green-600, #16a34a); }
				.hcc-sl-lot { padding: 8px 0; border-bottom: 1px solid var(--border-color); }
				.hcc-sl-recent { margin-top: 18px; }
				.hcc-sl-recent a { margin-right: 10px; }
				.hcc-sl-filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
				.hcc-sl-filters > div { min-width: 200px; flex: 1; }
				.hcc-sl-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 16px 0 8px; }
				.hcc-sl-bar .hcc-sl-total { margin-left: auto; font-weight: 600; }
				.hcc-sl-table { width: 100%; }
				.hcc-sl-table th { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; }
				.hcc-sl-table td, .hcc-sl-table th { padding: 6px 8px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
				.hcc-sl-table input { width: 70px; text-align: right; }
				.hcc-sl-table .num { text-align: right; }
				.hcc-sl-empty { color: var(--text-muted); padding: 30px 0; text-align: center; }
				@media (max-width: 600px) { .hcc-sl-table .hide-sm { display: none; } }
			</style>
			<div class="hcc-sl-tabs"><button data-tab="scan">${__("Scan")}</button><button data-tab="print">${__("Print labels")}</button></div>
			<div class="hcc-sl-pane" data-pane="scan"></div>
			<div class="hcc-sl-pane" data-pane="print"></div>
		</div>`).appendTo(page.body);
		this.$w.on("click", ".hcc-sl-tabs button", (e) => this.show($(e.currentTarget).attr("data-tab")));
		this.make_scan();
		this.make_print();
		this.show("scan");
	}

	show(tab) {
		this.tab = tab;
		this.$w.find(".hcc-sl-tabs button").each((_, b) => $(b).toggleClass("on", $(b).attr("data-tab") === tab));
		this.$w.find(".hcc-sl-pane").each((_, p) => $(p).toggle($(p).attr("data-pane") === tab));
		if (tab === "scan") this.focus();
	}

	focus() {
		setTimeout(() => this.$scan.find("input").trigger("focus"), 50);
	}

	// ---------------------------------------------------------------- scan --
	make_scan() {
		this.$scan = this.$w.find('[data-pane="scan"]').html(`<div class="hcc-sl-scan">
			<input type="text" class="form-control" autocomplete="off" placeholder="${__("Scan a label, or type a batch or item code")}">
			<div class="hcc-sl-result"></div>
			<div class="hcc-sl-recent"></div></div>`);
		this.$scan.find("input").on("keydown", (e) => {
			if (e.key !== "Enter") return;
			const code = e.target.value.trim();
			e.target.value = "";
			if (code) this.lookup(code);
		});
		this.$scan.on("click", "[data-code]", (e) => {
			e.preventDefault();
			this.lookup($(e.currentTarget).attr("data-code"));
		});
	}

	async lookup(code) {
		const esc = frappe.utils.escape_html;
		const $r = this.$scan.find(".hcc-sl-result").html(`<div class="hcc-sl-card text-muted">${__("Looking up {0}…", [esc(code)])}</div>`);
		const { message: m } = await frappe.call({ method: `${HCC_LBL}.lookup`, args: { code } });
		this.focus();
		if (!m || !m.found) {
			$r.html(`<div class="hcc-sl-card"><div class="hcc-sl-verdict move">${__("Nothing matches {0}.", [esc(code)])}</div></div>`);
			return;
		}
		this.recent = [m.batch_no || m.item_code, ...this.recent.filter((c) => c !== (m.batch_no || m.item_code))].slice(0, 8);
		const where = m.where || [];
		const total = where.reduce((s, w) => s + w.qty, 0);
		const waiting = m.inspection || [];
		const in_home = where.filter((w) => w.warehouse === m.home).reduce((s, w) => s + w.qty, 0);
		const elsewhere = where.filter((w) => w.warehouse !== m.home && w.qty > 0 && !waiting.length);
		let verdict;
		if (!where.length) verdict = `<div class="hcc-sl-verdict move">${__("No stock of this on the books.")}</div>`;
		else if (waiting.length && waiting.every((l) => l.transfer))
			verdict = `<div class="hcc-sl-verdict move">${__("Inspected. Move it to {0} and post the transfer.", [[...new Set(waiting.map((l) => esc(l.release || "")))].join(", ")])}</div>`;
		else if (waiting.length) verdict = `<div class="hcc-sl-verdict wait">${__("Waiting for inspection: keep it in Inspection Required.")}</div>`;
		else if (m.home && Math.abs(in_home - total) < 1e-6) verdict = `<div class="hcc-sl-verdict ok">✓ ${__("Belongs in {0}, and that is where the books have it.", [esc(m.home)])}</div>`;
		else if (m.home) verdict = `<div class="hcc-sl-verdict move">${__("Belongs in {0}. The books also have it in {1}.", [esc(m.home), elsewhere.map((w) => esc(w.warehouse)).join(", ")])}</div>`;
		else verdict = `<div class="hcc-sl-verdict move">${__("No home warehouse set on this item (Item › Defaults).")}</div>`;
		const uom = esc(m.uom || "");
		const lots = waiting.map((l) => {
			const link = `<a href="/app/${frappe.router.slug(l.reference_type)}/${encodeURIComponent(l.reference_name)}">${esc(l.reference_name)}</a>`;
			const state = l.transfer
				? __("Inspected. Transfer {0} drafted: rack it in {1} and post the transfer.", [`<a href="/app/stock-entry/${encodeURIComponent(l.transfer)}">${esc(l.transfer)}</a>`, esc(l.release || "")])
				: l.state === "started" ? __("Inspection {0} started; goes to {1} once accepted.", [esc(l.inspection), esc(l.release || "")])
				: __("Not inspected yet; goes to {0} once accepted.", [esc(l.release || "")]);
			return `<div class="hcc-sl-lot"><b>${link}</b> · ${format_number(l.qty)} ${uom}<div class="small">${state}</div></div>`;
		}).join("");
		const b = m.batch || {};
		$r.html(`<div class="hcc-sl-card">
			<h3>${esc(m.item_name)}</h3>
			<div class="hcc-sl-sub">${esc(m.item_code)}${m.batch_no ? ` · ${__("Batch")} <b>${esc(m.batch_no)}</b>` : ""} · ${esc(m.item_group || "")}</div>
			${verdict}
			<div class="hcc-sl-grid">
				<div><div class="hcc-sl-h">${__("Where it is now")}</div>
					${where.map((w) => `<div class="hcc-sl-wh ${w.warehouse === m.home ? "home" : ""}"><b>${esc(w.warehouse)}</b><span>${format_number(w.qty)} ${uom}</span></div>`).join("") || `<div class="text-muted">${__("Nowhere")}</div>`}
				</div>
				<div><div class="hcc-sl-h">${__("Where it belongs")}</div>
					<div class="hcc-sl-wh"><b>${esc(m.home || __("Not set"))}</b></div>
					${lots ? `<div class="hcc-sl-h" style="margin-top:12px">${__("Inspection")}</div>${lots}` : ""}
				</div>
				${m.batch_no ? `<div><div class="hcc-sl-h">${__("Batch")}</div>
					${b.supplier ? `<div>${__("Supplier")}: ${esc(b.supplier)}</div>` : ""}
					${b.manufacturing_date ? `<div>${__("Date")}: ${frappe.datetime.str_to_user(b.manufacturing_date)}</div>` : ""}
					${b.reference_name ? `<div>${__("From")}: <a href="/app/${frappe.router.slug(b.reference_doctype)}/${encodeURIComponent(b.reference_name)}">${esc(b.reference_name)}</a></div>` : ""}
				</div>` : ""}
			</div></div>`);
		this.$scan.find(".hcc-sl-recent").html(this.recent.length > 1
			? `<span class="text-muted small">${__("Recent")}:</span> ${this.recent.map((c) => `<a href="#" data-code="${esc(c)}">${esc(c)}</a>`).join("")}` : "");
	}

	// --------------------------------------------------------------- print --
	make_print() {
		const $p = this.$w.find('[data-pane="print"]');
		$p.html(`<div class="hcc-sl-filters"></div>
			<div class="hcc-sl-bar"></div>
			<div class="hcc-sl-list"><div class="hcc-sl-empty">${__("Choose a warehouse (and a group or item if you like), then Load stock.")}</div></div>`);
		const make = (df, parent) => frappe.ui.form.make_control({ df, parent: $("<div>").appendTo(parent), render_input: true });
		const $f = $p.find(".hcc-sl-filters");
		this.f = {
			warehouse: make({ fieldtype: "Link", options: "Warehouse", label: __("Warehouse"), get_query: () => ({ filters: { is_group: 0 } }) }, $f),
			item_group: make({ fieldtype: "Link", options: "Item Group", label: __("Item group") }, $f),
			item_code: make({ fieldtype: "Link", options: "Item", label: __("Item") }, $f),
		};
		$(`<div style="flex:0"><button class="btn btn-default btn-sm">${__("Load stock")}</button></div>`).appendTo($f)
			.find("button").on("click", () => this.load());
		const $b = $p.find(".hcc-sl-bar");
		this.layout = make({ fieldtype: "Select", label: __("Print on"), options: [], change: () => this.total() }, $b);
		this.guides = make({ fieldtype: "Check", label: __("Cutting guides") }, $b);
		$(`<div><div class="hcc-sl-h">${__("Labels each")}</div><input type="number" min="0" class="form-control input-sm hcc-sl-all" style="width:90px" placeholder="1"></div>`).appendTo($b);
		$b.append(`<span class="hcc-sl-total"></span><button class="btn btn-primary btn-sm hcc-sl-print">${__("Print")}</button>`);
		frappe.call({ method: `${HCC_LBL}.layouts` }).then(({ message }) => {
			this.layout.df.options = message;
			this.layout.refresh();
			this.layout.set_value(message[0].value);
		});
		$b.on("change", ".hcc-sl-all", (e) => {
			const n = cint(e.target.value);
			this.rows.forEach((r) => (r.labels = n));
			this.render();
		});
		$b.on("click", ".hcc-sl-print", () => this.print());
		$p.on("change", ".hcc-sl-n", (e) => {
			this.rows[cint($(e.target).attr("data-i"))].labels = cint(e.target.value);
			this.total();
		});
	}

	async load() {
		const args = {};
		Object.entries(this.f).forEach(([k, c]) => (args[k] = c.get_value() || null));
		if (!args.warehouse && !args.item_group && !args.item_code) return frappe.msgprint(__("Choose a warehouse, item group or item first."));
		const { message } = await frappe.call({ method: `${HCC_LBL}.stock_rows`, args, freeze: true, freeze_message: __("Reading stock…") });
		this.rows = message || [];
		this.render();
	}

	render() {
		const esc = frappe.utils.escape_html;
		const $l = this.$w.find(".hcc-sl-list");
		if (!this.rows.length) {
			$l.html(`<div class="hcc-sl-empty">${__("No stock found.")}</div>`);
			return this.total();
		}
		$l.html(`<table class="hcc-sl-table"><thead><tr>
			<th>${__("Item")}</th><th>${__("Batch")}</th><th class="hide-sm">${__("Warehouse")}</th>
			<th class="num hide-sm">${__("In stock")}</th><th class="num">${__("Labels")}</th></tr></thead><tbody>
			${this.rows.map((r, i) => `<tr>
				<td><b>${esc(r.item_code)}</b><div class="small text-muted">${esc(r.item_name || "")}</div></td>
				<td>${esc(r.batch_no || "—")}</td>
				<td class="hide-sm">${esc(r.warehouse)}</td>
				<td class="num hide-sm">${format_number(r.qty)} ${esc(r.uom || "")}</td>
				<td class="num"><input type="number" min="0" class="form-control input-xs hcc-sl-n" data-i="${i}" value="${cint(r.labels)}"></td>
			</tr>`).join("")}</tbody></table>`);
		this.total();
	}

	count() {
		return this.rows.reduce((s, r) => s + cint(r.labels), 0);
	}

	total() {
		const n = this.count();
		const sheet = (this.layout.get_value() || "a4-8") === "a4-8";
		this.$w.find(".hcc-sl-total").text(n ? (sheet ? __("{0} labels · {1} A4 sheet(s)", [n, Math.ceil(n / 8)]) : __("{0} labels", [n])) : "");
	}

	print() {
		const n = this.count();
		if (!n) return frappe.msgprint(__("Set a label count on at least one row."));
		const go = () =>
			frappe.call({
				method: `${HCC_LBL}.render_stock`,
				args: { rows: JSON.stringify(this.rows.filter((r) => cint(r.labels) > 0)), layout: this.layout.get_value(), guides: this.guides.get_value() ? 1 : 0 },
				freeze: true,
				freeze_message: __("Building the labels…"),
			}).then(({ message }) => {
				const w = window.open("", "_blank");
				if (!w) return frappe.msgprint(__("Allow pop-ups for this site to open the labels."));
				w.document.write(message);
				w.document.close();
			});
		if (n > 50) frappe.confirm(__("Print {0} labels?", [n]), go);
		else go();
	}
}
