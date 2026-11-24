const $ = (s) => document.querySelector(s);
const RUNNING = new Set(["uploaded", "extracting", "captioning", "embedding"]);

let docs = [];
let pollTimer = null;
let controller = null;
let lastQuery = null;

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

/* ---------------- tabs ---------------- */
document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${btn.dataset.tab}`));
    if (btn.dataset.tab === "documents") renderDocs();
  };
});

/* ---------------- health ---------------- */
async function checkHealth() {
  const dot = $("#health .dot");
  const text = $("#healthText");
  try {
    const h = await api("/api/health");
    dot.className = "dot " + (h.ok ? "ok" : "bad");
    text.textContent = h.ok ? "connected" : "degraded";
    text.title = JSON.stringify(h.checks);
  } catch (e) {
    dot.className = "dot bad";
    text.textContent = "offline";
  }
}
checkHealth();
setInterval(checkHealth, 30000);

/* ---------------- documents ---------------- */
function statusPill(status) {
  return `<span class="pill ${status}">${esc(status)}</span>`;
}

function countsText(c = {}) {
  return `${c.text || 0} text · ${c.table || 0} tables · ${c.visual || 0} visuals`;
}

function renderDocCards() {
  const box = $("#docList");
  if (!docs.length) {
    box.innerHTML = `<div class="empty">No documents yet. Upload a PDF to begin.</div>`;
    return;
  }
  box.innerHTML = docs.map((d) => {
    const running = RUNNING.has(d.status) && d.status !== "uploaded";
    const p = d.progress || {};
    const pct = p.total ? Math.round((p.done / p.total) * 100) : (d.status === "indexed" ? 100 : 0);
    const canIngest = !["extracting", "captioning", "embedding"].includes(d.status);
    return `
      <div class="doc-card">
        <div>
          <div class="doc-name">${esc(d.source)} ${statusPill(d.status)}</div>
          <div class="doc-meta">${d.pages || "—"} pages · ${countsText(d.counts)} ${d.indexed_points != null ? `· ${d.indexed_points} points` : ""}</div>
          ${running || d.status === "uploaded" ? `<div class="progress"><div style="width:${pct}%"></div></div>` : ""}
          ${d.error ? `<div class="error" style="margin-top:8px">${esc(d.error)}</div>` : ""}
        </div>
        <div class="doc-actions">
          ${canIngest ? `<button class="btn primary" data-ingest="${d.document_id}">${d.status === "uploaded" ? "Ingest" : "Re-ingest"}</button>` : ""}
          <button class="btn danger" data-delete="${d.document_id}">Delete</button>
        </div>
      </div>`;
  }).join("");

  box.querySelectorAll("[data-ingest]").forEach((b) => { b.onclick = () => startIngest(b.dataset.ingest); });
  box.querySelectorAll("[data-delete]").forEach((b) => { b.onclick = () => removeDoc(b.dataset.delete); });
}

function renderDocsTable() {
  const body = $("#docsBody");
  if (!docs.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty">No documents yet.</td></tr>`;
    return;
  }
  body.innerHTML = docs.map((d) => `
    <tr>
      <td><strong>${esc(d.source)}</strong><div class="doc-meta">${esc(d.document_id)}</div></td>
      <td>${statusPill(d.status)}</td>
      <td>${d.pages || "—"}</td>
      <td>${countsText(d.counts)}</td>
      <td>${d.indexed_points ?? "—"}</td>
      <td><button class="btn danger" data-delete="${d.document_id}">Delete</button></td>
    </tr>`).join("");
  body.querySelectorAll("[data-delete]").forEach((b) => { b.onclick = () => removeDoc(b.dataset.delete); });
}

function renderDocs() {
  renderDocCards();
  renderDocsTable();
}

async function fetchDocs() {
  try {
    const res = await api("/api/documents");
    docs = res.documents || [];
    renderDocs();
    schedulePoll();
  } catch (e) {
    console.error(e);
  }
}

function schedulePoll() {
  clearTimeout(pollTimer);
  const busy = docs.some((d) => ["uploaded", "extracting", "captioning", "embedding"].includes(d.status));
  if (busy) pollTimer = setTimeout(fetchDocs, 1500);
}

async function startIngest(id) {
  try {
    await api(`/api/documents/${id}/ingest`, { method: "POST" });
    await fetchDocs();
  } catch (e) {
    alert(`Ingest failed: ${e.message}`);
  }
}

async function removeDoc(id) {
  if (!confirm("Delete this document, its points and its assets?")) return;
  try {
    await api(`/api/documents/${id}`, { method: "DELETE" });
    await fetchDocs();
  } catch (e) {
    alert(`Delete failed: ${e.message}`);
  }
}

/* ---------------- upload ---------------- */
async function upload(file) {
  if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
    alert("Please choose a PDF.");
    return;
  }
  const drop = $("#dropzone");
  drop.querySelector(".dz-title").textContent = `Uploading ${file.name}…`;
  try {
    const form = new FormData();
    form.append("file", file);
    const manifest = await api("/api/documents", { method: "POST", body: form });
    await fetchDocs();
    await startIngest(manifest.document_id);
  } catch (e) {
    alert(`Upload failed: ${e.message}`);
  } finally {
    drop.querySelector(".dz-title").textContent = "Drop a PDF here";
  }
}

