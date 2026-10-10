// Deterministic demonstrations only. Never used as verified catalog evidence.
export const packagingStatusLabels = {
  likely_consistent: 'Looks consistent with an authentic product',
  suspicious: 'Suspicious: possible knockoff or lookalike',
  unable_to_assess: "Can't tell from these photos",
};

export function createPackagingDemo(scenario = 'consistent', fields = {}, id = 1) {
  if (!['consistent', 'suspicious_lookalike', 'registration_mismatch_demo', 'unclear_image'].includes(scenario)) throw new Error('Invalid VITE_PACKAGING_DEMO_SCENARIO configuration.');
  const unclear = scenario === 'unclear_image';
  const suspicious = ['suspicious_lookalike', 'registration_mismatch_demo'].includes(scenario);
  const status = unclear ? 'unable_to_assess' : suspicious ? 'suspicious' : 'likely_consistent';
  const registration = scenario === 'registration_mismatch_demo' ? 'simulated_mismatch' : 'not_in_reference';
  return {
    verification_id: id, status, status_label: packagingStatusLabels[status],
    risk_level: unclear ? 'unknown' : suspicious ? 'medium' : 'low', risk_score: unclear ? null : suspicious ? 40 : 0,
    summary: unclear ? 'The simulated label cannot be read. Retake clearer photos.' : suspicious ? 'Simulated discrepancies demonstrate the inspection workflow.' : 'The simulated observations show clear, consistent product details.',
    extracted: { brand_name: unclear ? null : scenario === 'suspicious_lookalike' ? 'Demo Relief Onne' : 'Demo Relief One', active_ingredient: unclear ? null : 'Examplemol', strength: unclear ? null : '500 mg', dosage_form: unclear ? null : 'tablet', manufacturer: unclear ? null : 'Demo manufacturer', registration_number: null, pack_type: unclear ? null : 'carton', ...fields },
    signals: [{ category: scenario === 'registration_mismatch_demo' ? 'registration' : suspicious ? 'name_brand' : 'label_print', severity: suspicious ? 'high' : unclear ? 'neutral' : 'positive', title: unclear ? 'Simulated unclear label' : suspicious ? 'Simulated discrepancy' : 'Simulated consistent printing', detail: 'Synthetic observation illustrating packaging analysis; no actual product or regulatory determination is represented.', evidence: 'Demonstration fixture', origin: 'simulated_demo', simulated: true, registration_state: scenario === 'registration_mismatch_demo' ? 'simulated_mismatch' : null }],
    matched_reference: null, registration_state: registration, counterfeit_confirmed: false,
    source: 'simulated_demo', limitations: ['Photographs cannot establish physical authenticity or confirm a counterfeit.', 'This is a simulated demonstration; no registry lookup was performed.'],
    simulated: true, image_quality: [], assessed_at: new Date().toISOString(), cached: false, reanalysis_of: null,
    online_lookup: { status: 'simulated', query: null, summary: 'Demo mode does not query the internet; no live product match is claimed.', sources: [], product: null, searched_at: null, source: 'Live DRAP public product index' },
    next_steps: unclear ? ['Retake clear photos with the label in focus.'] : ['Review any concerns with a pharmacist or manufacturer.', 'Keep the packaging and purchase receipt.'],
  };
}
