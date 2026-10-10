// Daily Commute Decision Agent Frontend Controller (Agentic 2.1 with Interactive Leaflet Map & GPS Telemetry)

let currentUser = "demo_commuter";
let currentSessionId = null;
let currentOptions = [];
let selectedSeat = null;
let availableSeatsData = [];
let latestReceiptData = null;
let currentTripId = "TRIP-demo";

// Live Map Variables
let liveMap = null;
let mapTileLayer = null;
let vehicleMarker = null;
let routePolyline = null;
let stationMarkers = [];
let simulationTimer = null;
let simProgress = 35.0; // percentage

// Sample Commute Coordinates Corridor (Bengaluru Metro / Express Transit Corridor)
const WAYPOINTS = [
  { name: "North Station", lat: 12.9716, lon: 77.5946, isOrigin: true },
  { name: "Tech Park Interchange", lat: 12.9850, lon: 77.6150 },
  { name: "Metro Central Terminal", lat: 13.0020, lon: 77.6400 },
  { name: "Financial District", lat: 13.0250, lon: 77.6700, isDest: true }
];

// ----------------------------------------------------
// Smart API Base URL Resolver (Cross-Origin & Live Server Resilient)
// ----------------------------------------------------
const API_BASE_URL = (() => {
  if (typeof window === "undefined" || !window.location) return "http://127.0.0.1:8000";
  const { protocol, hostname, port } = window.location;
  if (protocol === "file:") return "http://127.0.0.1:8000";
  if (port === "8000") return "";
  const host = hostname || "127.0.0.1";
  return `${protocol}//${host}:8000`;
})();

/**
 * Robust API Request Wrapper
 * Reads body stream exactly once and safely parses JSON or text.
 * Prevents "Failed to execute 'text' on 'Response': body stream already read".
 */
async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith("http")
    ? endpoint
    : `${API_BASE_URL}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  try {
    const res = await fetch(url, options);
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }

    if (!res.ok) {
      let errMsg = "API Request failed";
      if (data && typeof data === "object" && data.detail) {
        errMsg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } else if (typeof data === "string" && data.trim()) {
        errMsg = data.length > 200 ? data.substring(0, 200) + "..." : data;
      } else {
        errMsg = `HTTP ${res.status}: ${res.statusText}`;
      }
      return { ok: false, status: res.status, data, error: errMsg };
    }

    return { ok: true, status: res.status, data, error: null };
  } catch (netErr) {
    console.warn(`[API Connection Error] Failed connecting to ${url}:`, netErr);
    return {
      ok: false,
      status: 0,
      data: null,
      error: `Cannot connect to Agent backend at ${API_BASE_URL || 'port 8000'}. Ensure the backend server is running.`
    };
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initDefaults();
  checkHealth();
  loadUserAndWallet();
  loadPreferences();
  loadRAGDocuments();
  loadBookings();
  loadRegisteredTools();
  loadSeatMap("opt_train_exp_101");
  setupEventListeners();

  // Initialize Map when tracking tab is activated
  const trackingTabEl = document.getElementById("tracking-tab");
  if (trackingTabEl) {
    trackingTabEl.addEventListener("shown.bs.tab", () => {
      initOrRefreshMap();
    });
  }
});

// ----------------------------------------------------
// Theme Management (Dark / Light)
// ----------------------------------------------------
function initTheme() {
  const savedTheme = localStorage.getItem("commute_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
  updateThemeIcon(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const newTheme = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", newTheme);
  localStorage.setItem("commute_theme", newTheme);
  updateThemeIcon(newTheme);
  updateMapTiles(newTheme);
}

function updateThemeIcon(theme) {
  const icon = document.getElementById("themeIcon");
  if (!icon) return;
  if (theme === "light") {
    icon.className = "bi bi-sun text-warning fs-6";
  } else {
    icon.className = "bi bi-moon-stars text-light fs-6";
  }
}

function initDefaults() {
  const today = new Date().toISOString().split("T")[0];
  const journeyDateEl = document.getElementById("journeyDateInput");
  if (journeyDateEl) journeyDateEl.value = today;
}

// ----------------------------------------------------
// Interactive Map (Leaflet)
// ----------------------------------------------------
function initOrRefreshMap() {
  if (typeof L === "undefined") return;

  const mapContainer = document.getElementById("liveMap");
  if (!mapContainer) return;

  if (!liveMap) {
    // Initial Map Setup centered on transit corridor
    liveMap = L.map("liveMap", {
      zoomControl: true,
      scrollWheelZoom: true
    }).setView([12.9980, 77.6300], 12);

    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    updateMapTiles(currentTheme);

    // Draw route line
    const latlngs = WAYPOINTS.map(w => [w.lat, w.lon]);
    routePolyline = L.polyline(latlngs, {
      color: '#38bdf8',
      weight: 5,
      opacity: 0.85,
      dashArray: '1, 8'
    }).addTo(liveMap);

    // Add station markers
    stationMarkers = WAYPOINTS.map((w) => {
      const isEndpoint = w.isOrigin || w.isDest;
      const marker = L.circleMarker([w.lat, w.lon], {
        radius: isEndpoint ? 8 : 6,
        fillColor: w.isOrigin ? '#10b981' : (w.isDest ? '#f59e0b' : '#3b82f6'),
        color: '#ffffff',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9
      }).addTo(liveMap);

      marker.bindPopup(`<strong>${w.name}</strong><br><span class="small text-muted">${w.isOrigin ? 'Origin Station' : (w.isDest ? 'Final Destination' : 'Corridor Stop')}</span>`);
      return marker;
    });

    // Custom Vehicle Animated Marker
    const vehicleIcon = L.divIcon({
      className: 'custom-vehicle-icon',
      html: `<div class="vehicle-marker-icon"><i class="bi bi-train-front-fill"></i></div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17]
    });

    // Position vehicle at current interpolated position
    const currentCoord = interpolateCoord(simProgress / 100.0);
    vehicleMarker = L.marker([currentCoord.lat, currentCoord.lon], { icon: vehicleIcon }).addTo(liveMap);
    vehicleMarker.bindPopup(`<strong>Express Rail Line 9 (Active)</strong><br>Speed: <span id="popupSpeed">54.2</span> km/h`);
  } else {
    setTimeout(() => {
      liveMap.invalidateSize();
    }, 150);
  }
}

