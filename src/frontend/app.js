"use strict";

/* ===================== infra ===================== */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* O navegador lembra a área usada (cadastro/conversores) e o token de acesso
   ao cadastro. O token vale SÓ pro dia (o servidor também confere): no dia
   seguinte a senha é pedida de novo. */
const TOKEN_KEY = "lbwma_acesso";
const DIA_KEY = "lbwma_acesso_dia";
const AREA_KEY = "lbwma_area";
const hoje = () => new Date().toLocaleDateString("sv"); // YYYY-MM-DD local
function tokenAcesso() {
  if (localStorage.getItem(DIA_KEY) !== hoje()) {
    localStorage.removeItem(TOKEN_KEY);
    return "";
  }
  return localStorage.getItem(TOKEN_KEY) || "";
}
const hdrsAcesso = () => (tokenAcesso() ? { "X-Acesso": tokenAcesso() } : {});

/* 401 em qualquer chamada da API = token venceu (virou o dia) ou senha trocou:
   esquece o token e pede a senha de novo. */
function tratar401(url, status) {
  if (status === 401 && !url.startsWith("/api/auth")) {
    localStorage.removeItem(TOKEN_KEY);
    abrirSenha();
  }
}

async function jget(url) {
  const r = await fetch(url, { headers: hdrsAcesso() });
  if (!r.ok) { tratar401(url, r.status); const e = new Error("HTTP " + r.status); e.status = r.status; throw e; }
  return r.json();
}
async function jsend(url, method, body) {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json", ...hdrsAcesso() }, body: JSON.stringify(body) });
  if (!r.ok) {
    tratar401(url, r.status);
    let m = "HTTP " + r.status;
    try { const e = await r.json(); if (e.erro) m = e.erro; } catch (_) {}
    const e = new Error(m); e.status = r.status; throw e;
  }
  return r.json();
}

let toastT = null;
function toast(msg, cls = "ok") {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast " + cls; t.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => { t.hidden = true; }, 3200);
}
function setStatus(cls, txt) { const s = $("#status"); s.className = "badge " + cls; s.textContent = txt; }

/* ===================== campos da ficha ===================== */
// [grupo, chave, rótulo, tipo, opções]
const CAMPOS = [
  ["DUIMP", "cod_ss", "Cód. interno (SS)", "text"],
  ["DUIMP", "cod_sisc", "Cód. Siscomex", "text"],
  ["DUIMP", "fabricante", "Fabricante", "text"],
  ["DUIMP", "ncm", "NCM", "text"],
  ["DUIMP", "peso", "Peso", "text"],
  ["DUIMP", "medida", "Medida", "text"],
  ["DUIMP", "cclasstrib", "cClassTrib", "text"],
  ["DUIMP", "pais_origem", "País de origem", "text"],
  ["DUIMP", "fabric_revend", "Fabric/Revend (Siscomex)", "text"],
  ["DUIMP", "nve_materia_prima", "NVE matéria-prima", "text"],
  ["DUIMP", "nve_processo", "NVE processo", "text"],
  ["DUIMP", "nve_acabamento", "NVE acabamento", "text"],
  ["DUIMP", "desc_sisc", "Descrição Siscomex (DUIMP)", "textarea"],
  ["Comercial / logística", "descricao", "Descrição (comercial)", "textarea"],
  ["Comercial / logística", "un_medida_entrada", "Un. medida entrada", "text"],
  ["Comercial / logística", "qtd_embalagem_entrada", "Qtd. embalagem entrada", "text"],
  ["Comercial / logística", "un_medida_saida", "Un. medida saída", "text"],
  ["Comercial / logística", "qtd_embalagem_saida", "Qtd. embalagem saída", "text"],
  ["Comercial / logística", "localizacao_estoque", "Localização no estoque", "text"],
  ["Comercial / logística", "revenda_uso_interno", "Revenda / Uso interno", "select", ["", "Revenda", "Uso interno"]],
  ["Técnico", "aplicacoes", "Aplicações / dados técnicos", "textarea"],
  ["Técnico", "veiculos", "Veículos", "text"],
  ["Técnico", "caracteristicas", "Características (opcional)", "textarea"],
];
const ROTULOS = Object.fromEntries(CAMPOS.map((c) => [c[1], c[2]]));
ROTULOS.imagem = "Imagem";
const OBRIGATORIOS = new Set([
  "fabricante", "cod_ss", "cod_sisc", "peso", "medida", "ncm", "desc_sisc",
  "nve_materia_prima", "nve_processo", "nve_acabamento", "pais_origem",
  "fabric_revend", "descricao", "un_medida_entrada", "qtd_embalagem_entrada",
  "un_medida_saida", "qtd_embalagem_saida", "localizacao_estoque", "aplicacoes",
  "veiculos", "revenda_uso_interno", "imagem",
]);
// Campos com padrão global (não-laranja quando o padrão está setado).
const COM_PADRAO = new Set(["pais_origem", "fabric_revend"]);
const TEXTAREAS = new Set(["desc_sisc", "descricao", "aplicacoes", "caracteristicas"]);

