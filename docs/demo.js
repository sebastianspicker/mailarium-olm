(() => {
  "use strict";
  const messages = [
    { id: "fixture-0007", subject: "Renewal terms for Friday review", from: "Mara Chen <mara.chen@example.test>", to: "Archive Team <archive-team@example.test>", date: "2026-04-18 09:42", thread: "Vendor renewal · 4 messages", note: "Thread context available in fixture", score: "0.91 provisional", quote: "Please confirm the renewal option before the Friday review.", body: "Hello team,\n\nPlease confirm the renewal option before the Friday review. I attached the synthetic comparison sheet for our local walkthrough.\n\nMara", attachment: "renewal-options-fixture.pdf · 24 KB", path: "fixtures/mail/2026-04/0007.eml" },
    { id: "fixture-0012", subject: "Draft scope for archive migration", from: "Devon Lee <devon.lee@example.test>", to: "Archive Team <archive-team@example.test>", date: "2026-04-16 14:10", thread: "Archive migration · 2 messages", note: "No remote action in fixture", score: "0.78 provisional", quote: "The scope is limited to local archive records and review notes.", body: "Hi all,\n\nThe scope is limited to local archive records and review notes. This sample message is intentionally synthetic.\n\nDevon", attachment: "No attachments", path: "fixtures/mail/2026-04/0012.eml" },
    { id: "fixture-0019", subject: "Review notes from operations session", from: "Samir Patel <samir.patel@example.test>", to: "Archive Team <archive-team@example.test>", date: "2026-04-12 11:05", thread: "Operations review · 3 messages", note: "Derived entities are provisional", score: "0.63 provisional", quote: "Capture source references before treating the notes as evidence.", body: "Team,\n\nCapture source references before treating the notes as evidence. The ranking remains provisional until reviewed.\n\nSamir", attachment: "operations-notes-fixture.txt · 3 KB", path: "fixtures/mail/2026-04/0019.eml" }
  ];
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  let selected = 0;
  function renderResults(items = messages) {
    const list = $("[data-result-list]");
    list.replaceChildren(...items.map((message) => {
      const index = messages.indexOf(message);
      const button = document.createElement("button");
      button.type = "button"; button.className = "result"; button.role = "option";
      button.dataset.resultId = message.id; button.setAttribute("aria-selected", String(index === selected));
      button.innerHTML = `<strong>${message.subject}</strong><span>${message.from}</span><small>${message.date} · ${message.score}</small>`;
      button.addEventListener("click", () => { selected = index; renderResults(items); renderMessage(messages[selected]); });
      return button;
    }));
  }
  function renderMessage(message) {
    $("[data-message-subject]").textContent = message.subject; $("[data-message-from]").textContent = message.from;
    $("[data-message-to]").textContent = message.to; $("[data-message-date]").textContent = message.date;
    $("[data-message-thread]").textContent = message.thread; $("[data-message-thread-note]").textContent = message.note;
    $("[data-message-score]").textContent = message.score; $("[data-message-quote]").textContent = message.quote;
    $("[data-message-body]").textContent = message.body; $("[data-message-attachment]").textContent = message.attachment;
    $("[data-message-id]").textContent = message.id; $("[data-message-path]").textContent = message.path;
  }
  function feedback(text) { $$("[data-action-feedback]").forEach((node) => { node.textContent = text; }); }
  $$("[data-view-target]").forEach((button) => button.addEventListener("click", () => {
    const target = button.dataset.viewTarget;
    $$("[data-view]").forEach((view) => { const active = view.dataset.view === target; view.hidden = !active; view.classList.toggle("active", active); });
    $$("[data-view-target]").forEach((item) => {
      if (item === button) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    $("main").focus();
  }));
  $("[data-search-form]").addEventListener("submit", (event) => {
    event.preventDefault(); const query = $("[data-search-input]").value.trim().toLowerCase();
    const attachments = $("input[name=attachments]").checked; const evidence = $("input[name=evidence-only]").checked;
    const filtered = messages.filter((message) => (!query || `${message.subject} ${message.body}`.toLowerCase().includes(query) || query === "vendor renewal") && (!attachments || message.attachment !== "No attachments") && (!evidence || message.id === "fixture-0007"));
    if (filtered.length) { selected = messages.indexOf(filtered[0]); renderResults(filtered); renderMessage(filtered[0]); }
    else { $("[data-result-list]").innerHTML = "<p class=\"muted\">No synthetic fixture results match these simulated filters.</p>"; }
    $("[data-search-status]").innerHTML = `<strong>${filtered.length} synthetic result${filtered.length === 1 ? "" : "s"}</strong><span>scope: local fixture</span><span>simulated query</span>`;
    feedback("Simulated search updated the local fixture view only.");
  });
  $$('[data-action]').forEach((button) => button.addEventListener("click", () => feedback(`${button.textContent.trim()} confirmed. No archive, evidence, export, or mailbox state changed.`)));
  renderResults(); renderMessage(messages[0]);
})();
