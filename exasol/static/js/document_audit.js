window.renderMainPanel = function (data) {
  renderAudit(data.audit);
};

function renderAudit(audit) {
  const el = document.getElementById("panel-audit");
  if (!audit.length) {
    el.innerHTML = `<div class="empty-panel">No audit events recorded yet.</div>`;
    return;
  }
  el.innerHTML = `<div class="ledger">${audit.map(a => `
    <div class="ledger-entry">
      <div class="l-top">
        <span class="l-time">${esc(fmtTime(a.timestamp))}</span>
        <span class="l-agent">${esc(a.agent_name)}</span>
      </div>
      <div class="l-action">${esc((a.action || "").replace(/_/g, " "))}${a.confidence !== null && a.confidence !== undefined ? ` <span class="mono" style="color:var(--faint); font-weight:400; font-size:11.5px;">(${Number(a.confidence).toFixed(2)})</span>` : ""}</div>
      <div class="l-summary">${a.input_summary ? `<span class="k">in:</span> ${esc(a.input_summary)}` : ""}</div>
      <div class="l-summary">${a.output_summary ? `<span class="k">out:</span> ${esc(a.output_summary)}` : ""}</div>
    </div>
  `).join("")}</div>`;
}