/* ===================== estado ===================== */
let linhas = [];                 // todos os produtos do cadastro
let porCodigo = new Map();       // codigo -> produto
const selecionados = new Set();  // codigos marcados pra exportar
let vista = [];                  // produtos visíveis (filtrados), em ordem
let modalCod = null;             // produto aberto na ficha
let dirty = false;               // ficha tem edição não salva?
let padroes = {};                // padrões nível-declaração (pais_origem, fabric_revend)

/* ===================== carregar catálogo ===================== */
let cadastroCarregado = false;
async function carregar() {
  setStatus("running", "carregando");
  try {
    const [data, pad] = await Promise.all([jget("/api/produtos"), jget("/api/configuracoes")]);
    padroes = pad || {};
    linhas = data.linhas || [];
    porCodigo = new Map(linhas.map((p) => [p.codigo, p]));
    cadastroCarregado = true;
    render();
    setStatus(linhas.length ? "ok" : "idle", `cadastro · ${linhas.length}`);
  } catch (err) {
    if (err.status === 401) { setStatus("idle", "pronto"); return; } // tratar401 já pediu a senha
    setStatus("err", "erro");
    toast("Erro ao carregar o cadastro: " + err.message, "err");
  }
}

function passaFiltro(p) {
  if ($("#filtro-inc").checked && !p.incompleto) return false;
  if ($("#filtro-sel").checked && !selecionados.has(p.codigo)) return false;
  const q = $("#busca").value.trim().toLowerCase();
  if (q && !(`${p.codigo} ${p.desc_sisc} ${p.aplicacoes} ${p.descricao}`.toLowerCase().includes(q))) return false;
  return true;
}

/* ===================== render da tabela ===================== */
function chipFonte(f) {
  if (f && f.startsWith("http")) return `<span class="chip site">site</span>`;
  if (f && f.startsWith("catálogo")) return `<span class="chip cat">catálogo</span>`;
  return `<span class="chip none">—</span>`;
}
function linhaHTML(p) {
  const st = p.incompleto ? `<span class="st rev">incompleto</span>` : `<span class="st ok">completo</span>`;
  const sel = selecionados.has(p.codigo);
  return `
    <td class="cell-check"><input type="checkbox" data-sel="${esc(p.codigo)}" ${sel ? "checked" : ""}></td>
    <td class="cell-cod">${esc(p.codigo)}</td>
    <td class="cell-fab">${esc(p.fabricante) || "—"}</td>
    <td class="cell-ncm">${esc(p.ncm) || "—"}</td>
    <td class="cell-desc"><div class="clamp">${esc(p.desc_sisc) || "<span style='color:var(--text-mute)'>(sem descrição)</span>"}</div></td>
    <td class="col-fonte">${chipFonte(p.fonte_url)}</td>
    <td class="col-status">${st}</td>`;
}
function render() {
  vista = linhas.filter(passaFiltro);
  const tb = $("#tbody");
  tb.innerHTML = "";
  for (const p of vista) {
    const tr = document.createElement("tr");
    tr.dataset.cod = p.codigo;
    if (p.incompleto) tr.classList.add("rev");
    if (selecionados.has(p.codigo)) tr.classList.add("sel");
    tr.innerHTML = linhaHTML(p);
    tr.addEventListener("click", (e) => {
      if (e.target.closest("input[data-sel]")) return;
      abrirFicha(p.codigo);
    });
    tb.appendChild(tr);
  }
  const vazio = $("#vazio-filtro");
  if (vista.length === 0) {
    vazio.textContent = linhas.length === 0
      ? "Cadastro vazio. Processe um invoice ou adicione um código."
      : "Nenhum produto bate com o filtro.";
    vazio.hidden = false;
  } else { vazio.hidden = true; }
  atualizarMetricas();
  sincronizarCheckAll();
}
function atualizarLinha(cod) {
  const tr = $(`#tbody tr[data-cod="${CSS.escape(cod)}"]`);
  const p = porCodigo.get(cod);
  if (!tr || !p) return;
  tr.classList.toggle("rev", !!p.incompleto);
  tr.classList.toggle("sel", selecionados.has(cod));
  tr.innerHTML = linhaHTML(p);
}
function atualizarMetricas() {
  const n = linhas.length;
  const inc = linhas.filter((p) => p.incompleto).length;
  const ok = n - inc;
  $("#c-total").textContent = n;
  $("#c-ok").textContent = ok;
  $("#c-inc").textContent = inc;
  const pct = n ? Math.round((ok / n) * 100) : 0;
  $("#c-prog").textContent = pct + "%";
  $("#c-prog-fill").style.width = pct + "%";
}

