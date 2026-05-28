"use strict";

const $ = (s) => document.querySelector(s);

const fileInput = $("#file"), dropzone = $("#dropzone"), fileName = $("#file-name");
const btnProcessar = $("#processar"), chkIa = $("#ia"), status = $("#status");
const uploader = $("#uploader"), secProg = $("#progresso"), barra = $("#barra"), progTxt = $("#prog-txt");
const secResult = $("#resultados"), tbody = $("#tbody"), vazioFiltro = $("#vazio-filtro");
const cTotal = $("#c-total"), cOk = $("#c-ok"), cRev = $("#c-rev"), cProg = $("#c-prog"), cProgFill = $("#c-prog-fill");
const busca = $("#busca"), filtroRev = $("#filtro-rev");
const btnExport = $("#exportar"), btnNovo = $("#novo");
// base salva + adicionar código
const abrirBaseBtn = $("#abrir-base"), baixarBaseBtn = $("#baixar-base");
const addToggle = $("#add-toggle"), addForm = $("#add-form"), addInput = $("#add-input"), addGo = $("#add-go");
// modal
const modal = $("#modal"), modalBg = $("#modal-bg");
const mCod = $("#m-cod"), mStatus = $("#m-status"), mPos = $("#m-pos"), mMeta = $("#m-meta");
const mMotivos = $("#m-motivos"), mDesc = $("#m-desc"), mRevisado = $("#m-revisado");
const mPrev = $("#m-prev"), mNext = $("#m-next"), mClose = $("#m-close"), mSalvar = $("#m-salvar");

let linhas = [];
let total = 0;
let modalIdx = -1;

/* ---------------- seleção de arquivo ---------------- */
dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
["dragover", "dragenter"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; mostrarArquivo(); } });
fileInput.addEventListener("change", mostrarArquivo);
function mostrarArquivo() {
  const f = fileInput.files[0];
  if (!f) return;
  fileName.textContent = f.name; fileName.hidden = false; btnProcessar.disabled = false;
}

/* ---------------- processar (stream NDJSON) ---------------- */
btnProcessar.addEventListener("click", processar);
btnNovo.addEventListener("click", reset);
abrirBaseBtn.addEventListener("click", abrirBase);
baixarBaseBtn.addEventListener("click", baixarBase);
addToggle.addEventListener("click", toggleAddForm);
addForm.addEventListener("submit", (e) => { e.preventDefault(); adicionarCodigo(); });

function reset() {
  linhas = []; total = 0; tbody.innerHTML = "";
  secResult.hidden = true; secProg.hidden = true; uploader.hidden = false;
  btnExport.hidden = true; btnNovo.hidden = true;
  addForm.hidden = true; addToggle.textContent = "+ código"; addInput.value = "";
  fileInput.value = ""; fileName.hidden = true; btnProcessar.disabled = true;
  setStatus("idle", "pronto");
}

function setStatus(cls, txt) { status.className = "badge " + cls; status.textContent = txt; }

async function processar() {
  const f = fileInput.files[0];
  if (!f) return;
  linhas = []; total = 0; tbody.innerHTML = "";
  uploader.hidden = true; secResult.hidden = false; secProg.hidden = false;
  btnExport.hidden = false; btnNovo.hidden = false; btnProcessar.disabled = true;
  setProgress(0, 0, "enviando…"); setStatus("running", "processando");
  atualizarMetricas();

  const fd = new FormData(); fd.append("file", f);
  try {
    const resp = await fetch(`/api/processar?ia=${chkIa.checked}`, { method: "POST", body: fd });
    if (!resp.ok || !resp.body) throw new Error("HTTP " + resp.status);
    const reader = resp.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const ln = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (ln) handleEvento(JSON.parse(ln));
      }
    }
  } catch (err) {
    setStatus("err", "erro"); alert("Erro ao processar: " + err.message);
  }
}

function handleEvento(ev) {
  if (ev.tipo === "inicio") {
    total = ev.dado.total; setProgress(0, total, `0 / ${total}`);
  } else if (ev.tipo === "item") {
    const idx = linhas.length; linhas.push(ev.dado); addRow(ev.dado, idx);
    setProgress(linhas.length, total, `${linhas.length} / ${total}`); atualizarMetricas();
  } else if (ev.tipo === "fim") {
    secProg.hidden = true; setStatus("ok", "pronto"); atualizarMetricas(); aplicarFiltros();
  } else if (ev.tipo === "erro") {
    secProg.hidden = true; setStatus("err", "erro"); alert(ev.dado.msg);
  }
}

/* ---------------- render da tabela ---------------- */
function chipFonte(fonte) {
  if (fonte && fonte.startsWith("http")) return `<span class="chip site">site</span>`;
  if (fonte && fonte.startsWith("catálogo")) return `<span class="chip cat">catálogo</span>`;
  return `<span class="chip none">—</span>`;
}

