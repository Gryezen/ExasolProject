window.renderMainPanel = function (data) {
  renderDiscrepancies(data.discrepancies, data.actions, data.doc);
};

function renderDiscrepancies(discrepancies, actions, doc) {
  const el = document.getElementById("panel-discrepancies");

  if (doc.status === "reasoning") {
    el.innerHTML = `<div class="reasoning-note">This document is ready for reasoning but hasn't been compared against its linked case documents yet. Click "Run reasoning &amp; draft actions" above to validate it and, if any discrepancy is found, draft a follow-up action.</div>`;
    return;
  }

  if (!discrepancies.length) {
    el.innerHTML = `<div class="empty-panel">No discrepancies found. ${doc.status === "complete" ? "This document was checked against its case file and everything matched." : "Reasoning runs once the document reaches the \"reasoning\" stage."}</div>`;
    return;
  }

  el.innerHTML = discrepancies.map(d => {
    const relatedActions = actions.filter(a => a.discrepancy_id === d.discrepancy_id);
    return `
      <div class="disc-card">
        <div class="disc-head">
          <span class="badge ${esc(d.severity)}">${esc(d.severity)}</span>
          <span class="field-name">${esc(d.field_name)}</span>
          <span style="color:var(--faint); font-size:11.5px;">${esc(d.status)}</span>
        </div>
        <div class="disc-values">
          <div class="v"><div class="label">Document A</div><div class="val">${esc(d.value_1)}</div></div>
          <div class="v"><div class="label">Document B</div><div class="val">${esc(d.value_2)}</div></div>
        </div>
        <div class="explain">${esc(d.explanation || "")}</div>
        ${relatedActions.length ? relatedActions.map(a => `
          <div class="action-card" data-action-id="${esc(a.action_id)}">
            <div class="a-head">
              <span class="a-type">${esc(a.action_type.replace('_', ' '))}</span>
              <span class="badge ${a.status === 'proposed' ? 'medium' : (a.status === 'approved' ? 'low' : 'high')}">${esc(a.status)}</span>
            </div>
            <div class="content">${esc(a.content)}</div>
            ${a.status === "proposed" ? `
              <div class="a-controls">
                <button class="primary act-approve">Approve</button>
                <button class="danger act-reject">Reject</button>
              </div>` : `<div style="font-size:11.5px; color:var(--faint);">decided by ${esc(a.decided_by || "—")}</div>`}
          </div>
        `).join("") : ""}
      </div>
    `;
  }).join("");

  el.querySelectorAll(".act-approve, .act-reject").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const card = e.target.closest(".action-card");
      const actionId = card.dataset.actionId;
      const decision = e.target.classList.contains("act-approve") ? "approved" : "rejected";
      btn.disabled = true;
      try {
        await api(`/api/actions/${actionId}/decide`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, decided_by: "case_handler" }),
        });
        await refreshDocPage();
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    });
  });
}