/* ===================== seleção / exportar ===================== */
function atualizarExportBtn() {
  const n = selecionados.size;
  const b = $("#exportar");
  b.textContent = `Exportar (${n})`;
  b.disabled = n === 0;
  const info = $("#sel-info");
  info.hidden = n === 0;
  info.textContent = n ? `${n} selecionado${n > 1 ? "s" : ""}` : "";
}
function sincronizarCheckAll() {
  const visiveis = vista.map((p) => p.codigo);
  const todos = visiveis.length > 0 && visiveis.every((c) => selecionados.has(c));
  $("#check-all").checked = todos;
}
$("#tbody").addEventListener("change", (e) => {
  const cb = e.target.closest("input[data-sel]");
  if (!cb) return;
  const cod = cb.dataset.sel;
  if (cb.checked) selecionados.add(cod); else selecionados.delete(cod);
  atualizarExportBtn();
  if ($("#filtro-sel").checked) {
    render();                                  // "só selecionados": a linha some/aparece na hora
  } else {
    const tr = cb.closest("tr");
    if (tr) tr.classList.toggle("sel", cb.checked);
    sincronizarCheckAll();
  }
});
$("#check-all").addEventListener("change", (e) => {
  for (const p of vista) {
    if (e.target.checked) selecionados.add(p.codigo); else selecionados.delete(p.codigo);
  }
  render();
  atualizarExportBtn();
});
$("#busca").addEventListener("input", render);
$("#filtro-inc").addEventListener("change", render);
$("#filtro-sel").addEventListener("change", render);

/* ===================== ficha do produto ===================== */
function construirForm(p) {
  const grupos = {};
  for (const [g] of CAMPOS) grupos[g] = grupos[g] || [];
  for (const [g, key, label, tipo, opts] of CAMPOS) grupos[g].push({ key, label, tipo, opts });

  let html = "";
  for (const g of Object.keys(grupos)) {
    html += `<div class="grp"><div class="grp-title">${esc(g)}</div><div class="grp-fields">`;
    for (const f of grupos[g]) {
      const v = p[f.key] ?? "";
      const req = OBRIGATORIOS.has(f.key);
      const missing = (p.faltando || []).includes(f.key);
      const cls = `fld${TEXTAREAS.has(f.key) ? " full" : ""}${req ? " req" : ""}${missing ? " missing" : ""}`;
      let campo;
      if (f.tipo === "textarea") {
        campo = `<textarea data-key="${f.key}" spellcheck="false">${esc(v)}</textarea>`;
      } else if (f.tipo === "select") {
        const ops = f.opts.map((o) => `<option value="${esc(o)}" ${o === v ? "selected" : ""}>${esc(o || "—")}</option>`).join("");
        campo = `<select data-key="${f.key}">${ops}</select>`;
      } else {
        const ph = (!v && COM_PADRAO.has(f.key) && padroes[f.key]) ? ` placeholder="padrão: ${esc(padroes[f.key])}"` : "";
        campo = `<input data-key="${f.key}" value="${esc(v)}"${ph} autocomplete="off" spellcheck="false">`;
      }
      html += `<div class="${cls}"><label>${esc(f.label)}</label>${campo}</div>`;
    }
    html += `</div></div>`;
  }
  $("#ficha-form").innerHTML = html;
  $("#ficha-form").querySelectorAll("[data-key]").forEach((el) => el.addEventListener("input", () => { dirty = true; }));
}

