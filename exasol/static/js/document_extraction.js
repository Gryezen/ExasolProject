window.renderMainPanel = function (data) {
  renderFields(data.fields, data.doc.status);
  renderCaseFile(data.related);
};

function renderFields(fields, docStatus) {
  const el = document.getElementById("panel-fields");
  if (!fields.length) {
    el.innerHTML = `<div class="empty-panel">No fields extracted for this document yet.</div>`;
    return;
  }
  const threshold = window.CONFIDENCE_THRESHOLD;
  el.innerHTML = `
    <table class="fields">
      <thead><tr><th>Field</th><th>Extracted value</th><th>Confidence</th><th>Source</th></tr></thead>
      <tbody>
        ${fields.map(f => {
          const conf = f.confidence === null || f.confidence === undefined ? null : Number(f.confidence);
          const low = conf !== null && conf < threshold;
          return `
          <tr class="${low ? 'low-conf' : ''}" data-field-id="${esc(f.field_id)}">
            <td class="mono">${esc(f.field_name)}</td>
            <td>${esc(f.value)}</td>
            <td>
              ${conf === null ? '<span class="mono" style="color:var(--faint)">—</span>' : `
                <span class="conf-bar">
                  <span class="conf-track"><span class="conf-fill ${low ? 'low' : ''}" style="width:${Math.round(conf * 100)}%"></span></span>
                  ${conf >= threshold ? "🟢" : (conf >= threshold - 0.15 ? "🟡" : "🔴")} ${(conf * 100).toFixed(0)}%
                </span>`}
              ${low && docStatus === "review" ? `
                <div class="review-row">
                  <input type="text" class="review-input" placeholder="corrected value" value="${esc(f.value)}">
                  <button class="review-confirm" title="Confirm as-is">Confirm</button>
                  <button class="review-correct" title="Save corrected value">Correct</button>
                </div>` : ""}
            </td>
            <td class="mono" style="color:var(--faint)">${esc(f.source_agent || "")}</td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>
  `;

  el.querySelectorAll(".review-confirm, .review-correct").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const row = e.target.closest("tr");
      const fieldId = row.dataset.fieldId;
      const field = fields.find(f => f.field_id === fieldId);
      const input = row.querySelector(".review-input");
      const isCorrect = e.target.classList.contains("review-correct");
      const humanValue = isCorrect ? input.value : field.value;
      const status = isCorrect ? "corrected" : "confirmed";
      e.target.disabled = true;
      try {
        await api("/api/reviews", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            doc_id: window.DOC_ID,
            field_id: fieldId,
            field_name: field.field_name,
            ai_value: field.value,
            human_value: humanValue,
            status,
            reviewed_by: "case_handler",
          }),
        });
        await refreshDocPage();
      } catch (err) {
        alert(err.message);
        e.target.disabled = false;
      }
    });
  });
}

function renderCaseFile(related) {
  const el = document.getElementById("panel-case");
  if (!related.length) {
    el.innerHTML = `<div class="empty-panel">No linked documents yet. Once a related document (e.g. an income certificate for this welfare application) is uploaded and matched, it will appear here as part of the same case.</div>`;
    return;
  }
  el.innerHTML = related.map(r => `
    <div class="case-card" data-href="/documents/${esc(r.doc_id)}/extraction">
      <div class="c-main">
        <div class="c-name">${esc(r.filename)}</div>
        <div class="c-meta">${esc(r.document_type || "unclassified")}${r.vendor ? ` · ${esc(r.vendor)}` : ""} · <span class="badge ${esc(r.status)}">${esc(r.status)}</span></div>
      </div>
      <div class="c-rel">${esc((r.relationship_type || "").replace(/_/g, " "))}</div>
      ${r.confidence !== null && r.confidence !== undefined ? `<div class="c-conf">${Number(r.confidence).toFixed(2)}</div>` : ""}
    </div>
  `).join("");
  el.querySelectorAll(".case-card").forEach(node => {
    node.addEventListener("click", () => { window.location.href = node.dataset.href; });
  });
}
