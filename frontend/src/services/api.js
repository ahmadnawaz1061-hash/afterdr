import axios from "axios";
import { createDemoTodaySchedule, demoCatalog, demoPrescription, demoPackageExtraction, demoVerificationResult } from "../mocks/demoData";

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api",
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
  const response = await api.get("/dashboard");
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

export default api;
