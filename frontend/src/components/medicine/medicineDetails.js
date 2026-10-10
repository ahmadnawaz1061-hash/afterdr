export const substitutionNotice = 'Confirm with your pharmacist or prescriber before substituting.';

export function displayValue(value) {
  return value == null || value === '' ? 'Not provided' : value;
}

export function medicineDetails(medicine) {
  return [
    ['Strength', displayValue(medicine.strength)],
    ['Dose', displayValue(medicine.dose)],
    ['Frequency', displayValue(medicine.frequency)],
    ['Duration', medicine.duration_days == null ? 'Not provided' : `${medicine.duration_days} ${medicine.duration_days === 1 ? 'day' : 'days'}`],
  ];
}