function getMapSettings() {
  const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
  const defaultProvider = currentTheme === "dark" ? "cartodb_dark" : "osm_standard";
  return {
    provider: localStorage.getItem("commute_map_provider") || defaultProvider,
    apiKey: localStorage.getItem("commute_map_api_key") || ""
  };
}

function updateMapTiles(theme) {
  if (!liveMap) return;
  if (mapTileLayer) {
    liveMap.removeLayer(mapTileLayer);
  }

  const currentTheme = theme || document.documentElement.getAttribute("data-theme") || "dark";
  const { provider, apiKey } = getMapSettings();

  let tileUrl = '';
  let attribution = '';
  let maxZoom = 19;
  let subdomains = ['a', 'b', 'c'];

  if (provider === "google_roadmap") {
    const keyParam = apiKey ? `&key=${encodeURIComponent(apiKey)}` : '';
    tileUrl = `https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}${keyParam}`;
    attribution = '&copy; Google Maps';
    subdomains = ['mt0', 'mt1', 'mt2', 'mt3'];
  } else if (provider === "google_hybrid") {
    const keyParam = apiKey ? `&key=${encodeURIComponent(apiKey)}` : '';
    tileUrl = `https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}${keyParam}`;
    attribution = '&copy; Google Maps Satellite';
    subdomains = ['mt0', 'mt1', 'mt2', 'mt3'];
  } else if (provider === "google_terrain") {
    const keyParam = apiKey ? `&key=${encodeURIComponent(apiKey)}` : '';
    tileUrl = `https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}${keyParam}`;
    attribution = '&copy; Google Maps Terrain';
    subdomains = ['mt0', 'mt1', 'mt2', 'mt3'];
  } else if (provider === "cartodb_dark" || (currentTheme === "dark" && provider === "auto")) {
    tileUrl = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
    attribution = '&copy; OpenStreetMap &copy; CARTO';
    subdomains = ['a', 'b', 'c', 'd'];
  } else {
    // OpenStreetMap standard tiles
    tileUrl = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
    attribution = '&copy; OpenStreetMap contributors';
    subdomains = ['a', 'b', 'c'];
  }

  mapTileLayer = L.tileLayer(tileUrl, {
    maxZoom: maxZoom,
    subdomains: subdomains,
    attribution: attribution
  }).addTo(liveMap);
}

function interpolateCoord(fraction) {
  const f = Math.max(0, Math.min(1, fraction));
  const totalSegments = WAYPOINTS.length - 1;
  const scaled = f * totalSegments;
  const index = Math.floor(scaled);
  const remainder = scaled - index;

  if (index >= totalSegments) {
    return { lat: WAYPOINTS[totalSegments].lat, lon: WAYPOINTS[totalSegments].lon };
  }

  const p1 = WAYPOINTS[index];
  const p2 = WAYPOINTS[index + 1];

  const lat = p1.lat + (p2.lat - p1.lat) * remainder;
  const lon = p1.lon + (p2.lon - p1.lon) * remainder;
  return { lat, lon };
}

// ----------------------------------------------------
// Health Check & User Wallet
// ----------------------------------------------------
async function checkHealth() {
  const badge = document.getElementById("backendStatusBadge");
  const res = await apiRequest("/api/health");
  if (res.ok && res.data) {
    if (badge) {
      badge.className = "badge bg-success d-none d-md-inline";
      badge.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i>Agent Online (${res.data.registered_tools_count} Tools)`;
    }
  } else {
    if (badge) {
      badge.className = "badge bg-danger d-none d-md-inline cursor-pointer";
      badge.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i>Disconnected (Click to retry)`;
      badge.onclick = () => checkHealth();
    }
  }
}

async function loadUserAndWallet() {
  const res = await apiRequest(`/api/auth/user?username=${encodeURIComponent(currentUser)}`);
  if (res.ok && res.data) {
    currentUser = res.data.username;
    const navUser = document.getElementById("navUsername");
    if (navUser) navUser.innerText = res.data.display_name || res.data.username;
    const formattedBal = res.data.wallet_balance.toLocaleString("en-IN", { minimumFractionDigits: 2 });
    const navBal = document.getElementById("navWalletBalance");
    if (navBal) navBal.innerText = formattedBal;
    const modalBal = document.getElementById("modalWalletBalance");
    if (modalBal) modalBal.innerText = formattedBal;
    loadWalletTransactions();
  }
}

async function quickTopup(amount) {
  const res = await apiRequest("/api/wallet/topup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: currentUser,
      amount: amount,
      description: `Simulated Demo Wallet Top-Up (+₹${amount})`
    })
  });

  if (res.ok) {
    alert(`Top-up successful! Added ₹${amount} to simulated demo wallet.`);
    loadUserAndWallet();
  } else {
    alert("Top-up failed: " + res.error);
  }
}

