import axios from "axios";
import { createDemoTodaySchedule, demoCatalog, demoPrescription, demoPackageExtraction, demoVerificationResult } from "../mocks/demoData";
import { createPackagingDemo } from '../mocks/packagingDemo';

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: 30000,
  withCredentials: true,
});

if (api.interceptors?.response) {
  api.interceptors.response.use(
    (response) => response,
    (error) => {
      const detail = error.response?.data?.detail;
      if (typeof detail === "string") error.message = detail;
      return Promise.reject(error);
    },
  );
}

export async function registerAccount(payload) {
  const response = await api.post("/auth/register", payload);
  return response.data;
}

export async function loginAccount(payload) {
  const response = await api.post("/auth/login", payload);
  return response.data;
}

export async function logoutAccount() {
  await api.post("/auth/logout");
}

export async function getCurrentUser() {
  const response = await api.get("/auth/me");
  return response.data;
}

export async function getDashboard() {
  const response = await api.get("/dashboard", { params: { _t: Date.now() } });
  return response.data;
}

function mockResponse(data) {
  return new Promise((resolve) => {
    setTimeout(() => resolve(structuredClone(data)), 600);
  });
}

export async function extractPrescription(file) {
  if (USE_MOCKS) return mockResponse(demoPrescription);

  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post("/prescriptions/extract", formData, {
    timeout: 60000,
  });
  return response.data;
}

export async function savePrescription(payload) {
  if (USE_MOCKS) return mockResponse({
    prescription_id: 1,
    status: "confirmed",
    medicine_count: payload.medicines.length,
    scheduling: {
      items: payload.medicines.map((medicine, index) => ({
        prescription_item_id: 201 + index,
        medicine_name: medicine.name,
        status: index === 0 ? "scheduled" : "needs_times",
        times: index === 0 ? ["09:00", "21:00"] : [],
        doses_created: index === 0 ? 10 : 0,
        reason: index === 0 ? null : "Set reminder times for this frequency.",
      })),
      error: null,
    },
  });
  const response = await api.post("/prescriptions", payload);
  return response.data;
}

function demoSchedule(prescriptionId = 1) {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Karachi", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
  const doses = createDemoTodaySchedule();
  return {
    prescription_id: Number(prescriptionId),
    timezone: "Asia/Karachi",
    prescriptions: [{ prescription_id: Number(prescriptionId), created_at: new Date().toISOString() }],
    items: [
      {
        prescription_item_id: 201, medicine_name: demoPrescription.medicines[0].name,
        dose: demoPrescription.medicines[0].dose, frequency: demoPrescription.medicines[0].frequency,
        duration_days: 5, status: "scheduled", reason: null,
        times: ["09:00", "21:00"], suggested_times: ["09:00", "21:00"],
        course_start: today, course_end: today,
        days: [{ date: today, doses: doses.filter((dose) => dose.prescription_item_id === 201) }],
        is_demo: true,
      },
      {
        prescription_item_id: 202, medicine_name: demoPrescription.medicines[1].name,
        dose: demoPrescription.medicines[1].dose, frequency: null,
        duration_days: 3, status: "needs_times",
        reason: "Set reminder times for this frequency.", times: [], suggested_times: [],
        course_start: today, course_end: today, days: [], is_demo: true,
      },
    ],
    is_demo: true,
  };
}

export async function getPrescriptionSchedule(prescriptionId, timezone = "Asia/Karachi") {
  if (USE_MOCKS) return mockResponse(demoSchedule(prescriptionId || 1));
  const response = await api.get("/schedules", {
    params: { ...(prescriptionId ? { prescription_id: prescriptionId } : {}), timezone },
  });
  return response.data;
}

export async function regenerateScheduleItem(itemId, reminderTimes, timezone = "Asia/Karachi") {
  if (USE_MOCKS) return mockResponse({ schedule_id: itemId, doses_created: reminderTimes.length * 5, status: "scheduled", is_demo: true });
  const response = await api.post(`/schedules/items/${itemId}/regenerate`, {
    reminder_times: reminderTimes,
    timezone,
  });
  return response.data;
}

export async function updateScheduleDose(doseId, status) {
  if (USE_MOCKS) return mockResponse({
    ...createDemoTodaySchedule().find((dose) => dose.id === doseId),
    status,
    taken_at: status === "taken" ? new Date().toISOString() : null,
    is_demo: true,
  });
  const response = await api.patch(`/schedules/${doseId}`, { status });
  return response.data;
}

export async function getTodaySchedule() {
  if (USE_MOCKS) return mockResponse(createDemoTodaySchedule());

  const response = await api.get("/schedules/today");
  return response.data;
}

export async function searchMedicine(query) {
  if (USE_MOCKS) {
    const term = (query ?? "").trim().toLowerCase();
    return mockResponse(demoCatalog.filter((medicine) =>
      [medicine.brand_name, medicine.active_ingredient].some((value) => value.toLowerCase().includes(term)),
    ));
  }

  const response = await api.get("/medicines/search", { params: { q: query } });
  return response.data;
}

