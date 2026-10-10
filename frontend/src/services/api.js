import axios from "axios";
import { createDemoTodaySchedule, demoCatalog, demoPrescription } from "../mocks/demoData";

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
  const response = await api.post("/prescriptions", payload);
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

export default api;