async function loadWalletTransactions() {
  const res = await apiRequest(`/api/wallet/transactions?user_id=${encodeURIComponent(currentUser)}`);
  if (!res.ok) return;
  const txns = res.data;
  const tbody = document.getElementById("walletTxnTableBody");
  if (!tbody) return;
  if (!txns || txns.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No transactions recorded yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = txns.map((t) => `
    <tr>
      <td><code>${t.txn_id}</code></td>
      <td><span class="badge ${t.txn_type === 'CREDIT' ? 'bg-success' : 'bg-danger'}">${t.txn_type}</span></td>
      <td class="fw-bold ${t.txn_type === 'CREDIT' ? 'text-success' : 'text-danger'}">${t.txn_type === 'CREDIT' ? '+' : '-'}₹${t.amount.toFixed(2)}</td>
      <td>₹${t.balance_after.toFixed(2)}</td>
      <td class="small">${t.description}</td>
      <td class="small text-muted">${new Date(t.timestamp).toLocaleTimeString()}</td>
    </tr>
  `).join("");
}

// ----------------------------------------------------
// Event Listeners
// ----------------------------------------------------
function setupEventListeners() {
  // Theme Toggle
  const themeBtn = document.getElementById("themeToggleBtn");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

  // Login Form
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const u = document.getElementById("loginUsername").value;
      const p = document.getElementById("loginPassword").value;
      const res = await apiRequest("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p })
      });
      if (res.ok && res.data) {
        currentUser = res.data.username;
        loadUserAndWallet();
        const modalEl = document.getElementById("loginModal");
        if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
        alert(`Signed in as ${res.data.display_name}!`);
      } else {
        alert("Login Error: " + (res.error || "Invalid username or password"));
      }
    });
  }

  // Plan commute form submit
  const commuteForm = document.getElementById("commuteForm");
  if (commuteForm) {
    commuteForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await runCommutePlan();
    });
  }

  // Manual booking button
  const manualBookBtn = document.getElementById("manualBookBtn");
  if (manualBookBtn) {
    manualBookBtn.addEventListener("click", async () => {
      await executeManualBooking();
    });
  }

  // Refresh bookings button
  const refreshBookingsBtn = document.getElementById("refreshBookingsBtn");
  if (refreshBookingsBtn) {
    refreshBookingsBtn.addEventListener("click", () => {
      loadBookings();
    });
  }

  // Verify booking button
  const verifyBtn = document.getElementById("verifyBtn");
  if (verifyBtn) {
    verifyBtn.addEventListener("click", async () => {
      const bId = document.getElementById("verifyBookingIdInput").value.trim();
      if (bId) await verifyBooking(bId);
    });
  }

  // Disruption simulation button
  const triggerDisruptionBtn = document.getElementById("triggerDisruptionBtn");
  if (triggerDisruptionBtn) {
    triggerDisruptionBtn.addEventListener("click", async () => {
      await triggerDisruption();
    });
  }

  // RAG upload form
  const ragUploadForm = document.getElementById("ragUploadForm");
  if (ragUploadForm) {
    ragUploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await uploadRAGDocument();
    });
  }

  // RAG query button
  const ragQueryBtn = document.getElementById("ragQueryBtn");
  if (ragQueryBtn) {
    ragQueryBtn.addEventListener("click", async () => {
      await runRAGQuery();
    });
  }

  // Preferences form
  const prefsForm = document.getElementById("prefsForm");
  if (prefsForm) {
    prefsForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await savePreferences();
    });
  }

  // View Receipt Button
  const viewReceiptBtn = document.getElementById("viewReceiptBtn");
  if (viewReceiptBtn) {
    viewReceiptBtn.addEventListener("click", () => {
      if (latestReceiptData) {
        showReceiptModal(latestReceiptData);
      }
    });
  }

  // Advance Live Tracking Simulation (Step Forward)
  const advanceTrackingBtn = document.getElementById("advanceTrackingBtn");
  if (advanceTrackingBtn) {
    advanceTrackingBtn.addEventListener("click", async () => {
      advanceSimStep(15.0);
    });
  }

  // Auto Play Simulation
  const autoPlaySimBtn = document.getElementById("autoPlaySimBtn");
  if (autoPlaySimBtn) {
    autoPlaySimBtn.addEventListener("click", () => {
      startAutoPlaySim();
    });
  }

  // Pause Simulation
  const pauseSimBtn = document.getElementById("pauseSimBtn");
  if (pauseSimBtn) {
    pauseSimBtn.addEventListener("click", () => {
      pauseAutoPlaySim();
    });
  }

  // Reset Simulation
  const resetSimBtn = document.getElementById("resetSimBtn");
  if (resetSimBtn) {
    resetSimBtn.addEventListener("click", () => {
      resetSim();
    });
  }

  // Map Provider & API Key Modal Controls
  const mapProviderSelect = document.getElementById("mapProviderSelect");
  const mapApiKeyInput = document.getElementById("mapApiKeyInput");
  const saveMapConfigBtn = document.getElementById("saveMapConfigBtn");
  const resetMapConfigBtn = document.getElementById("resetMapConfigBtn");
  const toggleMapKeyVisibilityBtn = document.getElementById("toggleMapKeyVisibilityBtn");

  if (mapProviderSelect) {
    const saved = getMapSettings();
    mapProviderSelect.value = saved.provider;
    if (mapApiKeyInput) mapApiKeyInput.value = saved.apiKey;
  }

  if (saveMapConfigBtn) {
    saveMapConfigBtn.addEventListener("click", () => {
      const selectedProvider = mapProviderSelect.value;
      const key = mapApiKeyInput ? mapApiKeyInput.value.trim() : "";
      localStorage.setItem("commute_map_provider", selectedProvider);
      localStorage.setItem("commute_map_api_key", key);
      updateMapTiles();
      const modalEl = document.getElementById("mapConfigModal");
      if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
      }
      alert("Map layer & API key configuration applied!");
    });
  }

  if (resetMapConfigBtn) {
    resetMapConfigBtn.addEventListener("click", () => {
      localStorage.removeItem("commute_map_provider");
      localStorage.removeItem("commute_map_api_key");
      const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
      mapProviderSelect.value = currentTheme === "dark" ? "cartodb_dark" : "osm_standard";
      if (mapApiKeyInput) mapApiKeyInput.value = "";
      updateMapTiles();
      alert("Reset to default free high-contrast map tiles.");
    });
  }

  if (toggleMapKeyVisibilityBtn && mapApiKeyInput) {
    toggleMapKeyVisibilityBtn.addEventListener("click", () => {
      const isPassword = mapApiKeyInput.type === "password";
      mapApiKeyInput.type = isPassword ? "text" : "password";
      const icon = document.getElementById("toggleMapKeyIcon");
      if (icon) {
        icon.className = isPassword ? "bi bi-eye-slash" : "bi bi-eye";
      }
    });
  }
}