export async function extractPackage(file) {
  if (USE_MOCKS) return mockResponse(demoPackageExtraction);

  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post("/verifications/extract", formData, {
    timeout: 60000,
  });
  return response.data;
}

export async function verifyPackage(payload) {
  if (USE_MOCKS) return mockResponse(demoVerificationResult);

  const response = await api.post("/verifications", payload);
  return response.data;
}

const demoChecks = new Map();
let demoCheckId = 1;

function abortableDemo(value, signal) {
  return new Promise((resolve, reject) => {
    const cancel = () => { clearTimeout(timer); reject(new DOMException('Analysis canceled', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', cancel); resolve(structuredClone(value)); }, 600);
    if (signal?.aborted) cancel();
    else signal?.addEventListener('abort', cancel, { once: true });
  });
}

export async function analyzePackage(files, { signal, fields = {}, trustedReference = null } = {}) {
  if (!Array.isArray(files) || files.length < 1 || files.length > 3) throw new Error('Choose one to three packaging photos.');
  const uploads = [...files, ...(trustedReference ? [trustedReference] : [])];
  if (uploads.some((file) => !['image/png', 'image/jpeg'].includes(file.type) || file.size > 5 * 1024 * 1024)) throw new Error('Each image must be PNG or JPEG and no larger than 5 MB.');
  // Leave room for multipart headers and text fields inside the 12 MB request.
  if (uploads.reduce((sum, file) => sum + file.size, 0) > 12 * 1024 * 1024 - 16 * 1024) throw new Error('Combined photos exceed the 12 MB request limit.');
  if (USE_MOCKS) {
    const scenario = import.meta.env.VITE_PACKAGING_DEMO_SCENARIO || 'consistent';
    const result = createPackagingDemo(scenario, fields, demoCheckId++);
    const response = await abortableDemo(result, signal);
    demoChecks.set(response.verification_id, response);
    return response;
  }
  const form = new FormData();
  files.forEach((file) => form.append('images', file));
  if (trustedReference) form.append('trusted_reference', trustedReference);
  ['brand_name', 'manufacturer', 'registration_number'].forEach((key) => {
    if (Object.hasOwn(fields, key)) form.append(key, fields[key] ?? '');
  });
  return (await api.post('/verifications/analyze', form, { signal, timeout: 125000 })).data;
}

export async function reanalyzeVerification(id, fields, { signal } = {}) {
  if (USE_MOCKS) {
    const previous = demoChecks.get(Number(id));
    if (!previous) throw new Error('Demo check not found. Start another analysis.');
    const result = { ...previous, verification_id: demoCheckId++, extracted: { ...previous.extracted, ...fields }, reanalysis_of: Number(id), assessed_at: new Date().toISOString() };
    result.signals = [...previous.signals, ...Object.entries(fields).map(([key, value]) => ({ category: key === 'registration_number' ? 'registration' : key === 'manufacturer' ? 'manufacturer' : key === 'brand_name' ? 'name_brand' : 'ingredient_strength', severity: 'neutral', title: `User-corrected ${key.replaceAll('_', ' ')}`, detail: `Demo correction: ${value || 'not visible'}. The configured scenario remains simulated.`, origin: 'user_correction', simulated: false, evidence: null, image_index: null, reference_url: null, registration_state: null }))];
    const response = await abortableDemo(result, signal);
    demoChecks.set(response.verification_id, response);
    return response;
  }
  return (await api.post(`/verifications/${id}/reanalyze`, fields, { signal })).data;
}

export async function getVerification(id, { signal } = {}) {
  if (USE_MOCKS) {
    const result = demoChecks.get(Number(id));
    if (!result) throw new Error('Check not found in this demo session.');
    return abortableDemo(result, signal);
  }
  return (await api.get(`/verifications/${id}`, { signal })).data;
}

export async function listVerifications({ signal } = {}) {
  if (USE_MOCKS) return abortableDemo([...demoChecks.values()].reverse().slice(0, 10).map((result) => ({ verification_id: result.verification_id, brand_name: result.extracted.brand_name, status: result.status, status_label: result.status_label, risk_level: result.risk_level, risk_score: result.risk_score, simulated: true, assessed_at: result.assessed_at })), signal);
  return (await api.get('/verifications', { signal })).data;
}

export async function createReportDraft(payload, { signal } = {}) {
  // Reports always use persistence/PDF generation on the backend. Client-only
  // demonstration checks cannot be submitted as real verification records.
  if (USE_MOCKS) throw new Error('To save a report draft, use backend demo mode (USE_MOCK_AI=true) with frontend mocks disabled.');
  return (await api.post('/reports', payload, { signal })).data;
}

export async function downloadReportDraft(id, { signal } = {}) {
  return (await api.get(`/reports/${id}/download`, { responseType: 'blob', signal })).data;
}

export default api;