function addRow(d, idx) {
  const tr = document.createElement("tr");
  tr.dataset.idx = idx;
  pintarLinha(tr, d);
  tr.addEventListener("click", () => abrirModal(idx));
  if (!passaFiltro(d)) tr.hidden = true;
  tbody.appendChild(tr);
}

function pintarLinha(tr, d) {
  tr.classList.toggle("rev", !!d.precisa_revisao);
  const st = d.precisa_revisao ? `<span class="st rev">revisar</span>` : `<span class="st ok">OK</span>`;
  tr.innerHTML = `
    <td class="cell-cod">${esc(d.codigo)}</td>
    <td class="cell-qtd">${d.qtd_shipped ?? ""}</td>
    <td class="cell-ori">${esc(d.origem) || "—"}</td>
    <td class="cell-ncm">${esc(d.ncm_sugerida) || "—"}</td>
    <td class="cell-desc"><div class="clamp">${esc(d.descricao) || "<span style='color:var(--text-mute)'>(vazio)</span>"}</div></td>
    <td class="col-fonte">${chipFonte(d.fonte_url)}</td>
    <td class="col-status">${st}</td>`;
}

function atualizarLinha(idx) {
  const tr = tbody.querySelector(`tr[data-idx="${idx}"]`);
  if (tr) { pintarLinha(tr, linhas[idx]); tr.hidden = !passaFiltro(linhas[idx]); }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* ---------------- métricas ---------------- */
function atualizarMetricas() {
  const n = linhas.length, rev = linhas.filter((l) => l.precisa_revisao).length, ok = n - rev;
  cTotal.textContent = n; cOk.textContent = ok; cRev.textContent = rev;
  const pct = n ? Math.round((ok / n) * 100) : 0;
  cProg.textContent = pct + "%"; cProgFill.style.width = pct + "%";
}
function setProgress(n, tot, txt) { barra.style.width = tot ? Math.round((n / tot) * 100) + "%" : "0%"; progTxt.textContent = txt; }

/* ---------------- busca / filtro ---------------- */
function passaFiltro(d) {
  if (filtroRev.checked && !d.precisa_revisao) return false;
  const q = busca.value.trim().toLowerCase();
  if (q && !(`${d.codigo} ${d.descricao}`.toLowerCase().includes(q))) return false;
  return true;
}
function aplicarFiltros() {
  let visiveis = 0;
  for (const tr of tbody.children) {
    const ok = passaFiltro(linhas[+tr.dataset.idx]);
    tr.hidden = !ok; if (ok) visiveis++;
  }
  if (visiveis === 0) {
    vazioFiltro.textContent = linhas.length === 0
      ? "Base vazia. Adicione um código em “+ código” ou processe um invoice."
      : "Nenhum item bate com o filtro.";
    vazioFiltro.hidden = false;
  } else {
    vazioFiltro.hidden = true;
  }
}
busca.addEventListener("input", aplicarFiltros);
filtroRev.addEventListener("change", aplicarFiltros);

/* ---------------- modal de revisão ---------------- */
function indicesVisiveis() {
  return linhas.map((_, i) => i).filter((i) => passaFiltro(linhas[i]));
}

function abrirModal(idx) {
  modalIdx = idx;
  const d = linhas[idx];
  mCod.textContent = d.codigo;
  mStatus.className = "badge " + (d.precisa_revisao ? "running" : "ok");
  mStatus.textContent = d.precisa_revisao ? "revisar" : "OK";

  const vis = indicesVisiveis(), pos = vis.indexOf(idx);
  mPos.textContent = pos >= 0 ? `${pos + 1} / ${vis.length}` : "";

  const a = d.atributos || {};
  const meta = [
    ["Qtd", d.qtd_shipped, false], ["Origem", d.origem || "—", false],
    ["NCM", d.ncm_sugerida || "—", false], ["Fonte", d.fonte_url || "—", true],
    ["Aplicação", a.aplicacao || a.titulo || "—", true],
  ];
  mMeta.innerHTML = meta.map(([k, v, dim]) =>
    `<div class="cell"><div class="k">${k}</div><div class="v${dim ? " dim" : ""}">${esc(v)}</div></div>`).join("");

  if (d.precisa_revisao && (d.motivos || []).length) {
    mMotivos.hidden = false;
    mMotivos.innerHTML = `<b>Por que revisar:</b> ${esc(d.motivos.join("; "))}`;
  } else { mMotivos.hidden = true; }

  mDesc.value = d.descricao || "";
  mRevisado.checked = !d.precisa_revisao;
  modal.hidden = false;
  mDesc.focus();
  mDesc.setSelectionRange(mDesc.value.length, mDesc.value.length);
  atualizarNavBtns();
}

function atualizarNavBtns() {
  const vis = indicesVisiveis(), pos = vis.indexOf(modalIdx);
  mPrev.disabled = pos <= 0;
  mNext.disabled = pos < 0 || pos >= vis.length - 1;
}

function fecharModal() { modal.hidden = true; modalIdx = -1; }

function salvarModal(irProximo) {
  if (modalIdx < 0) return;
  const d = linhas[modalIdx];
  d.descricao = mDesc.value.trim();
  d.precisa_revisao = !mRevisado.checked;
  atualizarLinha(modalIdx);
  atualizarMetricas();
  if (irProximo) {
    const prox = vizinhoVisivel(modalIdx, +1);
    if (prox >= 0) { abrirModal(prox); return; }
  }
  fecharModal();
}

function vizinhoVisivel(fromIdx, dir) {
  for (let i = fromIdx + dir; i >= 0 && i < linhas.length; i += dir) {
    if (passaFiltro(linhas[i])) return i;
  }
  return -1;
}
function navegar(dir) {
  const prox = vizinhoVisivel(modalIdx, dir);
  if (prox >= 0) abrirModal(prox);
}

mClose.addEventListener("click", fecharModal);
modalBg.addEventListener("click", fecharModal);
mSalvar.addEventListener("click", () => salvarModal(false));
mPrev.addEventListener("click", () => navegar(-1));
mNext.addEventListener("click", () => navegar(+1));

document.addEventListener("keydown", (e) => {
  if (modal.hidden) return;
  if (e.key === "Escape") { e.preventDefault(); fecharModal(); }
  else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); salvarModal(true); }
});