// ----------------------------------------------------
// Run Commute Plan
// ----------------------------------------------------
async function runCommutePlan() {
  const btn = document.getElementById("planBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Agent Working...`;

  const payload = {
    user_id: currentUser,
    origin: document.getElementById("originInput").value,
    destination: document.getElementById("destinationInput").value,
    journey_date: document.getElementById("journeyDateInput").value,
    desired_arrival_time: document.getElementById("targetArrivalInput").value,
    budget_limit: parseFloat(document.getElementById("budgetInput").value),
    ranking_strategy: document.getElementById("strategyInput").value,
    passenger_name: document.getElementById("passengerNameInput").value,
    passenger_count: 1,
    seat_preference: document.getElementById("seatPrefInput").value,
    payment_mode: document.getElementById("paymentModeInput").value,
    auto_book: document.getElementById("autoBookToggle").checked,
    auto_book_authorized: document.getElementById("authConsentToggle").checked
  };

  const res = await apiRequest("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    alert("Agent planning notice: " + res.error);
    btn.disabled = false;
    btn.innerHTML = `<i class="bi bi-play-circle me-2"></i>Run Autonomous Agent Plan`;
    return;
  }

  const data = res.data;
  currentSessionId = data.session_id;
  currentTripId = `TRIP-${currentSessionId}`;
  currentOptions = data.all_options || [];

  const sessionBadge = document.getElementById("activeSessionBadge");
  if (sessionBadge) sessionBadge.innerText = `Session: ${currentSessionId}`;

  renderCommuteResults(data);
  renderTraces(data.steps_executed || []);
  loadBookings();
  loadUserAndWallet();

  btn.disabled = false;
  btn.innerHTML = `<i class="bi bi-play-circle me-2"></i>Run Autonomous Agent Plan`;
}

// ----------------------------------------------------
// Render Commute Results
// ----------------------------------------------------
function renderCommuteResults(data) {
  const container = document.getElementById("optionsContainer");
  const explanationBox = document.getElementById("explanationBox");
  const explanationText = document.getElementById("explanationText");
  const bookingAlert = document.getElementById("bookingResultAlert");
  const bookingDetails = document.getElementById("bookingResultDetails");
  const disruptionBanner = document.getElementById("disruptionBanner");

  if (explanationBox) explanationBox.classList.remove("d-none");
  if (explanationText) explanationText.innerHTML = data.decision_explanation || "Evaluation complete.";

  if (disruptionBanner) {
    if (data.disruption_detected) {
      disruptionBanner.classList.remove("d-none");
      const dt = document.getElementById("disruptionText");
      if (dt) dt.innerText = "Route plan dynamically adjusted following real-time disruption broadcast.";
    } else {
      disruptionBanner.classList.add("d-none");
    }
  }

  if (bookingAlert && bookingDetails) {
    if (data.booking_result && data.booking_result.status === "CONFIRMED") {
      latestReceiptData = data.booking_result.receipt || {
        receipt_id: `RCPT-${data.booking_result.booking_id}`,
        booking_id: data.booking_result.booking_id,
        passenger_name: data.booking_result.passenger_name,
        origin: data.booking_result.origin,
        destination: data.booking_result.destination,
        departure_time: data.booking_result.departure_time,
        arrival_time: data.booking_result.arrival_time,
        seat_number: data.booking_result.seat_number,
        seat_type: data.booking_result.seat_type,
        total_paid: data.booking_result.total_amount,
        currency: "INR",
        payment_mode: data.booking_result.payment_mode,
        payment_status: data.booking_result.payment_status,
        timestamp: data.booking_result.created_at
      };

      bookingAlert.classList.remove("d-none");
      bookingDetails.innerHTML = `
        Booking ID: <code>${data.booking_result.booking_id}</code> |
        Seat: <strong>${data.booking_result.seat_number} (${data.booking_result.seat_type})</strong> |
        Total: <strong>₹${data.booking_result.total_amount.toFixed(2)}</strong> |
        Payment: <span class="badge ${data.booking_result.payment_status === 'PAID' ? 'bg-success' : 'bg-warning'}">${data.booking_result.payment_mode} (${data.booking_result.payment_status})</span>
      `;
    } else {
      bookingAlert.classList.add("d-none");
    }
  }

  if (!container) return;

  if (!data.all_options || data.all_options.length === 0) {
    container.innerHTML = `<div class="col-12 text-center py-4 text-danger">No commute options found.</div>`;
    return;
  }

  container.innerHTML = data.all_options.map((opt) => {
    const isRec = data.recommended_option && data.recommended_option.id === opt.id;
    const modeIcons = {
      express_train: "bi-train-front text-info",
      metro: "bi-subway text-primary",
      bus: "bi-bus-front text-warning",
      rideshare: "bi-car-front text-success"
    };
    const icon = modeIcons[opt.mode] || "bi-signpost text-light";

    return `
      <div class="col-md-6">
        <div class="card commute-card ${isRec ? 'recommended' : ''} ${!opt.is_eligible ? 'ineligible' : ''} p-3">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div class="d-flex align-items-center gap-2">
              <i class="bi ${icon} fs-4"></i>
              <div>
                <h6 class="mb-0 fw-bold">${opt.title}</h6>
                <span class="small text-muted">${opt.origin} → ${opt.destination}</span>
              </div>
            </div>
            ${isRec ? '<span class="badge bg-success"><i class="bi bi-star-fill me-1"></i>Top Choice</span>' : ''}
            ${!opt.is_eligible ? '<span class="badge bg-danger">Rejected</span>' : ''}
          </div>

          <div class="row g-2 text-center my-2 py-2 bg-dark rounded border border-secondary">
            <div class="col-4">
              <div class="small text-muted">Departure</div>
              <div class="fw-bold">${opt.departure_time}</div>
            </div>
            <div class="col-4">
              <div class="small text-muted">Arrival</div>
              <div class="fw-bold text-success">${opt.arrival_time}</div>
            </div>
            <div class="col-4">
              <div class="small text-muted">Duration</div>
              <div class="fw-bold">${opt.duration_minutes} min</div>
            </div>
          </div>

          <div class="d-flex justify-content-between align-items-center mt-2">
            <div>
              <span class="fs-5 fw-bold text-primary">₹${opt.total_fare.toFixed(2)}</span>
              <span class="small text-muted ms-1">(Reliability: ${(opt.reliability_score * 100).toFixed(0)}%)</span>
            </div>
            ${opt.requires_booking ? `
              <button class="btn btn-sm btn-outline-info" onclick="switchToSeatBooking('${opt.id}')">
                <i class="bi bi-ticket-perforated me-1"></i>Select Seat
              </button>
            ` : '<span class="badge bg-secondary">Direct Boarding</span>'}
          </div>

          ${opt.rejection_reasons && opt.rejection_reasons.length > 0 ? `
            <div class="small text-danger mt-2 border-top border-secondary pt-1">
              <i class="bi bi-x-circle me-1"></i>${opt.rejection_reasons.join(', ')}
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join("");
}

// ----------------------------------------------------
// Render Workflow Traces
// ----------------------------------------------------
function renderTraces(steps) {
  const container = document.getElementById("traceTimelineContainer");
  const countBadge = document.getElementById("traceCountBadge");
  if (countBadge) countBadge.innerText = `${steps.length} Stages Executed`;

  if (!container) return;

  if (!steps || steps.length === 0) {
    container.innerHTML = `<div class="text-muted py-4">No traces available.</div>`;
    return;
  }

  container.innerHTML = steps.map((step) => {
    const toolCallsHtml = (step.tool_calls || []).map((t) => `
      <div class="p-2 my-1 rounded bg-dark border border-secondary font-monospace small">
        <div class="d-flex justify-content-between text-info">
          <span><i class="bi bi-gear-wide-connected me-1"></i><strong>${t.tool_name}</strong></span>
          <span class="text-muted">${t.execution_time_ms} ms</span>
        </div>
        <div class="text-muted small text-truncate">Input: ${JSON.stringify(t.input_params)}</div>
      </div>
    `).join("");

    return `
      <div class="trace-item">
        <div class="d-flex align-items-center gap-2 mb-1">
          <span class="stage-badge stage-${step.stage}">${step.stage}</span>
          <span class="small text-muted">Step ${step.step_number}</span>
          <span class="small text-muted ms-auto">${new Date(step.timestamp).toLocaleTimeString()}</span>
        </div>
        <div class="small text-light mb-2">${step.description}</div>
        ${toolCallsHtml ? `<div class="ms-2 mb-2">${toolCallsHtml}</div>` : ''}
      </div>
    `;
  }).join("");
}

// ----------------------------------------------------
// Seat Map & Manual Booking
// ----------------------------------------------------
async function loadSeatMap(optionId) {
  const res = await apiRequest("/api/booking/availability", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ option_id: optionId })
  });
  if (!res.ok || !res.data) return;
  availableSeatsData = res.data.seats || [];
  renderSeatGrid(availableSeatsData);
}

