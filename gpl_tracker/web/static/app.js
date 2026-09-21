// GPL Tracker - Frontend Application Logic
let currentVehicle = null;
let lastRefuelingRecord = null;
let allQuickStations = [];

document.addEventListener("DOMContentLoaded", () => {
  initApp();
  setupEventListeners();
});

async function initApp() {
  await loadVehicle();
  await loadDashboard();
  await loadHistory();
  await loadMunicipalities();
  await loadQuickStations();
  checkLastRefueling();
}

function setupEventListeners() {
  // Modal openers
  document.getElementById("btn-open-refueling")?.addEventListener("click", () => openRefuelingModal());
  document.getElementById("btn-open-settings")?.addEventListener("click", () => openSettingsModal());

  // Modal closers
  document.getElementById("btn-close-modal")?.addEventListener("click", closeRefuelingModal);
  document.getElementById("btn-cancel-refueling")?.addEventListener("click", closeRefuelingModal);
  document.getElementById("btn-close-settings")?.addEventListener("click", closeSettingsModal);
  document.getElementById("btn-cancel-settings")?.addEventListener("click", closeSettingsModal);

  // Close modals on backdrop click
  document.getElementById("modal-refueling")?.addEventListener("click", (e) => {
    if (e.target.id === "modal-refueling") closeRefuelingModal();
  });
  document.getElementById("modal-settings")?.addEventListener("click", (e) => {
    if (e.target.id === "modal-settings") closeSettingsModal();
  });

  // Station search and picker
  let searchDebounceTimer = null;
  document.getElementById("form-station-search")?.addEventListener("input", () => {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(triggerLiveStationSearch, 150);
  });
  document.getElementById("form-station-concelho")?.addEventListener("change", triggerLiveStationSearch);
  document.getElementById("btn-change-station")?.addEventListener("click", showStationPicker);
  document.getElementById("btn-toggle-fav-selected")?.addEventListener("click", toggleSelectedStationFav);

  // Forms
  document.getElementById("refueling-form")?.addEventListener("submit", saveRefueling);
  document.getElementById("settings-form")?.addEventListener("submit", saveSettings);

  // Live calculation listeners
  const liveInputs = ["form-distance", "form-amount", "form-lpg-price", "form-petrol-price"];
  liveInputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", updateLiveCalculations);
  });

  // Export buttons
  document.getElementById("btn-export-csv")?.addEventListener("click", () => {
    window.location.href = "/api/export/csv";
  });
  document.getElementById("btn-export-excel")?.addEventListener("click", () => {
    window.location.href = "/api/export/excel";
  });
}

// Format utilities (Portuguese format: 1.234,56 €)
function formatCurrency(val) {
  if (val === null || val === undefined || isNaN(val)) return "0,00 €";
  return new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR" }).format(val);
}

