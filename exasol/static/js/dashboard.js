async function refreshStats() {
  try {
    const stats = await api("/api/stats");
    document.getElementById("statTotal").textContent = stats.documents_total;
    document.getElementById("statHighConf").textContent = stats.high_confidence_fields;
    document.getElementById("statReview").textContent = stats.needs_review;
    document.getElementById("statActions").textContent = stats.actions_triggered;
  } catch (e) { /* keep server-rendered values */ }
}

function docLink(doc) {
  if (doc.status === "reasoning" || doc.status === "complete") return `/documents/${doc.doc_id}/reasoning`;
  return `/documents/${doc.doc_id}/extraction`;
}

async function refreshDocuments() {
  let docs;
  try { docs = await api("/api/documents"); }
  catch (e) { return; }

  const table = document.getElementById("docTable");
  const empty = document.getElementById("docEmpty");
  const body = document.getElementById("docTableBody");
  document.getElementById("docCount").textContent = docs.length ? `(${docs.length})` : "";

  if (!docs.length) {
    table.style.display = "none";
    empty.style.display = "block";
    return;
  }
  table.style.display = "table";
  empty.style.display = "none";

  body.innerHTML = docs.map(d => `
    <tr class="clickable" data-href="${docLink(d)}">
      <td>
        <div class="fname">${esc(d.filename)}</div>
        <div class="docid">${esc(shortId(d.doc_id))}</div>
      </td>
      <td>${esc(d.document_type || "unclassified")}</td>
      <td>${esc(d.vendor || "—")}</td>
      <td><span class="badge ${esc(d.status)}">${esc(d.status)}</span></td>
      <td class="mono" style="color:var(--faint); font-size:12px;">${esc(fmtTime(d.uploaded_at))}</td>
    </tr>
  `).join("");
  body.querySelectorAll("tr.clickable").forEach(row => {
    row.addEventListener("click", () => { window.location.href = row.dataset.href; });
  });
}

(async function init() {
  await refreshStats();
  await refreshDocuments();
  setInterval(() => { refreshStats(); refreshDocuments(); }, 8000);
})();