function renderSeatGrid(seats) {
  const grid = document.getElementById("seatGrid");
  if (!grid) return;
  grid.innerHTML = seats.map((s) => {
    let classes = "seat-btn";
    if (!s.is_available) classes += " booked";
    if (s.seat_type === "quiet") classes += " quiet";
    if (s.seat_type === "front") classes += " front";
    if (selectedSeat && selectedSeat.seat_number === s.seat_number) classes += " selected";

    return `
      <div class="${classes}" onclick="pickSeat('${s.seat_number}')">
        <div>${s.seat_number}</div>
        <div style="font-size:0.7rem;" class="text-muted">${s.seat_type}</div>
      </div>
    `;
  }).join("");
}

window.pickSeat = function(seatNum) {
  const seat = availableSeatsData.find(s => s.seat_number === seatNum);
  if (!seat || !seat.is_available) return;
  selectedSeat = seat;
  const sBadge = document.getElementById("selectedSeatBadge");
  if (sBadge) sBadge.innerText = `${seat.seat_number} (${seat.seat_type})`;
  const baseFare = 180.0;
  const total = baseFare + (seat.extra_fee || 0);
  const fareTxt = document.getElementById("bookingFareText");
  if (fareTxt) fareTxt.innerText = `₹${total.toFixed(2)}`;
  renderSeatGrid(availableSeatsData);
};

window.switchToSeatBooking = function(optionId) {
  const tabBtn = document.getElementById("booking-tab");
  if (tabBtn) {
    const tab = new bootstrap.Tab(tabBtn);
    tab.show();
  }
  loadSeatMap(optionId);
};

window.switchToLiveTracking = function() {
  const tabBtn = document.getElementById("tracking-tab");
  if (tabBtn) {
    const tab = new bootstrap.Tab(tabBtn);
    tab.show();
  }
  initOrRefreshMap();
};