function formatNumber(val, decimals = 2) {
  if (val === null || val === undefined || isNaN(val)) return "0";
  return new Intl.NumberFormat("pt-PT", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(val);
}

// 1. Load Vehicle Profile
async function loadVehicle() {
  try {
    const res = await fetch("/api/vehicle");
    if (!res.ok) throw new Error("Erro ao carregar veículo");
    currentVehicle = await res.json();

    const titleParts = [];
    if (currentVehicle.make) titleParts.push(currentVehicle.make);
    if (currentVehicle.model) titleParts.push(currentVehicle.model);
    if (currentVehicle.engine) titleParts.push(currentVehicle.engine);
    const nameStr = titleParts.join(" ") || "Veículo GPL";

    const subHeaderEl = document.getElementById("vehicle-sub-header");
    if (subHeaderEl) {
      subHeaderEl.textContent =
        `${nameStr} • Investimento: ${formatCurrency(currentVehicle.conversion_cost)} (+${currentVehicle.lpg_consumption_increase}% consumo GPL)`;
    }

    // Populate settings form
    document.getElementById("set-cost").value = currentVehicle.conversion_cost;
    document.getElementById("set-date").value = currentVehicle.conversion_date || "";
    document.getElementById("set-odometer").value = currentVehicle.conversion_odometer || 0;
    document.getElementById("set-make").value = currentVehicle.make || "";
    document.getElementById("set-model").value = currentVehicle.model || "";
    document.getElementById("set-engine").value = currentVehicle.engine || "";
    document.getElementById("set-petrol-ref").value = currentVehicle.petrol_consumption || 7.0;
    document.getElementById("set-lpg-increase").value = currentVehicle.lpg_consumption_increase || 20.0;
  } catch (err) {
    console.error("Erro ao obter dados do veículo:", err);
  }
}

// 2. Load Dashboard Financial Summary
async function loadDashboard() {
  try {
    const res = await fetch("/api/dashboard");
    if (!res.ok) throw new Error("Erro ao carregar dashboard");
    const summary = await res.json();

    // Primary Metric Cards
    document.getElementById("metric-total-savings").textContent = formatCurrency(summary.total_savings);
    document.getElementById("metric-lpg-spent").textContent = `Gasto em GPL: ${formatCurrency(summary.total_lpg_spent)}`;

    document.getElementById("metric-avg-savings-km").textContent = `${formatNumber(summary.avg_savings_per_km, 3)} €/km`;
    document.getElementById("metric-avg-savings-100km").textContent = `${formatCurrency(summary.avg_savings_per_100km)} a cada 100 km`;

    document.getElementById("metric-total-km").textContent = `${formatNumber(summary.total_distance_km, 1)} km`;
    document.getElementById("metric-total-liters").textContent = `${formatNumber(summary.total_lpg_liters, 1)} L de GPL consumidos`;

    document.getElementById("metric-avg-consumption").textContent = `${formatNumber(summary.avg_lpg_consumption, 2)} L/100km`;
    document.getElementById("metric-equiv-consumption").textContent = `Eq. Gasolina: ${formatNumber(summary.avg_petrol_consumption, 2)} L/100km`;

    // Break-Even Card
    const targetCost = summary.conversion_cost;
    document.getElementById("be-target-label").textContent = `${formatCurrency(targetCost)} (Investimento)`;
    document.getElementById("be-stat-savings").textContent = formatCurrency(summary.total_savings);

    const be = summary.break_even;
    const badgeEl = document.getElementById("be-status-badge");
    const progressBarEl = document.getElementById("be-progress-bar");
    const mainTextEl = document.getElementById("be-main-text");
    const remainingValEl = document.getElementById("be-stat-remaining");
    const remainingLabelEl = document.getElementById("be-stat-remaining-label");
    const kmLeftEl = document.getElementById("be-stat-km-left");
    const timeLeftEl = document.getElementById("be-stat-time-left");

    // Progress Bar width (max 100%)
    const pct = Math.min(Math.max(summary.recovered_percent, 0), 100);
    progressBarEl.style.width = `${pct}%`;

    if (summary.is_recovered) {
      badgeEl.className = "status-badge status-recovered";
      badgeEl.textContent = "Investimento Recuperado";
      mainTextEl.textContent = `+${formatCurrency(summary.net_profit)} de poupança líquida após recuperação!`;
      mainTextEl.style.color = "var(--color-accent-light)";

      remainingLabelEl.textContent = "Lucro Líquido";
      remainingValEl.textContent = `+${formatCurrency(summary.net_profit)}`;
      remainingValEl.style.color = "var(--color-accent-light)";

      kmLeftEl.textContent = "0 km (Meta atingida)";
      timeLeftEl.textContent = "0 meses (Meta atingida)";
    } else {
      remainingLabelEl.textContent = "Falta Recuperar";
      remainingValEl.textContent = formatCurrency(summary.remaining_amount);
      remainingValEl.style.color = "var(--text-primary)";

      if (be.status === "insufficient_data") {
        badgeEl.className = "status-badge status-insufficient";
        badgeEl.textContent = "Dados Insuficientes";
        mainTextEl.textContent = `${formatNumber(summary.recovered_percent, 1)}% recuperado`;
        mainTextEl.style.color = "var(--color-petrol)";

        kmLeftEl.textContent = be.remaining_km ? `~${formatNumber(be.remaining_km, 0)} km` : "Dados insuficientes";
        timeLeftEl.textContent = "Dados insuficientes";
      } else {
        badgeEl.className = "status-badge status-recovering";
        badgeEl.textContent = "Em Recuperação";
        mainTextEl.textContent = `${formatNumber(summary.recovered_percent, 1)}% recuperado`;
        mainTextEl.style.color = "var(--color-petrol)";

        kmLeftEl.textContent = `~${formatNumber(be.remaining_km, 0)} km`;
        timeLeftEl.textContent = `~${formatNumber(be.remaining_months, 1)} meses`;
      }
    }
  } catch (err) {
    console.error("Erro ao carregar resumo do dashboard:", err);
  }
}

// 3. Load Refueling History Table
async function loadHistory() {
  try {
    const res = await fetch("/api/refuelings");
    if (!res.ok) throw new Error("Erro ao carregar histórico");
    const items = await res.json();

    const tbody = document.getElementById("refuelings-tbody");
    document.getElementById("refuelings-count").textContent = `${items.length} ${items.length === 1 ? "registo" : "registos"}`;

    if (items.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="14" style="text-align: center; color: var(--text-muted); padding: 3rem;">
            Nenhum abastecimento registado.<br>
            <button class="btn btn-primary btn-sm" style="margin-top: 0.75rem;" onclick="document.getElementById('btn-open-refueling').click()">
              + Registar primeiro abastecimento
            </button>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = items.map(item => {
      const formattedDate = item.date ? item.date.replace("T", " ") : "";
      let badgeClass = "badge-source user";
      let sourceLabel = "Manual";
      if (item.data_source === "api") {
        badgeClass = "badge-source api";
        sourceLabel = "DGEG";
      } else if (item.data_source === "cache") {
        badgeClass = "badge-source cache";
        sourceLabel = "Cache";
      }

      return `
        <tr>
          <td>${formattedDate}</td>
          <td>
            <div class="station-cell">
              <span class="station-cell-name">${escapeHtml(item.station_name || "Posto")}</span>
              <span class="station-cell-brand">${escapeHtml(item.station_brand || "")}</span>
            </div>
          </td>
          <td><strong>${formatNumber(item.distance_km, 1)} km</strong></td>
          <td>${formatNumber(item.lpg_price, 3)} €</td>
          <td>${formatNumber(item.petrol_price, 3)} €</td>
          <td><strong>${formatCurrency(item.amount_paid)}</strong></td>
          <td>${formatNumber(item.lpg_liters, 2)} L</td>
          <td>${formatNumber(item.lpg_consumption, 2)} L/100</td>
          <td>${formatNumber(item.equivalent_petrol_consumption, 2)} L/100</td>
          <td>${formatCurrency(item.estimated_petrol_cost)}</td>
          <td class="table-savings">+${formatCurrency(item.savings)}</td>
          <td style="font-weight: 700;">${formatCurrency(item.cumulative_savings)}</td>
          <td><span class="${badgeClass}">${sourceLabel}</span></td>
          <td>
            <div class="table-actions">
              <button class="btn-icon" title="Editar" onclick="editRefueling(${item.id})">✏️</button>
              <button class="btn-icon" title="Duplicar para hoje" onclick="duplicateRefueling(${item.id})">📋</button>
              <button class="btn-icon" title="Eliminar" onclick="deleteRefueling(${item.id})">🗑️</button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Erro ao carregar histórico:", err);
  }
}

// 4. Quick Habitual & Favorite Stations
async function loadQuickStations() {
  try {
    const res = await fetch("/api/stations/quick");
    if (!res.ok) return;
    allQuickStations = await res.json();

    const container = document.getElementById("quick-station-chips");
    if (!allQuickStations || allQuickStations.length === 0) {
      container.innerHTML = `<span style="font-size: 0.78rem; color: var(--text-muted);">Sem postos habituais ainda</span>`;
      return;
    }

    container.innerHTML = allQuickStations.map(st => {
      const star = st.is_favorite ? "★ " : "";
      return `
        <button type="button" class="station-chip" data-id="${st.id}" onclick="selectQuickStation(${st.id})">
          ${star}${escapeHtml(st.name)}
        </button>
      `;
    }).join("");
  } catch (err) {
    console.error("Erro ao obter postos habituais:", err);
  }
}

// 5. "+ Abasteci novamente" logic
async function checkLastRefueling() {
  try {
    const res = await fetch("/api/refuelings/last");
    if (!res.ok) return;
    lastRefuelingRecord = await res.json();
    const btnRepeat = document.getElementById("btn-quick-repeat");
    if (btnRepeat) {
      if (lastRefuelingRecord) {
        btnRepeat.style.display = "inline-flex";
        btnRepeat.title = `Reutilizar posto ${lastRefuelingRecord.station_name}`;
      } else {
        btnRepeat.style.display = "none";
      }
    }
  } catch (err) {
    console.error("Erro ao obter último abastecimento:", err);
  }
}

function repeatLastRefueling() {
  if (!lastRefuelingRecord) return;
  openRefuelingModal();
  if (lastRefuelingRecord.station_id) {
    selectQuickStation(lastRefuelingRecord.station_id);
  }
  // Focus directly on distance field for zero-friction entry!
  setTimeout(() => {
    document.getElementById("form-distance").focus();
  }, 100);
}

// 6. Station Selection and Auto-Filling Prices
// 6. Station Identification, Selection and Auto-Filling Prices
let currentSelectedStation = null;

async function loadMunicipalities() {
  try {
    const res = await fetch("/api/stations/municipalities");
    if (!res.ok) return;
    const munis = await res.json();
    const sel = document.getElementById("form-station-concelho");
    sel.innerHTML = `<option value="">Todos os Concelhos (${munis.length})</option>` +
      munis.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join("");
  } catch (err) {
    console.error("Erro ao carregar concelhos:", err);
  }
}

function getBrandClass(brand) {
  if (!brand) return "";
  const b = brand.toLowerCase();
  if (b.includes("galp")) return "galp";
  if (b.includes("repsol")) return "repsol";
  if (b.includes("bp")) return "bp";
  if (b.includes("prio")) return "prio";
  if (b.includes("cepsa")) return "cepsa";
  if (b.includes("auchan")) return "auchan";
  if (b.includes("shell")) return "shell";
  if (b.includes("intermarch")) return "intermarche";
  return "";
}

async function selectQuickStation(stationId) {
  try {
    const res = await fetch(`/api/stations/search?limit=1000`);
    if (res.ok) {
      const all = await res.json();
      const st = all.find(s => s.id === stationId);
      if (st) {
        selectStationItem(st);
        return;
      }
    }
  } catch (err) {}
  
  // Fallback if not found in search
  const st = allQuickStations.find(s => s.id === stationId);
  if (st) {
    selectStationItem(st);
  }
}

function selectStationItem(st) {
  currentSelectedStation = st;
  document.getElementById("form-station-id").value = st.id;
  document.getElementById("form-station-name").value = st.name;

  renderSelectedStationCard(st);

  // Hide picker and show selected card
  document.getElementById("station-picker-container").style.display = "none";
  document.getElementById("station-selected-container").style.display = "block";

  // Highlight quick chip if present
  document.querySelectorAll(".station-chip").forEach(el => {
    if (parseInt(el.getAttribute("data-id")) === st.id) {
      el.classList.add("selected");
    } else {
      el.classList.remove("selected");
    }
  });

  // Fetch prices
  fetchAndSetPrices(st.id);
  updateLiveCalculations();

  // Move focus to distance
  setTimeout(() => {
    document.getElementById("form-distance").focus();
  }, 100);
}

function renderSelectedStationCard(st) {
  const pillEl = document.getElementById("selected-brand-pill");
  pillEl.className = `brand-pill ${getBrandClass(st.brand)}`;
  pillEl.textContent = st.brand || "POSTO";

  document.getElementById("selected-station-name").textContent = st.name;
  document.getElementById("selected-station-address").textContent = st.address || "Morada não especificada";
  
  const concelhoDistrito = [st.municipality, st.district].filter(Boolean).join(" • ");
  document.getElementById("selected-station-concelho").textContent = concelhoDistrito || "Portugal";

  const favBtn = document.getElementById("btn-toggle-fav-selected");
  favBtn.textContent = st.is_favorite ? "★" : "☆";
  favBtn.style.color = st.is_favorite ? "#f59e0b" : "var(--text-secondary)";
}

function showStationPicker() {
  document.getElementById("station-selected-container").style.display = "none";
  document.getElementById("station-picker-container").style.display = "block";
  document.getElementById("form-station-search").focus();
  triggerLiveStationSearch();
}

async function triggerLiveStationSearch() {
  const q = document.getElementById("form-station-search").value.trim();
  const concelho = document.getElementById("form-station-concelho").value;
  const listEl = document.getElementById("station-results-list");

  listEl.style.display = "block";
  listEl.innerHTML = `<div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">A pesquisar postos...</div>`;

  try {
    const params = new URLSearchParams();
    if (q) params.append("q", q);
    if (concelho) params.append("municipality", concelho);
    params.append("limit", "40");

    const res = await fetch(`/api/stations/search?${params.toString()}`);
    if (!res.ok) throw new Error("Erro na pesquisa");
    const stations = await res.json();
    renderStationSearchResults(stations);
  } catch (err) {
    console.error("Erro ao pesquisar postos:", err);
    listEl.innerHTML = `<div style="padding: 1rem; text-align: center; color: var(--color-danger); font-size: 0.85rem;">Erro na pesquisa de postos</div>`;
  }
}

function renderStationSearchResults(stations) {
  const listEl = document.getElementById("station-results-list");
  const q = document.getElementById("form-station-search").value.trim();

  if (!stations || stations.length === 0) {
    listEl.innerHTML = `
      <div style="padding: 1.25rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
        Nenhum posto encontrado para esta pesquisa.<br>
        ${q ? `<button type="button" class="btn btn-secondary btn-sm" style="margin-top: 0.5rem;" onclick="createCustomStationFromSearch('${escapeHtml(q)}')">
          + Criar posto "${escapeHtml(q)}" manualmente
        </button>` : ''}
      </div>
    `;
    return;
  }

  listEl.innerHTML = stations.map(st => {
    const brandClass = getBrandClass(st.brand);
    const priceText = st.last_lpg_price ? `${formatNumber(st.last_lpg_price, 3)} €/L` : "";
    const favStar = st.is_favorite ? "★" : "☆";
    const favColor = st.is_favorite ? "color: #f59e0b;" : "color: var(--text-muted);";

    // Encode station JSON safely for click attribute
    const stJson = JSON.stringify(st).replace(/"/g, '&quot;');

    return `
      <div class="station-result-item" onclick="selectStationItem(${stJson})">
        <div class="station-result-left">
          <div class="station-result-name">
            <span class="brand-pill ${brandClass}">${escapeHtml(st.brand || "POSTO")}</span>
            <span>${escapeHtml(st.name)}</span>
          </div>
          <div class="station-result-address">${escapeHtml(st.address || st.municipality || "")}</div>
          <div style="font-size: 0.72rem; color: var(--text-muted);">
            ${escapeHtml(st.municipality || "")} • ${escapeHtml(st.district || "")}
          </div>
        </div>
        <div class="station-result-right">
          <div class="station-result-price">${priceText}</div>
          <button type="button" class="btn-icon" style="font-size: 1.1rem; ${favColor}" onclick="event.stopPropagation(); toggleStationFavFromList(${st.id})" title="Favorito">
            ${favStar}
          </button>
        </div>
      </div>
    `;
  }).join("");
}

async function toggleStationFavFromList(stationId) {
  try {
    const res = await fetch(`/api/stations/${stationId}/favorite`, { method: "POST" });
    if (res.ok) {
      await loadQuickStations();
      await triggerLiveStationSearch();
    }
  } catch (err) {
    console.error("Erro ao alternar favorito:", err);
  }
}

async function toggleSelectedStationFav() {
  if (!currentSelectedStation) return;
  try {
    const res = await fetch(`/api/stations/${currentSelectedStation.id}/favorite`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      currentSelectedStation.is_favorite = data.is_favorite;
      renderSelectedStationCard(currentSelectedStation);
      await loadQuickStations();
    }
  } catch (err) {
    console.error("Erro ao alternar favorito:", err);
  }
}

async function createCustomStationFromSearch(name) {
  const concelho = document.getElementById("form-station-concelho").value || "";
  try {
    const res = await fetch("/api/stations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        brand: "Independente",
        municipality: concelho,
        provider: "manual"
      })
    });
    if (res.ok) {
      const newSt = await res.json();
      selectStationItem(newSt);
    }
  } catch (err) {
    console.error("Erro ao criar posto:", err);
  }
}

async function fetchAndSetPrices(stationId) {
  const lpgInput = document.getElementById("form-lpg-price");
  const petrolInput = document.getElementById("form-petrol-price");
  const lpgTag = document.getElementById("lpg-price-tag");
  const petrolTag = document.getElementById("petrol-price-tag");

  lpgTag.textContent = "A obter preço...";
  petrolTag.textContent = "A obter preço...";

  try {
    const res = await fetch(`/api/stations/${stationId}/prices`);
    if (!res.ok) throw new Error("Falha na rota de preços");
    const priceInfo = await res.json();

    if (priceInfo.lpg_price) {
      lpgInput.value = priceInfo.lpg_price.toFixed(3);
    }
    if (priceInfo.petrol_price) {
      petrolInput.value = priceInfo.petrol_price.toFixed(3);
    }

    let sourceText = "";
    if (priceInfo.source === "dgeg") {
      sourceText = `🟢 DGEG (${priceInfo.updated_at || "Hoje"})`;
    } else if (priceInfo.source === "cache") {
      sourceText = `🟡 Cache (${priceInfo.updated_at || "Anterior"})`;
    } else if (priceInfo.source === "apiaberta") {
      sourceText = `🔵 Média Nacional`;
    } else {
      sourceText = `⚪ Manual`;
    }

    lpgTag.textContent = sourceText;
    petrolTag.textContent = sourceText;
    lpgInput.dataset.source = priceInfo.source;
  } catch (err) {
    console.error("Erro ao obter preços automáticos:", err);
    lpgTag.textContent = "⚪ Manual (Sem ligação)";
    petrolTag.textContent = "⚪ Manual (Sem ligação)";
  }
}

// 7. Live Real-Time Calculation Preview
function updateLiveCalculations() {
  const dist = parseFloat(document.getElementById("form-distance").value);
  const amount = parseFloat(document.getElementById("form-amount").value);
  const lpgPrice = parseFloat(document.getElementById("form-lpg-price").value);
  const petrolPrice = parseFloat(document.getElementById("form-petrol-price").value);
  const increasePercent = currentVehicle ? currentVehicle.lpg_consumption_increase : 20.0;

  const litersEl = document.getElementById("calc-preview-liters");
  const lpgConsEl = document.getElementById("calc-preview-consumption");
  const equivConsEl = document.getElementById("calc-preview-equiv");
  const savingsEl = document.getElementById("calc-preview-savings");

  if (!dist || !amount || !lpgPrice || !petrolPrice || dist <= 0 || amount <= 0 || lpgPrice <= 0 || petrolPrice <= 0) {
    litersEl.textContent = "0,0 L";
    lpgConsEl.textContent = "0,0 L/100km";
    equivConsEl.textContent = "0,0 L/100km";
    savingsEl.textContent = "0,00 €";
    return;
  }

  // Exact formulas matching Rule #1 & #9
  const liters = amount / lpgPrice;
  const lpgCons = (liters / dist) * 100.0;
  const equivPetrolCons = lpgCons / (1.0 + (increasePercent / 100.0));
  const estimatedPetrolCost = (dist / 100.0) * equivPetrolCons * petrolPrice;
  const savings = estimatedPetrolCost - amount;

  litersEl.textContent = `${formatNumber(liters, 2)} L`;
  lpgConsEl.textContent = `${formatNumber(lpgCons, 2)} L/100km`;
  equivConsEl.textContent = `${formatNumber(equivPetrolCons, 2)} L/100km`;
  savingsEl.textContent = `+${formatCurrency(savings)}`;
}

// 8. Open / Close Refueling Modal
function openRefuelingModal(refuelingId = null) {
  const modal = document.getElementById("modal-refueling");
  const form = document.getElementById("refueling-form");
  form.reset();

  document.getElementById("form-refueling-id").value = "";
  document.getElementById("form-station-id").value = "";
  document.getElementById("form-station-name").value = "";
  document.getElementById("lpg-price-tag").textContent = "";
  document.getElementById("petrol-price-tag").textContent = "";
  document.querySelectorAll(".station-chip").forEach(c => c.classList.remove("selected"));
  currentSelectedStation = null;

  // Auto-fill current date & time formatted for datetime-local (YYYY-MM-DDTHH:MM)
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  document.getElementById("form-date").value = now.toISOString().slice(0, 16);

  if (refuelingId) {
    document.getElementById("modal-refueling-title").textContent = "Editar Abastecimento";
    loadRefuelingIntoModal(refuelingId);
  } else {
    document.getElementById("modal-refueling-title").textContent = "Novo Abastecimento";
    // If there's a favorite or habitual station, auto-select it!
    if (allQuickStations && allQuickStations.length > 0) {
      selectQuickStation(allQuickStations[0].id);
    } else {
      showStationPicker();
    }
  }

  modal.classList.add("active");
  setTimeout(() => {
    document.getElementById("form-distance").focus();
  }, 100);
}

function closeRefuelingModal() {
  document.getElementById("modal-refueling").classList.remove("active");
}

async function loadRefuelingIntoModal(id) {
  try {
    const res = await fetch(`/api/refuelings/${id}`);
    if (!res.ok) throw new Error("Registo não encontrado");
    const item = await res.json();

    document.getElementById("form-refueling-id").value = item.id;
    document.getElementById("form-station-id").value = item.station_id || "";
    document.getElementById("form-station-name").value = item.station_name || "";
    document.getElementById("form-station-search").value = item.station_name || "";
    document.getElementById("form-date").value = item.date ? item.date.slice(0, 16) : "";
    document.getElementById("form-odometer").value = item.odometer || "";
    document.getElementById("form-lpg-price").value = item.lpg_price;
    document.getElementById("form-petrol-price").value = item.petrol_price;
    document.getElementById("form-distance").value = item.distance_km;
    document.getElementById("form-amount").value = item.amount_paid;
    document.getElementById("form-notes").value = item.notes || "";

    if (item.station_id) {
      selectQuickStation(item.station_id);
    } else {
      showStationPicker();
    }

    updateLiveCalculations();
  } catch (err) {
    console.error("Erro ao carregar abastecimento:", err);
  }
}

// 9. Save Refueling
async function saveRefueling(e) {
  e.preventDefault();
  const id = document.getElementById("form-refueling-id").value;
  const stationId = document.getElementById("form-station-id").value;
  const stationName = document.getElementById("form-station-name").value || document.getElementById("form-station-search").value;
  const date = document.getElementById("form-date").value;
  const distance = parseFloat(document.getElementById("form-distance").value);
  const amount = parseFloat(document.getElementById("form-amount").value);
  const lpgPrice = parseFloat(document.getElementById("form-lpg-price").value);
  const petrolPrice = parseFloat(document.getElementById("form-petrol-price").value);
  const odometer = document.getElementById("form-odometer").value ? parseInt(document.getElementById("form-odometer").value) : null;
  const notes = document.getElementById("form-notes").value;
  const source = document.getElementById("form-lpg-price").dataset.source || "user";

  const payload = {
    station_id: stationId ? parseInt(stationId) : null,
    station_name: stationName || "Posto Independente",
    date: date,
    distance_km: distance,
    amount_paid: amount,
    lpg_price: lpgPrice,
    petrol_price: petrolPrice,
    odometer: odometer,
    data_source: source,
    notes: notes
  };

  try {
    let res;
    if (id) {
      res = await fetch(`/api/refuelings/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } else {
      res = await fetch("/api/refuelings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    }

    if (!res.ok) {
      const errData = await res.json();
      alert("Erro ao guardar: " + (errData.detail || "Verifique os dados."));
      return;
    }

    closeRefuelingModal();
    await loadDashboard();
    await loadHistory();
    await loadQuickStations();
    await checkLastRefueling();
  } catch (err) {
    console.error("Erro ao guardar abastecimento:", err);
    alert("Erro de ligação ao servidor.");
  }
}

// 10. Refueling Row Actions
window.editRefueling = function(id) {
  openRefuelingModal(id);
};

window.duplicateRefueling = async function(id) {
  try {
    const res = await fetch(`/api/refuelings/${id}/duplicate`, { method: "POST" });
    if (!res.ok) throw new Error("Erro ao duplicar");
    await loadDashboard();
    await loadHistory();
    await checkLastRefueling();
  } catch (err) {
    console.error("Erro ao duplicar:", err);
    alert("Erro ao duplicar registo.");
  }
};

window.deleteRefueling = async function(id) {
  if (!confirm("Tem a certeza que deseja eliminar este abastecimento?")) return;
  try {
    const res = await fetch(`/api/refuelings/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Erro ao eliminar");
    await loadDashboard();
    await loadHistory();
    await checkLastRefueling();
  } catch (err) {
    console.error("Erro ao eliminar:", err);
    alert("Erro ao eliminar registo.");
  }
};

// 11. Vehicle Settings Modal
function openSettingsModal() {
  document.getElementById("modal-settings").classList.add("active");
}

function closeSettingsModal() {
  document.getElementById("modal-settings").classList.remove("active");
}

async function saveSettings(e) {
  e.preventDefault();
  const payload = {
    conversion_cost: parseFloat(document.getElementById("set-cost").value),
    conversion_date: document.getElementById("set-date").value,
    conversion_odometer: parseInt(document.getElementById("set-odometer").value) || 0,
    make: document.getElementById("set-make").value,
    model: document.getElementById("set-model").value,
    engine: document.getElementById("set-engine").value,
    petrol_consumption: parseFloat(document.getElementById("set-petrol-ref").value) || 7.0,
    lpg_consumption_increase: parseFloat(document.getElementById("set-lpg-increase").value) || 20.0
  };

  try {
    const res = await fetch("/api/vehicle", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error("Erro ao atualizar definições");
    currentVehicle = await res.json();
    closeSettingsModal();
    await loadVehicle();
    await loadDashboard();
    await loadHistory();
  } catch (err) {
    console.error("Erro ao guardar definições:", err);
    alert("Erro ao guardar definições.");
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

