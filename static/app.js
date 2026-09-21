const state = {
  authenticated: false,
  monitorRunning: false,
  pickedGatilho: null,
  pickedFila: null,
  firedRecently: new Set(),
};

const el = (id) => document.getElementById(id);

let searchTimers = {};

function debounceSearch(inputId, resultsId, onPick) {
  el(inputId).addEventListener("input", () => {
    clearTimeout(searchTimers[inputId]);
    const termo = el(inputId).value.trim();
    if (!termo) {
      el(resultsId).innerHTML = "";
      return;
    }
    searchTimers[inputId] = setTimeout(() => runSearch(termo, resultsId, onPick), 300);
  });
}

async function runSearch(termo, resultsId, onPick) {
  const resp = await fetch(`/api/search?q=${encodeURIComponent(termo)}`);
  if (!resp.ok) return;
  const itens = await resp.json();
  const container = el(resultsId);
  container.innerHTML = "";
  itens.forEach((track) => {
    const row = document.createElement("div");
    row.className = "search-result";
    row.innerHTML = `
      <img src="${track.image || ''}" alt="">
      <div class="sr-text">
        <div class="sr-name">${escapeHtml(track.name)}</div>
        <div class="sr-artist">${escapeHtml(track.artist)}</div>
      </div>`;
    row.addEventListener("click", () => onPick(track));
    container.appendChild(row);
  });
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.innerText = str;
  return d.innerHTML;
}

function renderPicked(pickedId, track) {
  const box = el(pickedId);
  if (!track) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = `
    <img src="${track.image || ''}" alt="">
    <div class="sr-text">
      <div class="sr-name">${escapeHtml(track.name)}</div>
      <div class="sr-artist">${escapeHtml(track.artist)}</div>
    </div>`;
}

debounceSearch("input-gatilho", "results-gatilho", (track) => {
  state.pickedGatilho = track;
  renderPicked("picked-gatilho", track);
  el("results-gatilho").innerHTML = "";
  el("input-gatilho").value = "";
  updateSaveButton();
});

debounceSearch("input-fila", "results-fila", (track) => {
  state.pickedFila = track;
  renderPicked("picked-fila", track);
  el("results-fila").innerHTML = "";
  el("input-fila").value = "";
  updateSaveButton();
});

function updateSaveButton() {
  el("save-rule").disabled = !(state.pickedGatilho && state.pickedFila);
}

el("save-rule").addEventListener("click", async () => {
  if (!state.pickedGatilho || !state.pickedFila) return;
  el("save-rule").disabled = true;
  el("save-rule").innerText = "Salvando...";

  await fetch("/api/rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gatilho: state.pickedGatilho, fila: state.pickedFila }),
  });

  state.pickedGatilho = null;
  state.pickedFila = null;
  renderPicked("picked-gatilho", null);
  renderPicked("picked-fila", null);
  el("save-rule").innerText = "Salvar regra";
  await refreshState();
});

el("monitor-toggle").addEventListener("click", async () => {
  const endpoint = state.monitorRunning ? "/api/monitor/stop" : "/api/monitor/start";
  el("monitor-toggle").disabled = true;
  await fetch(endpoint, { method: "POST" });
  await refreshState();
});

function renderRules(rules) {
  const list = el("rules-list");
  el("rules-count").innerText = rules.length;

  if (rules.length === 0) {
    list.innerHTML = `<p class="empty-state">Nenhuma regra cadastrada ainda. Crie uma ao lado —&gt;</p>`;
    return;
  }

  list.innerHTML = "";
  rules.forEach((r, idx) => {
    const row = document.createElement("div");
    row.className = "rule-row" + (r.ja_enfileirada ? " fired" : "");
    row.innerHTML = `
      <img src="${r.gatilho_imagem || ''}" alt="">
      <div class="rule-track">
        <div class="t-name">${escapeHtml(r.gatilho_nome)}</div>
        <div class="t-artist">${escapeHtml(r.gatilho_artista)}</div>
      </div>
      <div class="rail-line"></div>
      <div class="rule-track">
        <div class="t-name">${escapeHtml(r.fila_nome)}</div>
        <div class="t-artist">${escapeHtml(r.fila_artista)}</div>
      </div>
      <button class="remove-rule" title="Remover">×</button>
    `;
    row.querySelector(".remove-rule").addEventListener("click", async () => {
      await fetch(`/api/rules/${idx}`, { method: "DELETE" });
      await refreshState();
    });
    list.appendChild(row);
  });

  // segunda passada: reflete visualmente as que faltam colocar imagem
  list.querySelectorAll("img").forEach((img) => {
    img.onerror = () => { img.style.visibility = "hidden"; };
  });
}

function renderNowPlaying(np) {
  const box = el("now-playing");
  if (!np) {
    box.classList.remove("hidden");
    el("np-name").innerText = "Nada tocando no momento";
    el("np-artist").innerText = "—";
    el("np-image").src = "";
    el("np-pulse").classList.remove("live");
    return;
  }
  box.classList.remove("hidden");
  el("np-name").innerText = np.name;
  el("np-artist").innerText = np.artist;
  el("np-image").src = np.image || "";
  el("np-pulse").classList.toggle("live", !!np.is_playing);
}

function renderAuthArea(authenticated) {
  const area = el("auth-area");
  if (authenticated) {
    area.innerHTML = `<a class="logout" href="/logout">Desconectar</a>`;
  } else {
    area.innerHTML = "";
  }
}

async function refreshState() {
  const resp = await fetch("/api/state");
  const data = await resp.json();

  state.authenticated = data.authenticated;
  state.monitorRunning = data.monitor_running;

  renderAuthArea(data.authenticated);

  if (!data.authenticated) {
    el("login-gate").classList.remove("hidden");
    el("app-main").classList.add("hidden");
    el("now-playing").classList.add("hidden");
    return;
  }

  el("login-gate").classList.add("hidden");
  el("app-main").classList.remove("hidden");

  renderNowPlaying(data.now_playing);
  renderRules(data.rules);

  const toggle = el("monitor-toggle");
  toggle.disabled = false;
  toggle.classList.toggle("on", data.monitor_running);
  el("monitor-toggle-label").innerText = data.monitor_running
    ? "monitoramento ativo — parar"
    : "iniciar monitoramento";

  updateSaveButton();
}

refreshState();
setInterval(refreshState, 3000);
