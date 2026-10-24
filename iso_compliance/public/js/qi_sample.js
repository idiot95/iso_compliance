// Copyright (c) 2026, Hatim Carbon Co. Pvt. Ltd. and contributors
// For license information, please see license.txt

// How many pieces of a lot to measure: − / number / + with a few quick picks
// and the settings' percentage, and what share of the lot that is. Used when
// an inspection starts and on the inspection itself.

window.iso_qi_sample = (() => {
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

	function picks(lot, suggested) {
		const out = [1, 3, 5, 10].filter((n) => !lot || n <= lot).map((n) => ({ n, label: String(n) }));
		if (suggested && !out.some((p) => p.n === suggested)) out.push({ n: suggested, label: __("{0} · default", [suggested]) });
		else if (suggested) out.find((p) => p.n === suggested).label += " · " + __("default");
		return out;
	}

	// mounts the control in $host; on_change(n) on every valid change
	function mount($host, { lot, value, suggested, on_change }) {
		const share = (n) => (lot ? `${format_number((n / lot) * 100, null, n / lot < 0.01 ? 2 : 1)}%` : "");
		$host.html(`<div class="qi-smp">
			<div class="qi-smp-row">
				<button type="button" class="qi-smp-step" data-d="-1" aria-label="${__("Fewer")}">−</button>
				<input class="qi-smp-n" type="number" min="1" ${lot ? `max="${lot}"` : ""} inputmode="numeric" value="${esc(value)}">
				<button type="button" class="qi-smp-step" data-d="1" aria-label="${__("More")}">+</button>
				<div class="qi-smp-ctx"><b>${__("pieces")}</b>${lot ? `<span>${__("of {0} in the lot", [format_number(lot, null, 0)])} · <span class="qi-smp-share">${share(value)}</span></span>` : ""}</div>
			</div>
			<div class="qi-smp-picks">${picks(lot, suggested)
				.map((p) => `<button type="button" class="qi-smp-pick ${p.n === value ? "on" : ""}" data-n="${p.n}">${esc(p.label)}</button>`)
				.join("")}</div>
		</div>`);
		const $n = $host.find(".qi-smp-n");
		const set = (n, quiet) => {
			n = Math.max(1, Math.min(lot || Infinity, parseInt(n, 10) || 1));
			$n.val(n);
			$host.find(".qi-smp-share").text(share(n));
			$host.find(".qi-smp-pick").each((_, el) => $(el).toggleClass("on", Number($(el).data("n")) === n));
			if (!quiet && on_change) on_change(n);
			return n;
		};
		$host.find(".qi-smp-step").on("click", (e) => set((parseInt($n.val(), 10) || 0) + Number($(e.currentTarget).data("d"))));
		$host.find(".qi-smp-pick").on("click", (e) => set(Number($(e.currentTarget).data("n"))));
		$n.on("change", () => set($n.val()));
		return { get: () => set($n.val(), true) };
	}

	// the question asked when an inspection starts
	function ask({ lot, suggested, value, title, action, then }) {
		let ctl = null;
		const d = new frappe.ui.Dialog({
			title: title || __("Sample size"),
			fields: [{ fieldname: "picker", fieldtype: "HTML" }],
			primary_action_label: action || __("Start inspection"),
			primary_action: () => {
				d.hide();
				then(ctl.get());
			},
		});
		d.show();
		ctl = mount(d.fields_dict.picker.$wrapper, { lot, value: value || suggested || 1, suggested });
		setTimeout(() => d.$wrapper.find(".qi-smp-n").trigger("focus").select(), 200);
	}

	frappe.dom.set_style(`
.qi-smp{display:flex;flex-direction:column;gap:10px}
.qi-smp-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.qi-smp-step{width:40px;height:40px;border-radius:10px;border:1px solid var(--border-color);background:var(--fg-color);font-size:20px;line-height:1;color:var(--text-color)}
.qi-smp-step:hover{border-color:var(--gray-500)}
.qi-smp-n{width:84px;height:40px;border-radius:10px;border:1px solid var(--border-color);background:var(--control-bg);text-align:center;font-size:22px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--text-color);-moz-appearance:textfield}
.qi-smp-n::-webkit-outer-spin-button,.qi-smp-n::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
.qi-smp-ctx{display:flex;flex-direction:column;line-height:1.25;margin-left:4px}
.qi-smp-ctx b{font-weight:600;color:var(--text-color)}
.qi-smp-ctx span{font-size:var(--text-sm);color:var(--text-muted)}
.qi-smp-picks{display:flex;flex-wrap:wrap;gap:6px}
.qi-smp-pick{border:1px solid var(--border-color);background:var(--fg-color);border-radius:8px;padding:3px 10px;font-size:var(--text-sm);color:var(--text-color)}
.qi-smp-pick.on{background:var(--gray-800);border-color:var(--gray-800);color:#fff}
`);

	return { mount, ask };
})();