async function executeManualBooking() {
  const btn = document.getElementById("manualBookBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Confirming with Provider...`;

  const paymentMode = document.getElementById("manualBookingPaymentMode").value;

  const payload = {
    option_id: "opt_train_exp_101",
    journey_date: document.getElementById("journeyDateInput").value || new Date().toISOString().split("T")[0],
    user_id: currentUser,
    passenger_name: document.getElementById("passengerNameInput").value || "Demo Commuter",
    passenger_count: 1,
    seat_number: selectedSeat ? selectedSeat.seat_number : null,
    seat_preference: document.getElementById("seatPrefInput").value,
    max_budget: parseFloat(document.getElementById("budgetInput").value) || 2000.0,
    payment_mode: paymentMode,
    is_auto_booked: false,
    user_authorized: true,
    idempotency_key: `manual_bkg_${Date.now()}`
  };

  const res = await apiRequest("/api/booking/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (res.ok && res.data) {
    const data = res.data;
    if (data.status === "CONFIRMED") {
      loadBookings();
      loadUserAndWallet();
      loadSeatMap("opt_train_exp_101");
      if (data.receipt) {
        showReceiptModal(data.receipt);
      } else {
        alert(`Booking Confirmed!\nBooking ID: ${data.booking_id}\nSeat: ${data.seat_number}\nPayment: ${data.payment_mode} (${data.payment_status})`);
      }
    } else {
      alert(`Booking Failed: ${data.failure_reason}`);
    }
  } else {
    alert("Error executing booking: " + res.error);
  }

  btn.disabled = false;
  btn.innerHTML = `<i class="bi bi-lock me-1"></i>Execute Confirmed Seat Reservation`;
}

async function loadBookings() {
  const res = await apiRequest("/api/booking/history");
  if (!res.ok || !res.data) return;
  const data = res.data;
  const tbody = document.getElementById("bookingsTableBody");
  if (!tbody) return;
  if (!data.bookings || data.bookings.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No bookings recorded yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.bookings.map((b) => `
    <tr>
      <td><code>${b.booking_id}</code></td>
      <td>${b.passenger_name}</td>
      <td><span class="badge bg-secondary">${b.seat_number}</span></td>
      <td>₹${b.total_amount.toFixed(2)}</td>
      <td><span class="badge ${b.payment_status === 'PAID' ? 'bg-success' : 'bg-warning'}">${b.payment_mode || 'WALLET'} (${b.payment_status || 'PAID'})</span></td>
      <td><span class="badge ${b.status === 'CONFIRMED' ? 'bg-success' : 'bg-danger'}">${b.status}</span></td>
    </tr>
  `).join("");
}

async function verifyBooking(bId) {
  const resultBox = document.getElementById("verifyResultBox");
  if (!resultBox) return;
  resultBox.innerHTML = `<span class="text-muted">Querying provider...</span>`;
  const res = await apiRequest(`/api/booking/status/${encodeURIComponent(bId)}`);
  if (res.ok && res.data) {
    const data = res.data;
    if (data.verified) {
      resultBox.innerHTML = `<div class="alert alert-success py-2 mb-0"><i class="bi bi-patch-check-fill me-1"></i><strong>VERIFIED:</strong> Seat ${data.seat_number} confirmed for ${data.passenger_name} | Payment: ${data.payment_mode} (${data.payment_status}) (Code: ${data.verification_code})</div>`;
    } else {
      resultBox.innerHTML = `<div class="alert alert-danger py-2 mb-0"><i class="bi bi-x-circle-fill me-1"></i>Verification failed: ${data.message || data.status}</div>`;
    }
  } else {
    resultBox.innerHTML = `<span class="text-danger">Verification error: ${res.error}</span>`;
  }
}

// ----------------------------------------------------
// Receipt Modal Helper
// ----------------------------------------------------
function showReceiptModal(receipt) {
  const container = document.getElementById("receiptCardContent");
  if (!container) return;
  container.innerHTML = `
    <div class="receipt-watermark">SIMULATED DEMO</div>
    <div class="text-center mb-3">
      <i class="bi bi-ticket-detailed fs-1 text-success"></i>
      <h5 class="fw-bold mb-0">Autonomous Transit Receipt</h5>
      <span class="badge bg-dark border border-secondary text-muted">Receipt ID: ${receipt.receipt_id || 'RCPT-DEMO'}</span>
    </div>

    <div class="row g-2 small border-top border-bottom border-secondary py-2 mb-3">
      <div class="col-6"><span class="text-muted">Booking ID:</span> <code>${receipt.booking_id}</code></div>
      <div class="col-6"><span class="text-muted">Passenger:</span> <strong>${receipt.passenger_name}</strong></div>
      <div class="col-6"><span class="text-muted">Route:</span> ${receipt.origin} → ${receipt.destination}</div>
      <div class="col-6"><span class="text-muted">Seat:</span> <strong>${receipt.seat_number} (${receipt.seat_type})</strong></div>
      <div class="col-6"><span class="text-muted">Departure:</span> ${receipt.departure_time}</div>
      <div class="col-6"><span class="text-muted">Arrival:</span> ${receipt.arrival_time}</div>
    </div>

    <div class="d-flex justify-content-between mb-1 small">
      <span class="text-muted">Base Fare:</span>
      <span>₹${(receipt.base_fare || receipt.total_paid).toFixed(2)}</span>
    </div>
    <div class="d-flex justify-content-between mb-2 small">
      <span class="text-muted">Seat Reservation Fee:</span>
      <span>₹${(receipt.seat_fee || 0).toFixed(2)}</span>
    </div>
    <div class="d-flex justify-content-between border-top border-secondary pt-2 mb-3 fw-bold fs-6">
      <span>Total Paid / Due:</span>
      <span class="text-success">₹${receipt.total_paid.toFixed(2)}</span>
    </div>

    <div class="p-2 rounded bg-dark border border-secondary small text-center mb-2">
      Payment Mode: <strong>${receipt.payment_mode}</strong> | Status: <span class="badge ${receipt.payment_status === 'PAID' ? 'bg-success' : 'bg-warning'}">${receipt.payment_status}</span>
      ${receipt.txn_id ? `<div class="text-muted" style="font-size:0.75rem;">Transaction Ref: <code>${receipt.txn_id}</code></div>` : ''}
    </div>

    <div class="text-center text-muted" style="font-size: 0.7rem;">
      <i class="bi bi-shield-exclamation me-1"></i>${receipt.disclaimer || 'SIMULATED RECEIPT - NOT A REAL MONETARY CHARGE'}
    </div>
  `;

  const modalEl = document.getElementById("receiptModal");
  if (modalEl) {
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }
}

// ----------------------------------------------------
// Live Map Telemetry & Simulation Loop
// ----------------------------------------------------
function advanceSimStep(delta = 15.0) {
  simProgress += delta;
  if (simProgress > 100.0) {
    simProgress = 100.0;
    pauseAutoPlaySim();
  }
  updateSimView();
}

function startAutoPlaySim() {
  if (simulationTimer) clearInterval(simulationTimer);
  const btn = document.getElementById("autoPlaySimBtn");
  if (btn) {
    btn.className = "btn btn-sm btn-success";
    btn.innerHTML = `<i class="bi bi-arrow-repeat spin me-1"></i>Auto-Pilot Active`;
  }

  simulationTimer = setInterval(() => {
    simProgress += 4.0;
    if (simProgress >= 100.0) {
      simProgress = 100.0;
      pauseAutoPlaySim();
    }
    updateSimView();
  }, 1200);
}

function pauseAutoPlaySim() {
  if (simulationTimer) {
    clearInterval(simulationTimer);
    simulationTimer = null;
  }
  const btn = document.getElementById("autoPlaySimBtn");
  if (btn) {
    btn.className = "btn btn-sm btn-primary";
    btn.innerHTML = `<i class="bi bi-play-fill me-1"></i>Start Auto-Pilot Simulation`;
  }
}

function resetSim() {
  pauseAutoPlaySim();
  simProgress = 0.0;
  updateSimView();
}

function updateSimView() {
  const coord = interpolateCoord(simProgress / 100.0);
  
  if (vehicleMarker && liveMap) {
    vehicleMarker.setLatLng([coord.lat, coord.lon]);
    // Smooth pan
    liveMap.panTo([coord.lat, coord.lon], { animate: true, duration: 0.8 });
  }

  // Update UI Elements
  const progTxt = document.getElementById("trackingProgressText");
  if (progTxt) progTxt.innerText = `${simProgress.toFixed(0)}%`;
  const progFill = document.getElementById("trackingProgressFill");
  if (progFill) progFill.style.width = `${simProgress.toFixed(0)}%`;
  const coordsTxt = document.getElementById("trackingCoords");
  if (coordsTxt) coordsTxt.innerText = `${coord.lat.toFixed(4)}° N, ${coord.lon.toFixed(4)}° E`;

  let currentStop = "North Station";
  let nextStop = "Tech Park Interchange";
  let speed = 54.0 + (Math.sin(simProgress) * 6.0);
  let eta = Math.max(0, Math.round((100.0 - simProgress) * 0.35));

  if (simProgress < 30) {
    currentStop = "North Station (Departed)";
    nextStop = "Tech Park Interchange";
  } else if (simProgress < 70) {
    currentStop = "Transit Corridor Sector 4";
    nextStop = "Metro Central Terminal";
  } else if (simProgress < 100) {
    currentStop = "Metro Central Terminal";
    nextStop = "Financial District";
  } else {
    currentStop = "Financial District (Arrived)";
    nextStop = "Journey Complete";
    speed = 0.0;
    eta = 0;
  }

  const curStopEl = document.getElementById("trackingCurrentStop");
  if (curStopEl) curStopEl.innerText = currentStop;
  const nextStopEl = document.getElementById("trackingNextStop");
  if (nextStopEl) nextStopEl.innerText = nextStop;
  const speedEl = document.getElementById("hudSpeed");
  if (speedEl) speedEl.innerText = speed.toFixed(1);
  const etaEl = document.getElementById("hudEta");
  if (etaEl) etaEl.innerText = eta;
}

// ----------------------------------------------------
// Disruption & Re-planning
// ----------------------------------------------------
async function triggerDisruption() {
  if (!currentSessionId) {
    alert("Please run an initial Commute Plan first so the agent has an active session to re-plan.");
    return;
  }

  const btn = document.getElementById("triggerDisruptionBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Re-planning Workflow...`;

  const payload = {
    session_id: currentSessionId,
    disruption: {
      disruption_type: document.getElementById("disruptionTypeSelect").value,
      severity: "severe",
      affected_mode: document.getElementById("affectedModeSelect").value,
      delay_minutes: parseInt(document.getElementById("delayMinutesInput").value, 10),
      location: "Active Corridor",
      description: document.getElementById("disruptionDescInput").value
    },
    allow_auto_rebook: document.getElementById("replanAutoRebook").checked,
    payment_mode: document.getElementById("paymentModeInput").value
  };

  const res = await apiRequest("/api/replan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    alert("Re-planning error: " + res.error);
    btn.disabled = false;
    btn.innerHTML = `<i class="bi bi-radioactive me-2"></i>Broadcast Disruption & Trigger REPLAN Loop`;
    return;
  }

  const data = res.data;
  const replanBox = document.getElementById("replanResultsBox");
  if (replanBox) {
    replanBox.innerHTML = `
      <div class="alert alert-warning mb-3">
        <h6 class="alert-heading fw-bold"><i class="bi bi-arrow-repeat me-1"></i>Autonomous Re-plan Decision</h6>
        <p class="mb-0">${data.decision_explanation}</p>
      </div>
      <div class="p-3 bg-dark rounded border border-secondary">
        <h6 class="text-muted small text-uppercase fw-bold">New Recommended Route</h6>
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <h5 class="mb-0 text-success">${data.recommended_option ? data.recommended_option.title : 'None'}</h5>
            <span class="small text-muted">Arrival: ${data.recommended_option ? data.recommended_option.arrival_time : 'N/A'} | Fare: ₹${data.recommended_option ? data.recommended_option.total_fare.toFixed(2) : '0.00'}</span>
          </div>
          <span class="badge bg-success">Optimal Backup</span>
        </div>
      </div>
    `;
  }

  renderCommuteResults(data);
  renderTraces(data.steps_executed || []);
  loadUserAndWallet();

  btn.disabled = false;
  btn.innerHTML = `<i class="bi bi-radioactive me-2"></i>Broadcast Disruption & Trigger REPLAN Loop`;
}

// ----------------------------------------------------
// RAG Knowledge Base
// ----------------------------------------------------
async function loadRAGDocuments() {
  const res = await apiRequest("/api/rag/documents");
  if (!res.ok || !res.data) return;
  const docs = res.data;
  const list = document.getElementById("ragDocList");
  if (!list) return;
  if (!docs || docs.length === 0) {
    list.innerHTML = `<li class="list-group-item bg-transparent text-muted">No documents indexed yet.</li>`;
    return;
  }
  list.innerHTML = docs.map((d) => `
    <li class="list-group-item bg-transparent text-light border-secondary d-flex justify-content-between align-items-center">
      <div>
        <i class="bi bi-file-earmark-text text-primary me-2"></i>
        <strong>${d.filename}</strong>
        <span class="badge bg-dark border border-secondary ms-2">${d.source_type.toUpperCase()}</span>
      </div>
      <span class="badge bg-secondary">${d.chunk_count} Chunks</span>
    </li>
  `).join("");
}

async function uploadRAGDocument() {
  const fileInput = document.getElementById("ragFileInput");
  if (!fileInput.files || fileInput.files.length === 0) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const res = await apiRequest("/api/rag/upload", {
    method: "POST",
    body: formData
  });

  if (res.ok && res.data) {
    alert(res.data.message || "Document uploaded and indexed successfully!");
    fileInput.value = "";
    loadRAGDocuments();
    checkHealth();
  } else {
    alert("Upload failed: " + res.error);
  }
}

async function runRAGQuery() {
  const queryInput = document.getElementById("ragQueryInput");
  const query = queryInput ? queryInput.value.trim() : "";
  if (!query) return;

  const container = document.getElementById("ragQueryResultContainer");
  if (container) {
    container.innerHTML = `<span class="text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Searching vector index...</span>`;
  }

  const res = await apiRequest("/api/rag/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: query, top_k: 3 })
  });

  if (!res.ok || !res.data) {
    if (container) {
      container.innerHTML = `<span class="text-danger">RAG Query failed: ${res.error}</span>`;
    }
    return;
  }

  const data = res.data;
  const sourcesHtml = (data.sources || []).map((s) => `
    <div class="rag-source-box">
      <div class="d-flex justify-content-between text-info small mb-1">
        <span><i class="bi bi-link-45deg"></i> Source: <strong>${s.source}</strong></span>
        <span>Score: ${s.score}</span>
      </div>
      <div class="text-light small">${s.excerpt}</div>
    </div>
  `).join("");

  if (container) {
    container.innerHTML = `
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h6 class="mb-0 fw-bold text-success"><i class="bi bi-shield-check me-1"></i>Grounded Knowledge Response</h6>
        <span class="badge bg-primary">Confidence: ${(data.confidence_score * 100).toFixed(0)}%</span>
      </div>
      <div class="small text-light mb-3" style="white-space: pre-line;">${data.answer}</div>
      <h6 class="text-muted small text-uppercase fw-bold mb-1">Retrieved Citations</h6>
      ${sourcesHtml || '<span class="text-muted small">No direct excerpts.</span>'}
    `;
  }
}

// ----------------------------------------------------
// Preferences & Memory
// ----------------------------------------------------
async function loadPreferences() {
  const res = await apiRequest(`/api/preferences?user_id=${encodeURIComponent(currentUser)}`);
  if (!res.ok || !res.data) return;
  const prefs = res.data;
  const pBudget = document.getElementById("prefMaxBudget");
  if (pBudget) pBudget.value = prefs.max_budget || 2000.0;
  const pArr = document.getElementById("prefArrivalTime");
  if (pArr) pArr.value = prefs.latest_arrival_time || "09:00";
  const pSeat = document.getElementById("prefSeat");
  if (pSeat) pSeat.value = prefs.seat_preference || "window";
  const pStrat = document.getElementById("prefStrategy");
  if (pStrat) pStrat.value = prefs.ranking_strategy || "balanced";
}

async function savePreferences() {
  const payload = {
    user_id: currentUser,
    max_budget: parseFloat(document.getElementById("prefMaxBudget").value),
    latest_arrival_time: document.getElementById("prefArrivalTime").value,
    seat_preference: document.getElementById("prefSeat").value,
    ranking_strategy: document.getElementById("prefStrategy").value,
    payment_mode_preference: document.getElementById("paymentModeInput").value,
    auto_book_enabled: document.getElementById("autoBookToggle").checked,
    auto_book_authorized: document.getElementById("authConsentToggle").checked
  };

  const res = await apiRequest("/api/preferences", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    alert("Preferences saved successfully to SQLite memory.");
  } else {
    alert("Failed to save preferences: " + res.error);
  }
}

async function loadRegisteredTools() {
  const res = await apiRequest("/api/tools");
  if (!res.ok || !res.data) return;
  const tbody = document.getElementById("toolsCatalogBody");
  if (!tbody) return;
  tbody.innerHTML = (res.data.tools || []).map((t) => `
    <tr>
      <td><code>${t.name}</code></td>
      <td class="small text-muted">${t.description}</td>
    </tr>
  `).join("");
}