const dz = $("#dropzone");
const input = $("#fileInput");
dz.onclick = () => input.click();
$("#browse").onclick = (e) => { e.stopPropagation(); input.click(); };
input.onchange = () => { if (input.files[0]) upload(input.files[0]); input.value = ""; };
dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("drag"); };
dz.ondragleave = () => dz.classList.remove("drag");
dz.ondrop = (e) => {
  e.preventDefault(); dz.classList.remove("drag");
  if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
};

/* ---------------- search ---------------- */
document.querySelectorAll("#modalityChips .chip").forEach((chip) => {
  chip.onclick = () => {
    document.querySelectorAll("#modalityChips .chip").forEach((c) => c.classList.toggle("active", c === chip));
  };
});
$("#k").oninput = (e) => { $("#kOut").textContent = e.target.value; };

$("#searchForm").onsubmit = (e) => {
  e.preventDefault();
  ask($("#question").value.trim());
};

$("#stopBtn").onclick = () => {
  if (controller) controller.abort();
  finishStream();
};

function currentModalities() {
  const active = [...document.querySelectorAll("#modalityChips .chip.active")][0];
  return active && active.dataset.mod ? [active.dataset.mod] : null;
}

function resetAnswer() {
  $("#answer").hidden = false;
  $("#answerBody").textContent = "";
  $("#answerBody").classList.add("streaming");
  $("#sources").innerHTML = "";
  $("#route").textContent = "…";
  $("#route").className = "route";
  $("#evidence").innerHTML = "";
  $("#stopBtn").hidden = false;
}

function finishStream() {
  $("#stopBtn").hidden = true;
  $("#answerBody").classList.remove("streaming");
  $("#askBtn").disabled = false;
}

function docLabel(source) {
  return (source || "").split("_")[0] || "doc";
}

function renderSources(sources) {
  $("#sources").innerHTML = sources.map((s, i) =>
    `<button class="src" data-src="${i}">${esc(docLabel(s.source))} · p${s.page} · ${esc(s.modality)}</button>`).join("");
  $("#sources").querySelectorAll("[data-src]").forEach((b) => {
    b.onclick = () => {
      const s = sources[Number(b.dataset.src)];
      if (s.modality === "visual" && s.asset_path) openLightbox(`/assets/${s.asset_path}`);
      else document.getElementById(`hit-${Number(b.dataset.src)}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
}

function renderEvidence(sources) {
  $("#evidence").innerHTML = sources.map((s, i) => {
    const thumb = s.modality === "visual" && s.asset_path
      ? `<img class="hit-thumb" src="/assets/${s.asset_path}" alt="p${s.page}" data-open="/assets/${s.asset_path}">` : "";
    return `
      <div class="hit" id="hit-${i}">
        ${thumb}
        <div class="hit-body">
          <div class="hit-top">
            <span class="mod ${s.modality}">${esc(s.modality)}</span>
            <span>${esc(docLabel(s.source))} · page ${s.page}</span>
            <span class="score">${Number(s.score).toFixed(3)}</span>
          </div>
          <div class="hit-text">${esc(s.snippet || "")}</div>
        </div>
      </div>`;
  }).join("");
  $("#evidence").querySelectorAll("[data-open]").forEach((img) => {
    img.onclick = () => openLightbox(img.dataset.open);
  });
}

async function readSSE(res, onEvent) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      let data = "";
      raw.split("\n").forEach((line) => {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      });
      if (data) {
        try { onEvent(event, JSON.parse(data)); } catch (_) {}
      }
    }
  }
}

async function ask(question) {
  if (!question) return;
  if (controller) controller.abort();
  controller = new AbortController();
  lastQuery = question;

  resetAnswer();
  $("#askBtn").disabled = true;

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, k: Number($("#k").value), modalities: currentModalities(), stream: true }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    await readSSE(res, (event, data) => {
      if (event === "meta") {
        $("#route").textContent = data.route === "none" ? "no hits" : data.route;
        $("#route").className = "route " + (data.route === "vision" ? "vision" : "");
        renderSources(data.sources || []);
        renderEvidence(data.sources || []);
      } else if (event === "token") {
        $("#answerBody").textContent += data.text;
      } else if (event === "done") {
        finishStream();
      } else if (event === "error") {
        $("#answerBody").textContent += `\n\n[error] ${data.message}`;
        finishStream();
      }
    });
  } catch (e) {
    if (e.name !== "AbortError") {
      $("#answerBody").textContent = `Request failed: ${e.message}`;
    }
  } finally {
    finishStream();
    controller = null;
  }
}

/* ---------------- lightbox ---------------- */
function openLightbox(src) {
  $("#lightboxImg").src = src;
  $("#lightbox").classList.add("open");
}
$("#lightbox").onclick = () => {
  $("#lightbox").classList.remove("open");
  $("#lightboxImg").src = "";
};
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#lightbox").click(); });

fetchDocs();
