"use strict";

// Static, synthetic walk-through of the Mailarium reading desk. Everything stays
// in this tab: no requests, no storage beyond an optional theme preference.
(() => {
  const data = window.MailariumDemoData;
  const messages = data.messages;
  const RELEVANCE = ["Tangential", "Background", "Supporting", "Significant", "Critical"];
  const state = {
    query: "",
    folder: "",
    mode: "semantic",
    selectedId: messages[0].id,
    findings: [],
    nextFinding: 1,
  };

  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const byId = (id) => messages.find((message) => message.id === id);
  const pad = (value, size = 2) => String(value).padStart(size, "0");
  const isoDate = (value) => String(value).slice(0, 10);
  const isoTime = (value) => `${isoDate(value)} · ${String(value).slice(11, 19)} UTC`;
  const relevance = (value) => `${value} · ${RELEVANCE[value - 1]}`;
  const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;

  function escape(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
  }
  function normalize(value) {
    return String(value).normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  }
  function notify(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(notify.timer);
    notify.timer = window.setTimeout(() => toast.classList.remove("show"), 3600);
  }
  function sourceText(message) {
    return [...message.body, ...message.quoted].join(" ");
  }
  function textMatch(message, quote) {
    const needle = normalize(quote);
    return needle.length > 0 && normalize(sourceText(message)).includes(needle);
  }

  // Ranking is fixed per mode in this demo; folder and keyword filters are real.
  function candidates() {
    const folder = state.folder.trim().toLowerCase();
    const terms = normalize(state.query).split(" ").filter((term) => term.length > 3);
    return messages
      .filter((message) => !folder || message.folder.toLowerCase().includes(folder))
      .filter((message) => state.mode !== "keyword" || !terms.length ||
        terms.some((term) => normalize(`${message.subject} ${sourceText(message)}`).includes(term)))
      .sort((first, second) => second.score[state.mode] - first.score[state.mode]);
  }

  function renderStatus() {
    $("#archive-status").innerHTML = `<span class="num">${messages.length}</span> synthetic messages · offline`;
    $("#scope-count").textContent = messages.length;
    $$("[data-evidence-count]").forEach((item) => {
      item.textContent = state.findings.length;
    });
  }

  function renderInspect() {
    const list = candidates();
    if (!list.some((message) => message.id === state.selectedId)) state.selectedId = list[0]?.id ?? null;
    const chips = [state.mode, state.folder.trim() && `Folder: ${state.folder.trim()}`].filter(Boolean)
      .map((chip) => `<span class="chip">${escape(chip)}</span>`).join("");
    $("#result-summary").innerHTML = `<strong>${plural(list.length, "candidate message", "candidate messages")}</strong>` +
      `<span>for “${escape(state.query || "(no question)")}”, ordered by relevance</span>${chips}`;
    $("#results-list").innerHTML = list.length
      ? list.map((message, index) => `<li><button class="candidate" type="button" data-result-id="${message.id}" ` +
        `aria-current="${message.id === state.selectedId}"><span class="candidate-title"><span class="num">${pad(index + 1)}</span>` +
        `${escape(message.subject)}</span><span class="candidate-meta">${escape(message.from.name)} · ` +
        `<span class="num">${isoDate(message.date)}</span></span><span class="candidate-preview">` +
        `${escape(message.body.join(" ").slice(0, 96))}…</span>` +
        (message.attachments.length ? `<span class="candidate-preview">${plural(message.attachments.length, "attachment", "attachments")}</span>` : "") +
        "</button></li>").join("")
      : '<li class="empty"><strong>No candidates in these filters.</strong>Clear the folder filter or switch to Semantic ranking.</li>';
    $$("[data-result-id]").forEach((button) => button.addEventListener("click", () => {
      state.selectedId = button.dataset.resultId;
      resetCapture();
      renderInspect();
      if (window.matchMedia("(max-width: 760px)").matches) $("#source-sheet").focus();
    }));
    renderSheet();
  }

  function highlight(paragraph) {
    const quote = $("#quote-input").value.trim();
    const escaped = escape(paragraph);
    if (quote.length < 3) return escaped;
    const lower = paragraph.toLowerCase();
    const index = lower.length === paragraph.length ? lower.indexOf(quote.toLowerCase()) : paragraph.indexOf(quote);
    if (index < 0) return escaped;
    return escape(paragraph.slice(0, index)) +
      `<mark class="pencil-mark">${escape(paragraph.slice(index, index + quote.length))}</mark>` +
      escape(paragraph.slice(index + quote.length));
  }

  function renderSheet() {
    const message = byId(state.selectedId);
    const sheet = $("#source-sheet");
    if (!message) {
      sheet.innerHTML = '<div class="empty"><strong>No message selected.</strong>Broaden the search to read a stored message.</div>';
      return;
    }
    sheet.innerHTML = `<p class="register">Stored message</p><h2>${escape(message.subject)}</h2>` +
      `<dl class="headers"><dt>From</dt><dd>${escape(message.from.name)} &lt;${escape(message.from.address)}&gt;</dd>` +
      `<dt>To</dt><dd>${message.to.map(escape).join(", ")}</dd><dt>Date</dt><dd class="num">${isoTime(message.date)}</dd>` +
      `<dt>Folder</dt><dd>${escape(message.folder)}</dd></dl>` +
      `<div class="body">${message.body.map((paragraph) => `<p>${highlight(paragraph)}</p>`).join("")}` +
      (message.quoted.length
        ? `<div class="quoted"><p class="register">Quoted history</p>${message.quoted.map((line) => `<p>${highlight(line)}</p>`).join("")}</div>`
        : "") +
      "</div>" +
      (message.attachments.length
        ? `<div class="attachments"><p class="register">${plural(message.attachments.length, "attachment", "attachments")}</p><ul>` +
          message.attachments.map((name) => `<li><span>${escape(name)}</span><small>name recorded</small></li>`).join("") + "</ul></div>"
        : '<p class="attachments hint">No attachments recorded</p>') +
      `<p class="provenance">Synthetic ID ${escape(message.id)} · rank score ${message.score[state.mode].toFixed(2)} (${state.mode}). ` +
      "A score orders reading; it is not a probability.</p>";
  }

  function renderQuoteStatus() {
    const message = byId(state.selectedId);
    const quote = $("#quote-input").value.trim();
    const status = $("#quote-status");
    if (!quote || !message) {
      status.className = "quote-status";
      status.textContent = "";
    } else if (textMatch(message, quote)) {
      status.className = "quote-status is-match";
      status.textContent = "Text match in the stored message";
    } else {
      status.className = "quote-status is-unmatched";
      status.textContent = "No text match. It can still be saved as unverified.";
    }
    window.clearTimeout(renderQuoteStatus.timer);
    renderQuoteStatus.timer = window.setTimeout(renderSheet, 250);
  }

  function resetCapture() {
    $("#capture-form").reset();
    $("#capture-error").textContent = "";
    renderQuoteStatus();
  }

  function saveFinding(event) {
    event.preventDefault();
    const message = byId(state.selectedId);
    const quote = $("#quote-input").value.trim();
    const category = $("#category-input").value.trim();
    const summary = $("#summary-input").value.trim();
    if (!message || !quote || !category || !summary) {
      $("#capture-error").textContent = "Enter an exact quote, a category, and why this matters.";
      return;
    }
    const finding = {
      id: state.nextFinding++,
      messageId: message.id,
      quote,
      category,
      summary,
      relevance: Number($("#relevance-input").value),
      verified: textMatch(message, quote),
    };
    state.findings.unshift(finding);
    resetCapture();
    renderStatus();
    renderLedger();
    notify(`F-${pad(finding.id, 4)} saved to the ledger${finding.verified ? "" : " as unverified"}.`);
  }

  function toggleEvidence(findingId) {
    const index = state.findings.findIndex((finding) => finding.id === findingId);
    if (index < 0) return;
    const [removed] = state.findings.splice(index, 1);
    renderStatus();
    renderLedger();
    notify(`F-${pad(removed.id, 4)} removed from this browser's ledger.`);
  }

  function figure(label, value) {
    return `<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`;
  }

  function entry(finding) {
    const message = byId(finding.messageId);
    return `<article class="entry"><div class="entry-register"><span class="entry-id">F-${pad(finding.id, 4)}</span>` +
      `<span>${isoDate(message.date)}</span><span class="category">${escape(finding.category)}</span>` +
      `<span>${relevance(finding.relevance)}</span>` +
      `<span class="${finding.verified ? "status-match" : "status-unmatched"}">${finding.verified ? "text match" : "unverified"}</span></div>` +
      `<div class="entry-body"><h3>${escape(message.subject)}</h3><p class="entry-source">${escape(message.from.name)} ` +
      `&lt;${escape(message.from.address)}&gt;</p><blockquote class="entry-quote${finding.verified ? "" : " is-unmatched"}">` +
      `${escape(finding.quote)}</blockquote><p><b>Why it matters</b> · ${escape(finding.summary)}</p>` +
      `<div class="entry-actions"><button class="link-button" type="button" data-remove-finding="${finding.id}">Remove from this demo</button></div>` +
      "</div></article>";
  }

  function renderLedger() {
    const total = state.findings.length;
    const verified = state.findings.filter((finding) => finding.verified).length;
    $("#evidence-figures").innerHTML = figure("Findings", total) + figure("Text match", verified) +
      figure("Unverified", total - verified) + figure("Match rate", total ? `${Math.round((verified / total) * 100)}%` : "–");
    $("#ledger").innerHTML = total
      ? state.findings.map(entry).join("")
      : '<div class="empty"><strong>No findings here yet.</strong>Open a message on Inspect, copy a sentence into Exact quote, and save it.</div>';
    $$("[data-remove-finding]").forEach((button) => button.addEventListener("click", () => toggleEvidence(Number(button.dataset.removeFinding))));
    renderExport();
  }

  function exportSelection() {
    const category = $("#export-category").value;
    const minimum = Number($("#export-relevance").value);
    return state.findings.filter((finding) => (!category || finding.category === category) && finding.relevance >= minimum);
  }

  function renderExport() {
    const select = $("#export-category");
    const current = select.value;
    const categories = [...new Set(state.findings.map((finding) => finding.category))].sort();
    select.innerHTML = '<option value="">All categories</option>' +
      categories.map((category) => `<option${category === current ? " selected" : ""}>${escape(category)}</option>`).join("");
    const selection = exportSelection();
    $("#export-count").textContent = `${plural(selection.length, "saved finding matches", "saved findings match")} these filters.`;
    $("#export-preview").innerHTML = selection.length
      ? '<div class="table-wrap"><table><thead><tr><th scope="col">Finding</th><th scope="col">Subject</th><th scope="col">Category</th>' +
        '<th scope="col" class="is-num">Relevance</th></tr></thead><tbody>' +
        selection.map((finding) => `<tr><td class="num">F-${pad(finding.id, 4)}</td><td>${escape(byId(finding.messageId).subject)}</td>` +
          `<td>${escape(finding.category)}</td><td class="is-num">${finding.relevance}</td></tr>`).join("") + "</tbody></table></div>"
      : '<div class="empty"><strong>Nothing to export.</strong>Lower the minimum relevance, choose All categories, or capture a finding on Inspect.</div>';
    $("#export-download").disabled = !selection.length;
  }

  function downloadCsv() {
    const selection = exportSelection();
    const cell = (value) => {
      const text = String(value);
      const safe = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
      return `"${safe.replaceAll('"', '""')}"`;
    };
    const rows = [
      ["Synthetic demo export", "Fictional browser-demo data only"],
      ["finding", "message_id", "subject", "from", "date", "category", "relevance", "text_match", "key_quote", "summary"],
      ...selection.map((finding) => {
        const message = byId(finding.messageId);
        return [`F-${pad(finding.id, 4)}`, message.id, message.subject, message.from.address, message.date,
          finding.category, finding.relevance, finding.verified ? "yes" : "no", finding.quote, finding.summary];
      }),
    ];
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([rows.map((row) => row.map(cell).join(",")).join("\n")], { type: "text/csv;charset=utf-8" }));
    link.download = "mailarium-synthetic-evidence.csv";
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    notify(`Downloaded ${plural(selection.length, "finding", "findings")} as CSV, created entirely in this browser.`);
  }

  function table(headers, rows, numeric = []) {
    return '<div class="table-wrap"><table><thead><tr>' +
      headers.map((header, index) => `<th scope="col"${numeric.includes(index) ? ' class="is-num"' : ""}>${escape(header)}</th>`).join("") +
      "</tr></thead><tbody>" +
      rows.map((row) => "<tr>" + row.map((value, index) => `<td${numeric.includes(index) ? ' class="is-num"' : ""}>${escape(value)}</td>`).join("") + "</tr>").join("") +
      "</tbody></table></div>";
  }

  function renderAnalysis() {
    const attachments = messages.reduce((total, message) => total + message.attachments.length, 0);
    const threads = new Set(messages.map((message) => message.thread)).size;
    $("#overview-figures").innerHTML = figure("Messages", messages.length) + figure("Threads", threads) +
      figure("Attachments", attachments) + figure("Folders", new Set(messages.map((message) => message.folder)).size);
    const max = Math.max(...data.overview.monthlyVolume);
    $("#volume-chart").innerHTML = data.overview.monthlyVolume.map((volume, index) =>
      `<div class="volume-bar" title="${data.overview.labels[index]}: ${volume}"><span style="height:${Math.round((volume / max) * 100)}%"></span>` +
      `<span>${data.overview.labels[index]}</span></div>`).join("");

    const people = new Map();
    messages.forEach((message) => {
      const sender = people.get(message.from.address) ?? { name: message.from.name, sent: 0, received: 0 };
      sender.sent += 1;
      people.set(message.from.address, sender);
      message.to.forEach((address) => {
        const person = people.get(address) ?? { name: address, sent: 0, received: 0 };
        person.received += 1;
        people.set(address, person);
      });
    });
    $("#people-table").innerHTML = table(["Name", "Address", "Sent", "Received"],
      [...people.entries()].sort((a, b) => (b[1].sent + b[1].received) - (a[1].sent + a[1].received))
        .map(([address, person]) => [person.name, address, person.sent, person.received]), [2, 3]);

    const pairs = new Map();
    messages.forEach((message) => message.to.forEach((recipient) => {
      const key = [message.from.address, recipient].sort().join(" ↔ ");
      pairs.set(key, (pairs.get(key) ?? 0) + 1);
    }));
    $("#connection-table").innerHTML = table(["Correspondents", "Shared messages"],
      [...pairs.entries()].sort((a, b) => b[1] - a[1]), [1]);
  }

  function goToPage(page) {
    $$(".page").forEach((section) => section.classList.toggle("active", section.id === `page-${page}`));
    $$(".steps button[data-page]").forEach((button) => {
      if (button.dataset.page === page) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    if (page === "inspect") renderInspect();
    if (page === "export") renderExport();
    $("#main-content").focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  const commands = [
    { label: "Search", detail: "Step 1", page: "search" },
    { label: "Inspect", detail: "Step 2", page: "inspect" },
    { label: "Evidence ledger", detail: "Step 3", page: "evidence" },
    { label: "Export", detail: "Step 4", page: "export" },
    { label: "Overview", detail: "Derived", page: "overview" },
    { label: "People & names", detail: "Derived", page: "people" },
    { label: "Connections", detail: "Derived", page: "connections" },
    { label: "Live mailbox", detail: "Disabled here", page: "mailbox" },
    { label: "Switch light", detail: "Day / night", action: () => toggleTheme() },
  ];
  function renderCommands(query = "") {
    const needle = query.toLowerCase();
    const matches = commands.filter((command) => `${command.label} ${command.detail}`.toLowerCase().includes(needle));
    $("#command-list").innerHTML = matches.map((command) =>
      `<button class="command-item" type="button" data-command="${commands.indexOf(command)}">${escape(command.label)}<small>${escape(command.detail)}</small></button>`,
    ).join("") || '<p class="hint">No matching command.</p>';
    $$("[data-command]").forEach((button) => button.addEventListener("click", () => {
      const command = commands[Number(button.dataset.command)];
      $("#command-palette").close();
      if (command.page) goToPage(command.page);
      else command.action();
    }));
  }
  function openPalette() {
    const palette = $("#command-palette");
    if (palette.open) return;
    $("#command-filter").value = "";
    renderCommands();
    palette.showModal();
    $("#command-filter").focus();
  }

  function currentTheme() {
    const explicit = document.documentElement.dataset.theme;
    if (explicit) return explicit;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "night" : "day";
  }
  function renderThemeButton() {
    const night = currentTheme() === "night";
    const button = $("#theme-toggle");
    button.innerHTML = night ? "Use light theme" : "Use dark theme";
    button.setAttribute("aria-pressed", String(night));
  }
  function toggleTheme() {
    const next = currentTheme() === "night" ? "day" : "night";
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem("mailarium-demo-theme", next);
    } catch {
      // Theme persistence is optional; the demo works without storage.
    }
    renderThemeButton();
  }

  function initialise() {
    data.findings.forEach((seed) => {
      state.findings.push({ ...seed, id: state.nextFinding++, verified: textMatch(byId(seed.messageId), seed.quote) });
    });
    renderStatus();
    renderThemeButton();
    renderLedger();
    renderAnalysis();

    $$("[data-page]").forEach((button) => button.addEventListener("click", () => goToPage(button.dataset.page)));
    $$("[data-mode]").forEach((button) => button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      $$("[data-mode]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    }));
    $("#search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      state.query = $("#search-input").value.trim();
      state.folder = $("#folder-input").value;
      if (!state.query) {
        $("#search-input").focus();
        notify("Enter a question or phrase to search.");
        return;
      }
      goToPage("inspect");
    });
    $("#quote-input").addEventListener("input", renderQuoteStatus);
    $("#use-selection").addEventListener("mousedown", (event) => event.preventDefault());
    $("#use-selection").addEventListener("click", () => {
      const selection = String(window.getSelection() ?? "").replace(/\s+/g, " ").trim();
      if (!selection) {
        notify("Select words in the message first, then use this button.");
        return;
      }
      $("#quote-input").value = selection;
      renderQuoteStatus();
    });
    $("#capture-form").addEventListener("submit", saveFinding);
    $("#export-category").addEventListener("change", renderExport);
    $("#export-relevance").addEventListener("change", renderExport);
    $("#export-download").addEventListener("click", downloadCsv);
    $("#theme-toggle").addEventListener("click", toggleTheme);
    $("#command-open").addEventListener("click", openPalette);
    $("#command-filter").addEventListener("input", (event) => renderCommands(event.target.value));
    document.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openPalette();
      }
    });
  }
  initialise();
})();