/* ---------------- exportar ---------------- */
btnExport.addEventListener("click", async () => {
  if (!linhas.length) return;
  const rotulo = btnExport.textContent;
  btnExport.disabled = true; btnExport.textContent = "gerando…";
  try {
    const resp = await fetch("/api/exportar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ linhas }),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const blob = await resp.blob(), url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url; a.download = "descricoes_duimp.xlsx";
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  } catch (err) { alert("Erro ao exportar: " + err.message); }
  finally { btnExport.disabled = false; btnExport.textContent = rotulo; }
});

/* ---------------- base salva (cache) + adicionar código ---------------- */
function entrarResultados() {
  uploader.hidden = true; secProg.hidden = true; secResult.hidden = false;
  btnExport.hidden = false; btnNovo.hidden = false;
}
function renderTodas() {
  tbody.innerHTML = "";
  linhas.forEach((d, i) => addRow(d, i));
  atualizarMetricas(); aplicarFiltros();
}

async function abrirBase() {
  const r = abrirBaseBtn.textContent;
  abrirBaseBtn.disabled = true; abrirBaseBtn.textContent = "carregando…";
  try {
    const resp = await fetch("/api/base");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    linhas = data.linhas || []; total = linhas.length; modalIdx = -1;
    entrarResultados(); renderTodas();
    setStatus(linhas.length ? "ok" : "idle", linhas.length ? `base · ${linhas.length}` : "base vazia");
  } catch (err) { alert("Erro ao abrir a base: " + err.message); }
  finally { abrirBaseBtn.disabled = false; abrirBaseBtn.textContent = r; }
}

async function baixarBase() {
  const r = baixarBaseBtn.textContent;
  baixarBaseBtn.disabled = true; baixarBaseBtn.textContent = "gerando…";
  try {
    const resp = await fetch("/api/base/planilha");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const blob = await resp.blob(), url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url; a.download = "base_descricoes.xlsx";
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  } catch (err) { alert("Erro ao baixar a base: " + err.message); }
  finally { baixarBaseBtn.disabled = false; baixarBaseBtn.textContent = r; }
}

function toggleAddForm() {
  const mostrar = addForm.hidden;
  addForm.hidden = !mostrar;
  addToggle.textContent = mostrar ? "fechar" : "+ código";
  if (mostrar) addInput.focus();
}

async function adicionarCodigo() {
  const cod = addInput.value.trim();
  if (!cod) { addInput.focus(); return; }
  const r = addGo.textContent;
  addGo.disabled = true; addInput.disabled = true; addGo.textContent = "buscando…";
  try {
    const resp = await fetch(`/api/adicionar?ia=${chkIa.checked}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: cod }),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    let idx = linhas.findIndex((l) => l.codigo === d.codigo);
    if (idx >= 0) { linhas[idx] = d; atualizarLinha(idx); }
    else { idx = linhas.length; linhas.push(d); addRow(d, idx); }
    total = linhas.length;
    atualizarMetricas(); aplicarFiltros(); flashLinha(idx);
    addInput.value = "";
  } catch (err) { alert("Erro ao adicionar: " + err.message); }
  finally { addGo.disabled = false; addInput.disabled = false; addGo.textContent = r; addInput.focus(); }
}

function flashLinha(idx) {
  const tr = tbody.querySelector(`tr[data-idx="${idx}"]`);
  if (!tr || tr.hidden) return;
  tr.scrollIntoView({ block: "nearest", behavior: "smooth" });
  tr.classList.remove("flash"); void tr.offsetWidth; tr.classList.add("flash");
}
