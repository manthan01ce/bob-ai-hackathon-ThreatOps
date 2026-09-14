const API_BASE = "http://localhost:8000/api";

export async function fetchSummary() {
  const res = await fetch(`${API_BASE}/dashboard/summary`);
  if (!res.ok) throw new Error("Failed to fetch summary");
  return res.json();
}

export async function fetchRiskMap() {
  const res = await fetch(`${API_BASE}/dashboard/risk-map`);
  if (!res.ok) throw new Error("Failed to fetch risk map");
  return res.json();
}

export async function fetchRecentAlerts() {
  const res = await fetch(`${API_BASE}/dashboard/recent-alerts`);
  if (!res.ok) throw new Error("Failed to fetch recent alerts");
  return res.json();
}

export async function fetchTopRiskAssets() {
  const res = await fetch(`${API_BASE}/dashboard/top-risk`);
  if (!res.ok) throw new Error("Failed to fetch top risk assets");
  return res.json();
}

export async function fetchRecommendations() {
  const res = await fetch(`${API_BASE}/dashboard/recommendations`);
  if (!res.ok) throw new Error("Failed to fetch recommendations");
  return res.json();
}

export async function fetchWeatherRisk() {
  const res = await fetch(`${API_BASE}/weather/risk`);
  if (!res.ok) throw new Error("Failed to fetch weather risk");
  return res.json();
}

export async function fetchAssetHistory(assetId: string) {
  const res = await fetch(`${API_BASE}/sensors/${assetId}/history?hours=24`);
  if (!res.ok) throw new Error("Failed to fetch asset history");
  return res.json();
}

export async function fetchLivePrediction(assetId: string) {
  const res = await fetch(`${API_BASE}/predictions/live/${assetId}`);
  if (!res.ok) throw new Error("Failed to fetch live prediction");
  return res.json();
}

export async function fetchModelInfo() {
  const res = await fetch(`${API_BASE}/predictions/model-info`);
  if (!res.ok) throw new Error("Failed to fetch model info");
  return res.json();
}

export async function fetchAssets(limit: number = 100) {
  const res = await fetch(`${API_BASE}/assets/?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch assets");
  return res.json();
}

export async function fetchIncidents(limit: number = 50) {
  const res = await fetch(`${API_BASE}/incidents/?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch incidents");
  return res.json();
}

export async function fetchCrews() {
  const res = await fetch(`${API_BASE}/crews/`);
  if (!res.ok) throw new Error("Failed to fetch crews");
  return res.json();
}

export async function runCustomPrediction(payload: Record<string, any>) {
  const res = await fetch(`${API_BASE}/predictions/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to run prediction");
  return res.json();
}

export async function fetchSensorStream(limit: number = 40) {
  const res = await fetch(`${API_BASE}/sensors/stream?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch sensor stream");
  return res.json();
}

// Challenge U1 Planning & Advisor APIs
export async function fetchPlanningSummary() {
  const res = await fetch(`${API_BASE}/planning/summary`);
  if (!res.ok) throw new Error("Failed to fetch planning summary");
  return res.json();
}

export async function fetchMaintenancePlan(urgencyFilter?: string, district?: string) {
  let url = `${API_BASE}/planning/maintenance-plan?limit=60`;
  if (urgencyFilter && urgencyFilter !== "ALL") url += `&urgency_filter=${urgencyFilter}`;
  if (district) url += `&district=${encodeURIComponent(district)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch maintenance plan");
  return res.json();
}

export async function fetchCrewPrepositioning(weatherEvent?: string) {
  let url = `${API_BASE}/planning/crew-prepositioning`;
  if (weatherEvent && weatherEvent !== "normal_scada") {
    url += `?simulate_weather_event=${weatherEvent}`;
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch crew prepositioning");
  return res.json();
}

export async function persistWorkOrder(payload: Record<string, any>) {
  const res = await fetch(`${API_BASE}/planning/work-orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to persist work order");
  return res.json();
}

export async function verifyScadaInterlock(woId: string) {
  const res = await fetch(`${API_BASE}/planning/work-orders/${woId}/verify-interlock`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to verify SCADA safety interlock");
  return res.json();
}

export async function runBatchAudit() {
  const res = await fetch(`${API_BASE}/predictions/batch-audit`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to run grid batch audit");
  return res.json();
}