function renderImagem(p) {
  const box = $("#ficha-img-box");
  if (p.tem_imagem) {
    box.innerHTML = `<img src="/api/produtos/${encodeURIComponent(p.codigo)}/imagem?t=${Date.now()}&acesso=${encodeURIComponent(tokenAcesso())}" alt="imagem">`;
    $("#img-remove-btn").hidden = false;
  } else {
    box.innerHTML = `<span class="ficha-img-vazia">sem imagem</span>`;
    $("#img-remove-btn").hidden = true;
  }
}
function renderFalta(p) {
  const el = $("#ficha-falta");
  const falta = p.faltando || [];
  if (!falta.length) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<span class="lab">faltando pra completar (${falta.length})</span>` +
    falta.map((k) => `<span class="chip-f">${esc(ROTULOS[k] || k)}</span>`).join("");
}

function preencherFicha(p) {
  modalCod = p.codigo;
  $("#m-cod").textContent = p.codigo;
  const badge = $("#m-status");
  badge.className = "badge " + (p.incompleto ? "running" : "ok");
  badge.textContent = p.incompleto ? "incompleto" : "completo";
  const idx = vista.findIndex((x) => x.codigo === p.codigo);
  $("#m-pos").textContent = idx >= 0 ? `${idx + 1} / ${vista.length}` : "";
  $("#m-fonte").innerHTML = p.fonte_url ? `Fonte: ${esc(p.fonte_url)}` : "";
  const mot = $("#m-motivos");
  if ((p.motivos || []).length) { mot.hidden = false; mot.innerHTML = `<b>Observações da descrição:</b> ${esc(p.motivos.join("; "))}`; }
  else mot.hidden = true;
  renderImagem(p);
  renderFalta(p);
  construirForm(p);
  dirty = false;
}

async function abrirFicha(cod) {
  const p = porCodigo.get(cod);
  if (!p) return;
  preencherFicha(p);
  $("#modal").hidden = false;
}
function fecharFicha() { $("#modal").hidden = true; modalCod = null; }

function coletarCampos() {
  const campos = {};
  $("#ficha-form").querySelectorAll("[data-key]").forEach((el) => { campos[el.dataset.key] = el.value; });
  return campos;
}
async function salvarFicha(stay = true) {
  if (!modalCod) return;
  const campos = coletarCampos();
  try {
    const p = await jsend(`/api/produtos/${encodeURIComponent(modalCod)}`, "PUT", { campos });
    porCodigo.set(p.codigo, p);
    const i = linhas.findIndex((x) => x.codigo === p.codigo);
    if (i >= 0) linhas[i] = p;
    atualizarLinha(p.codigo);
    atualizarMetricas();
    dirty = false;
    if (stay) {
      // atualiza status/falta sem recriar os inputs (não perde foco)
      const badge = $("#m-status");
      badge.className = "badge " + (p.incompleto ? "running" : "ok");
      badge.textContent = p.incompleto ? "incompleto" : "completo";
      renderFalta(p);
      $("#ficha-form").querySelectorAll("[data-key]").forEach((el) => {
        el.closest(".fld").classList.toggle("missing", (p.faltando || []).includes(el.dataset.key));
      });
      toast("Ficha salva", "ok");
    }
    return p;
  } catch (err) { toast("Erro ao salvar: " + err.message, "err"); throw err; }
}
async function navFicha(dir) {
  const idx = vista.findIndex((x) => x.codigo === modalCod);
  const prox = idx + dir;
  if (prox < 0 || prox >= vista.length) return;
  if (dirty) { try { await salvarFicha(false); } catch (_) { return; } }
  preencherFicha(vista[prox]);
}

$("#m-close").addEventListener("click", async () => { if (dirty) { try { await salvarFicha(false); } catch (_) {} } fecharFicha(); });
$("#modal-bg").addEventListener("click", async () => { if (dirty) { try { await salvarFicha(false); } catch (_) {} } fecharFicha(); });
$("#m-salvar").addEventListener("click", () => salvarFicha(true));
$("#m-prev").addEventListener("click", () => navFicha(-1));
$("#m-next").addEventListener("click", () => navFicha(+1));
document.addEventListener("keydown", (e) => {
  if ($("#modal").hidden) return;
  if (e.key === "Escape") { e.preventDefault(); $("#m-close").click(); }
  else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); salvarFicha(true); }
});

/* ---- imagem ---- */
$("#img-upload-btn").addEventListener("click", () => $("#img-file").click());
$("#img-file").addEventListener("change", async () => {
  const f = $("#img-file").files[0];
  if (!f || !modalCod) return;
  const fd = new FormData(); fd.append("file", f);
  try {
    const r = await fetch(`/api/produtos/${encodeURIComponent(modalCod)}/imagem`, { method: "POST", body: fd, headers: hdrsAcesso() });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const p = await r.json();
    aplicarProduto(p);
    toast("Imagem enviada", "ok");
  } catch (err) { toast("Erro no upload: " + err.message, "err"); }
  finally { $("#img-file").value = ""; }
});
$("#img-remove-btn").addEventListener("click", async () => {
  if (!modalCod) return;
  try {
    const r = await fetch(`/api/produtos/${encodeURIComponent(modalCod)}/imagem`, { method: "DELETE", headers: hdrsAcesso() });
    if (!r.ok) throw new Error("HTTP " + r.status);
    aplicarProduto(await r.json());
    toast("Imagem removida", "ok");
  } catch (err) { toast("Erro ao remover: " + err.message, "err"); }
});
function aplicarProduto(p) {
  porCodigo.set(p.codigo, p);
  const i = linhas.findIndex((x) => x.codigo === p.codigo);
  if (i >= 0) linhas[i] = p; else { linhas.push(p); }
  if (modalCod === p.codigo) { renderImagem(p); renderFalta(p);
    const badge = $("#m-status"); badge.className = "badge " + (p.incompleto ? "running" : "ok"); badge.textContent = p.incompleto ? "incompleto" : "completo"; }
  atualizarLinha(p.codigo);
  atualizarMetricas();
}

/* ===================== + código (buscar/cadastrar) ===================== */
$("#add-toggle").addEventListener("click", () => {
  const form = $("#add-form");
  const mostrar = form.hidden;
  form.hidden = !mostrar;
  $("#add-toggle").textContent = mostrar ? "fechar" : "+ código";
  if (mostrar) $("#add-input").focus();
});
$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const cod = $("#add-input").value.trim();
  if (!cod) { $("#add-input").focus(); return; }
  const ia = $("#ia").checked;
  const btn = $("#add-go"), rotulo = btn.textContent;
  btn.disabled = true; $("#add-input").disabled = true; btn.textContent = "buscando…";
  try {
    const p = await jsend(`/api/adicionar?ia=${ia}`, "POST", { codigo: cod });
    if (!porCodigo.has(p.codigo)) linhas.push(p);
    porCodigo.set(p.codigo, p);
    render();
    $("#add-input").value = "";
    toast(`Cadastrado: ${p.codigo}`, "ok");
    abrirFicha(p.codigo);
  } catch (err) { toast("Erro ao adicionar: " + err.message, "err"); }
  finally { btn.disabled = false; $("#add-input").disabled = false; btn.textContent = rotulo; $("#add-input").focus(); }
});

/* ===================== exportar ===================== */
$("#exportar").addEventListener("click", () => {
  if (!selecionados.size) return;
  $("#exp-count").innerHTML = `<b>${selecionados.size}</b> produto(s) selecionado(s).`;
  $("#exp-nome").value = "";
  $("#exp-msg").textContent = "";
  $("#modal-export").hidden = false;
  $("#exp-nome").focus();
});
document.querySelectorAll("[data-close-export]").forEach((el) => el.addEventListener("click", () => { $("#modal-export").hidden = true; }));
$("#exp-go").addEventListener("click", async () => {
  const nome = $("#exp-nome").value.trim() || "planilha";
  const tipo = document.querySelector("input[name='exp-tipo']:checked").value;
  const codigos = [...selecionados];
  const btn = $("#exp-go"), rotulo = btn.textContent;
  btn.disabled = true; btn.textContent = "gerando…"; $("#exp-msg").textContent = "";
  try {
    const rec = await jsend("/api/exportar", "POST", { nome, tipo, codigos });
    baixarPlanilha(rec.id);
    $("#modal-export").hidden = true;
    toast(`Planilha "${rec.nome}" salva (${rec.total} itens)`, "ok");
  } catch (err) { $("#exp-msg").textContent = err.message; }
  finally { btn.disabled = false; btn.textContent = rotulo; }
});
function baixarPlanilha(id) {
  const a = document.createElement("a");
  a.href = `/api/planilhas/${id}/download?acesso=${encodeURIComponent(tokenAcesso())}`;
  document.body.appendChild(a); a.click(); a.remove();
}

/* ===================== planilhas salvas ===================== */
async function abrirPlanilhas() {
  $("#modal-planilhas").hidden = false;
  const lista = $("#plan-list"); lista.innerHTML = "";
  try {
    const data = await jget("/api/planilhas");
    const ls = data.linhas || [];
    $("#plan-vazio").hidden = ls.length > 0;
    lista.innerHTML = ls.map((p) => `
      <li class="plan-item" data-id="${p.id}">
        <div class="pi-main">
          <div class="pi-nome">${esc(p.nome)}</div>
          <div class="pi-meta"><span class="pi-tipo ${p.tipo}">${p.tipo}</span> · ${p.total} itens · ${esc((p.criada_em || "").replace("T", " "))}</div>
        </div>
        <button class="btn-ghost sm" data-dl="${p.id}">baixar</button>
        <button class="icon-btn" data-del="${p.id}" title="apagar">✕</button>
      </li>`).join("");
  } catch (err) { toast("Erro ao listar planilhas: " + err.message, "err"); }
}
$("#abrir-planilhas").addEventListener("click", abrirPlanilhas);
document.querySelectorAll("[data-close-planilhas]").forEach((el) => el.addEventListener("click", () => { $("#modal-planilhas").hidden = true; }));
$("#plan-list").addEventListener("click", async (e) => {
  const dl = e.target.closest("[data-dl]"); const del = e.target.closest("[data-del]");
  if (dl) { baixarPlanilha(dl.dataset.dl); return; }
  if (del) {
    if (!confirm("Apagar esta planilha salva?")) return;
    try { await fetch(`/api/planilhas/${del.dataset.del}`, { method: "DELETE", headers: hdrsAcesso() }); abrirPlanilhas(); toast("Planilha apagada", "ok"); }
    catch (err) { toast("Erro ao apagar: " + err.message, "err"); }
  }
});

/* ===================== padrões (nível-declaração) ===================== */
async function abrirPadroes() {
  try {
    padroes = await jget("/api/configuracoes") || {};
    $("#pad-pais").value = padroes.pais_origem || "";
    $("#pad-fr").value = padroes.fabric_revend || "";
    $("#pad-msg").textContent = "";
    $("#modal-padroes").hidden = false;
    $("#pad-pais").focus();
  } catch (err) { toast("Erro ao abrir padrões: " + err.message, "err"); }
}
$("#abrir-padroes").addEventListener("click", abrirPadroes);
document.querySelectorAll("[data-close-padroes]").forEach((el) => el.addEventListener("click", () => { $("#modal-padroes").hidden = true; }));
$("#pad-go").addEventListener("click", async () => {
  const btn = $("#pad-go"), rotulo = btn.textContent;
  btn.disabled = true; btn.textContent = "salvando…"; $("#pad-msg").textContent = "";
  try {
    padroes = await jsend("/api/configuracoes", "PUT", { padroes: { pais_origem: $("#pad-pais").value.trim(), fabric_revend: $("#pad-fr").value.trim() } });
    await carregar();                 // recarrega: completude muda com o padrão
    $("#modal-padroes").hidden = true;
    toast("Padrões salvos", "ok");
  } catch (err) { $("#pad-msg").textContent = err.message; }
  finally { btn.disabled = false; btn.textContent = rotulo; }
});

/* ===================== processar invoice ===================== */
const dz = $("#dropzone"), fileInv = $("#file");
$("#btn-invoice").addEventListener("click", () => {
  $("#modal-invoice").hidden = false;
  $("#inv-prog").hidden = true; $("#file-name").hidden = true; $("#inv-processar").disabled = true; fileInv.value = "";
});
document.querySelectorAll("[data-close-invoice]").forEach((el) => el.addEventListener("click", () => { $("#modal-invoice").hidden = true; }));
dz.addEventListener("click", () => fileInv.click());
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInv.click(); } });
["dragover", "dragenter"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) { fileInv.files = e.dataTransfer.files; mostrarInvoice(); } });
fileInv.addEventListener("change", mostrarInvoice);
function mostrarInvoice() {
  const f = fileInv.files[0];
  if (!f) return;
  $("#file-name").textContent = f.name; $("#file-name").hidden = false; $("#inv-processar").disabled = false;
}
function setInvProg(n, tot, txt) { $("#inv-barra").style.width = tot ? Math.round((n / tot) * 100) + "%" : "0%"; $("#inv-prog-txt").textContent = txt; }

$("#inv-processar").addEventListener("click", async () => {
  const f = fileInv.files[0];
  if (!f) return;
  const ia = $("#ia").checked;
  $("#inv-prog").hidden = false; $("#inv-processar").disabled = true; setInvProg(0, 0, "enviando…");
  setStatus("running", "processando");
  const processados = [];
  let total = 0;
  const fd = new FormData(); fd.append("file", f);
  try {
    const resp = await fetch(`/api/processar?ia=${ia}`, { method: "POST", body: fd, headers: hdrsAcesso() });
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
        if (!ln) continue;
        const ev = JSON.parse(ln);
        if (ev.tipo === "inicio") { total = ev.dado.total; setInvProg(0, total, `0 / ${total}`); }
        else if (ev.tipo === "item") { processados.push(ev.dado.codigo); setInvProg(processados.length, total, `${processados.length} / ${total}`); }
        else if (ev.tipo === "erro") { throw new Error(ev.dado.msg); }
      }
    }
    // recarrega o cadastro e seleciona os processados pra exportar
    await carregar();
    selecionados.clear();
    processados.forEach((c) => selecionados.add(c));
    if (processados.length) $("#filtro-sel").checked = true;  // isola os achados na visualização
    render(); atualizarExportBtn();
    $("#modal-invoice").hidden = true;
    setStatus("ok", `cadastro · ${linhas.length}`);
    toast(`Invoice processado: ${processados.length} item(ns), já selecionados`, "ok");
  } catch (err) {
    setStatus("err", "erro"); toast("Erro ao processar: " + err.message, "err"); $("#inv-processar").disabled = false;
  }
});

/* ===================== conversores (área separada) ===================== */
/* Tabela de preços dos conversores de torque — editável, com busca
   instantânea. Área separada do cadastro DUIMP. */
let convLinhas = [];
let convCarregado = false;
let convId = null;          // id aberto no modal (null = novo)
let convRev = -1;           // revisão da tabela no servidor (pro tempo real)
let vistaAtual = "cadastro";

/* Busca tolerante: minúscula, sem acento (PISTÃO = pistao) e também sem
   separador (6L-80 = 6l80). convBase preserva o tamanho da string — por isso
   o realce do trecho encontrado continua alinhado com o texto original. */
const convBase = (s) => String(s || "").toLowerCase().split("").map((ch) => ch.normalize("NFD")[0]).join("");
const convCompacta = (s) => convBase(s).replace(/[^a-z0-9]/g, "");

function setView(v, lembrar = true) {
  if (v === "cadastro" && !tokenAcesso()) { abrirSenha(); return; }
  vistaAtual = v;
  if (lembrar) localStorage.setItem(AREA_KEY, v);
  document.body.classList.toggle("em-conversores", v === "conversores");
  $("#view-cadastro").hidden = v === "conversores";
  $("#view-conversores").hidden = v !== "conversores";
  document.querySelectorAll(".nav-tab").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  if (v === "conversores") {
    if (!convCarregado) convCarregarLista();
    $("#conv-busca").focus();
  } else if (!cadastroCarregado) {
    carregar();
  }
}
document.querySelectorAll(".nav-tab").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));

async function convCarregarLista() {
  try {
    const data = await jget("/api/conversores");
    convLinhas = data.linhas || [];
    convRev = data.rev ?? convRev;
    convCarregado = true;
    convRender();
  } catch (err) { toast("Erro ao carregar conversores: " + err.message, "err"); }
}

/* Tempo real: consulta a revisão da tabela a cada 2,5s; mudou (outra pessoa
   salvou), recarrega sozinho — ninguém precisa dar F5. O modal aberto não é
   tocado: só a lista atrás se atualiza. */
setInterval(async () => {
  if (document.hidden || vistaAtual !== "conversores" || !convCarregado) return;
  try {
    const { rev } = await jget("/api/conversores/rev");
    if (rev !== convRev) await convCarregarLista();
  } catch (_) { /* servidor fora do ar: tenta de novo no próximo tique */ }
}, 2500);

function convFiltra() {
  const q = convBase($("#conv-busca").value.trim());
  if (!q) return convLinhas;
  const qc = convCompacta(q);
  return convLinhas.filter((c) => {
    const alvo = convBase(`${c.modelo} ${c.preco_de} ${c.preco_ate} ${c.venda_impostos} ${c.anotacoes}`);
    return alvo.includes(q) || (qc && convCompacta(alvo).includes(qc));
  });
}

function convMarca(texto, q) {
  // realça o trecho buscado (comparação sem acento; índice alinha porque convBase preserva o tamanho)
  const t = esc(texto);
  if (!q) return t;
  const i = convBase(texto).indexOf(convBase(q));
  if (i < 0) return t;
  return esc(texto.slice(0, i)) + `<mark class="conv-hit">` + esc(texto.slice(i, i + q.length)) + `</mark>` + esc(texto.slice(i + q.length));
}

function convRender() {
  const q = $("#conv-busca").value.trim();
  const vista = convFiltra();
  const tb = $("#conv-tbody");
  tb.innerHTML = "";
  for (const c of vista) {
    const tr = document.createElement("tr");
    tr.dataset.id = c.id;
    tr.innerHTML = `
      <td class="cell-conv-mod">${convMarca(c.modelo, q)}</td>
      <td class="cell-conv-preco">${esc(c.preco_de) || "<span class='conv-dim'>—</span>"}</td>
      <td class="cell-conv-preco">${esc(c.preco_ate) || "<span class='conv-dim'>—</span>"}</td>
      <td class="cell-conv-venda">${convMarca(c.venda_impostos, q) || "<span class='conv-dim'>consultar</span>"}</td>
      <td class="cell-conv-anot">${convMarca(c.anotacoes, q)}</td>`;
    tr.addEventListener("click", () => convAbrir(c.id));
    tb.appendChild(tr);
  }
  const vazio = $("#conv-vazio");
  if (!vista.length) {
    vazio.textContent = convLinhas.length
      ? "Nenhum modelo bate com a busca."
      : "Tabela vazia. Adicione um modelo.";
    vazio.hidden = false;
  } else vazio.hidden = true;
  $("#conv-count").innerHTML = q
    ? `<b>${vista.length}</b> de ${convLinhas.length} modelos`
    : `<b>${convLinhas.length}</b> modelos`;
}
$("#conv-busca").addEventListener("input", convRender);

/* ---- modal: novo/editar/apagar ---- */
function convAbrir(id) {
  convId = id ?? null;
  const c = convLinhas.find((x) => x.id === convId) || {};
  $("#conv-m-titulo").textContent = convId ? c.modelo : "Novo modelo";
  $("#conv-f-modelo").value = c.modelo || "";
  $("#conv-f-de").value = c.preco_de || "";
  $("#conv-f-ate").value = c.preco_ate || "";
  $("#conv-f-venda").value = c.venda_impostos || "";
  $("#conv-f-anot").value = c.anotacoes || "";
  $("#conv-m-apagar").hidden = !convId;
  $("#conv-m-msg").textContent = "";
  $("#modal-conv").hidden = false;
  $("#conv-f-modelo").focus();
}
function convFechar() { $("#modal-conv").hidden = true; convId = null; }
document.querySelectorAll("[data-close-conv]").forEach((el) => el.addEventListener("click", convFechar));

/* Consultar conversores é livre; ALTERAR pede a senha do dia (a mesma do
   cadastro). Sem token, abre o modal de senha e a ação continua depois. */
function convExigeSenha(acao) {
  if (tokenAcesso()) return false;
  abrirSenha(acao);
  return true;
}

async function convSalvar() {
  const campos = {
    modelo: $("#conv-f-modelo").value.trim(),
    preco_de: $("#conv-f-de").value.trim(),
    preco_ate: $("#conv-f-ate").value.trim(),
    venda_impostos: $("#conv-f-venda").value.trim(),
    anotacoes: $("#conv-f-anot").value.trim(),
  };
  if (!campos.modelo) { $("#conv-m-msg").textContent = "informe o modelo"; $("#conv-f-modelo").focus(); return; }
  if (convExigeSenha(convSalvar)) return;
  const btn = $("#conv-m-salvar"), rotulo = btn.textContent;
  btn.disabled = true; btn.textContent = "salvando…"; $("#conv-m-msg").textContent = "";
  try {
    const c = convId
      ? await jsend(`/api/conversores/${convId}`, "PUT", { campos })
      : await jsend("/api/conversores", "POST", { campos });
    const i = convLinhas.findIndex((x) => x.id === c.id);
    if (i >= 0) convLinhas[i] = c; else convLinhas.push(c);
    convLinhas.sort((a, b) => a.modelo.localeCompare(b.modelo, "pt-BR", { sensitivity: "base" }));
    convRender();
    convFechar();
    toast(`${c.modelo} salvo`, "ok");
  } catch (err) {
    // 401 = token venceu/senha trocou: pede a senha e o salvar continua depois
    if (err.status === 401) abrirSenha(convSalvar);
    else $("#conv-m-msg").textContent = err.message;
  }
  finally { btn.disabled = false; btn.textContent = rotulo; }
}
$("#conv-m-salvar").addEventListener("click", convSalvar);
$("#conv-add").addEventListener("click", () => convAbrir(null));

async function convApagar() {
  if (!convId) return;
  if (convExigeSenha(convApagar)) return;
  const c = convLinhas.find((x) => x.id === convId);
  if (!confirm(`Apagar "${c ? c.modelo : "este modelo"}" da tabela de conversores?`)) return;
  try {
    const r = await fetch(`/api/conversores/${convId}`, { method: "DELETE", headers: hdrsAcesso() });
    if (r.status === 401) { localStorage.removeItem(TOKEN_KEY); abrirSenha(convApagar); return; }
    if (!r.ok) throw new Error("HTTP " + r.status);
    convLinhas = convLinhas.filter((x) => x.id !== convId);
    convRender();
    convFechar();
    toast("Modelo apagado", "ok");
  } catch (err) { toast("Erro ao apagar: " + err.message, "err"); }
}
$("#conv-m-apagar").addEventListener("click", convApagar);

document.addEventListener("keydown", (e) => {
  if ($("#modal-conv").hidden) return;
  if (e.key === "Escape") { e.preventDefault(); convFechar(); }
  else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); convSalvar(); }
});

/* ===================== senha (cadastro / alterar conversores) ===================== */
/* O mesmo modal serve aos dois fluxos. Sem ação pendente é o fluxo do cadastro
   (senha certa -> entra no cadastro). Com ação pendente (alterar conversores),
   a senha certa libera o token do dia e a ação continua de onde parou. */
let senhaAoLiberar = null;

function abrirSenha(aoLiberar = null) {
  senhaAoLiberar = aoLiberar || null;
  $("#senha-titulo").textContent = senhaAoLiberar ? "Alterar conversores" : "Acesso ao cadastro";
  $("#senha-hint").textContent = senhaAoLiberar
    ? "Consultar a tabela é livre, mas alterar pede a senha. Ela vale até o fim do dia — amanhã é pedida de novo."
    : "O cadastro (DUIMP, planilhas, padrões) é restrito. A senha vale até o fim do dia — amanhã ela é pedida de novo.";
  $("#senha-cancelar").textContent = senhaAoLiberar ? "Cancelar" : "Voltar aos conversores";
  $("#senha-msg").textContent = "";
  $("#senha-input").value = "";
  $("#modal-senha").hidden = false;
  $("#senha-input").focus();
}
function fecharSenha() { $("#modal-senha").hidden = true; }

async function senhaEntrar() {
  const senha = $("#senha-input").value;
  if (!senha) { $("#senha-input").focus(); return; }
  const btn = $("#senha-entrar"), rotulo = btn.textContent;
  btn.disabled = true; btn.textContent = "verificando…"; $("#senha-msg").textContent = "";
  try {
    const { token } = await jsend("/api/auth", "POST", { senha });
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(DIA_KEY, hoje());
    fecharSenha();
    toast("Acesso liberado até o fim do dia", "ok");
    const continuar = senhaAoLiberar;
    senhaAoLiberar = null;
    if (continuar) continuar(); else setView("cadastro");
  } catch (err) {
    $("#senha-msg").textContent = err.status === 401 ? "senha incorreta" : err.message;
    $("#senha-input").select();
  } finally { btn.disabled = false; btn.textContent = rotulo; }
}
$("#senha-entrar").addEventListener("click", senhaEntrar);
$("#senha-cancelar").addEventListener("click", () => {
  fecharSenha();
  if (senhaAoLiberar) { senhaAoLiberar = null; return; } // desistiu de alterar: fica onde está
  setView("conversores");
});
$("#senha-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); senhaEntrar(); }
  else if (e.key === "Escape") { e.preventDefault(); $("#senha-cancelar").click(); }
});

/* ===================== início ===================== */
/* Restaura a última área usada neste navegador. Sem token de acesso, o
   cadastro pede a senha; os conversores são abertos pra equipe toda. */
atualizarExportBtn();
{
  const salva = localStorage.getItem(AREA_KEY);
  const area = salva || "conversores";
  if (area === "cadastro" && !tokenAcesso()) {
    setView("conversores", false);
    abrirSenha();
  } else {
    setView(area, false);
  }
}
