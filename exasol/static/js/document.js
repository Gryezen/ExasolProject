// Shared across document_extraction.html / document_reasoning.html /
// document_audit.html. Each of those pages sets window.DOC_ID and defines
// window.renderMainPanel(data) before this file's DOMContentLoaded runs.

async function loadDocData() {
  const [doc, fields, discrepancies, actions, audit, related] = await Promise.all([
    api(`/api/documents/${window.DOC_ID}`).catch(() => null),
    api(`/api/documents/${window.DOC_ID}/fields`).catch(() => []),
    api(`/api/documents/${window.DOC_ID}/discrepancies`).catch(() => []),
    api(`/api/documents/${window.DOC_ID}/actions`).catch(() => []),
    api(`/api/documents/${window.DOC_ID}/audit`).catch(() => []),
    api(`/api/documents/${window.DOC_ID}/related`).catch(() => []),
  ]);
  return { doc, fields, discrepancies, actions, audit, related };
}

function renderCounts(data) {
  const countFields = document.getElementById("countFields");
  const countCase = document.getElementById("countCase");
  const countDisc = document.getElementById("countDisc");
  const countAudit = document.getElementById("countAudit");
  if (countFields) countFields.textContent = data.fields.length ? `(${data.fields.length})` : "";
  if (countCase) countCase.textContent = data.related.length ? `(${data.related.length})` : "";
  if (countDisc) countDisc.textContent = data.discrepancies.length ? `(${data.discrepancies.length})` : "";
  if (countAudit) countAudit.textContent = data.audit.length ? `(${data.audit.length})` : "";
}

function renderDocActions(doc) {
  const el = document.getElementById("docActions");
  if (!el) return;
  el.innerHTML = "";
  if (doc.status === "reasoning") {
    const btn = document.createElement("button");
    btn.className = "primary";
    btn.textContent = "Run reasoning & draft actions";
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = "Reasoning…";
      try {
        await api(`/api/documents/${doc.doc_id}/process`, { method: "POST" });
        window.location.href = `/documents/${doc.doc_id}/reasoning`;
      } catch (e) {
        alert(e.message);
        btn.disabled = false;
        btn.textContent = "Run reasoning & draft actions";
      }
    };
    el.appendChild(btn);
  }
  const refresh = document.createElement("button");
  refresh.textContent = "Refresh";
  refresh.onclick = refreshDocPage;
  el.appendChild(refresh);
}

async function refreshDocPage() {
  const data = await loadDocData();
  if (!data.doc) return;
  renderCounts(data);
  renderDocActions(data.doc);
  if (typeof window.renderMainPanel === "function") window.renderMainPanel(data);
}

document.addEventListener("DOMContentLoaded", () => {
  refreshDocPage();
});
