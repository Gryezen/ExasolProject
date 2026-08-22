document.getElementById("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const question = input.value.trim();
  if (!question) return;
  await runChatQuestion(question);
});

async function runChatQuestion(question) {
  const input = document.getElementById("chatInput");
  input.value = question;

  const turn = document.createElement("div");
  turn.className = "chat-turn";
  turn.dataset.q = question;
  turn.innerHTML = `<div class="q">${esc(question)}</div><div class="chat-loading">translating to SQL…</div>`;
  document.getElementById("chatHistory").prepend(turn);

  try {
    const result = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderChatResult(turn, result);
  } catch (err) {
    turn.innerHTML = `<div class="q">${esc(question)}</div><div class="explanation sql-error">${esc(err.message)}</div>`;
  }
  input.value = "";
}

function renderChatResult(turn, result) {
  const q = turn.dataset.q || "";
  if (result.error) {
    turn.innerHTML = `
      <div class="q">${esc(q)}</div>
      <div class="explanation">${esc(result.explanation || "")}</div>
      <div class="sql-box sql-error">rejected: ${esc(result.error)}</div>
    `;
    return;
  }
  const columns = result.columns || (result.rows && result.rows[0] ? result.rows[0].map((_, i) => `col_${i}`) : []);
  const rowsHtml = (result.rows || []).length
    ? `<table class="chat-rows">
        <thead><tr>${columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
        <tbody>${result.rows.map(r => `<tr>${r.map(v => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>`
    : `<div style="color:var(--faint); font-size:12.5px;">No rows returned.</div>`;
  turn.innerHTML = `
    <div class="q">${esc(q)}</div>
    <div class="explanation">${esc(result.explanation || "")}</div>
    <div class="sql-box">${esc(result.sql || "")}</div>
    ${rowsHtml}
  `;
}

const CHAT_EXAMPLES = [
  "Show all welfare applicants earning below ₹2,00,000",
  "Find land records owned by Ravi Kumar",
  "List complaints from Chennai district",
  "Show contractors bidding above ₹1 crore",
  "Which documents are still waiting on human review?",
];
if (window.PREFILL_DOC_NAME) {
  CHAT_EXAMPLES.unshift(
    `What fields were extracted from "${window.PREFILL_DOC_NAME}"?`,
    `Why was "${window.PREFILL_DOC_NAME}" flagged for review?`
  );
}
document.getElementById("chatExamples").innerHTML = CHAT_EXAMPLES.map(q =>
  `<button type="button" class="chat-chip">${esc(q)}</button>`
).join("");
document.querySelectorAll(".chat-chip").forEach(chip => {
  chip.addEventListener("click", () => runChatQuestion(chip.textContent));
});

if (window.PREFILL_DOC_NAME) {
  document.getElementById("chatInput").placeholder = `Ask about "${window.PREFILL_DOC_NAME}"…`;
}
