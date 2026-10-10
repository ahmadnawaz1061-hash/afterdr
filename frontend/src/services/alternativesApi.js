import api from './api';

// Module C always uses the Pakistan catalog, independently of other modules' mocks.
function medicineList(data, alternatives = false) {
  if (!Array.isArray(data) || data.some((record) =>
    !record || !Number.isSafeInteger(record.id) || record.id < 1 || record.data_source !== 'drap_pk' ||
    !['brand_name', 'active_ingredient', 'strength', 'dosage_form', 'route', 'release_type', 'registration_no']
      .every((key) => typeof record[key] === 'string' && record[key].trim()) ||
    (alternatives && (record.is_alternative !== true ||
      !Array.isArray(record.match_reasons) || !record.match_reasons.every((reason) => typeof reason === 'string'))),
  )) throw new Error('The Pakistan medicine catalog returned an invalid response. Please try again.');
  return data;
}

export async function searchAlternativeMedicines(query = '', { signal, offset = 0 } = {}) {
  const term = query.trim();
  if (term.length > 100) throw new Error('Use 100 characters or fewer for your search.');
  if (!Number.isSafeInteger(offset) || offset < 0 || offset > 10000) throw new Error('Invalid catalog page. Start a new search.');
  const params = { q: term, catalog: 'drap_pk', ...(offset ? { offset } : {}) };
  const response = await api.get('/medicines/search', { params, signal });
  return medicineList(response.data);
}

export async function getMedicineAlternatives(medicineId, { signal } = {}) {
  if (!Number.isSafeInteger(medicineId) || medicineId < 1) throw new Error('Select a medicine from the catalog first.');
  const response = await api.get(`/medicines/${medicineId}/alternatives`, { params: { catalog: 'drap_pk' }, signal });
  return medicineList(response.data, true);
}
