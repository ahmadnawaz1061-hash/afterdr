import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertOctagon,
  AlertTriangle,
  ArrowLeft,
  Calendar,
  CalendarX,
  CheckCircle2,
  ExternalLink,
  FilePenLine,
  HelpCircle,
  Info,
  Package,
  RefreshCw,
  RotateCcw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import FileUploader from '../components/common/FileUploader';
import LoadingState from '../components/common/LoadingState';
import ErrorMessage from '../components/common/ErrorMessage';
import { extractPackage, verifyPackage } from '../services/api';

const SAMPLES = [
  {
    label: 'Augmentin 625mg (DRAP Reg #012345)',
    description: 'Active registered Pakistani medicine',
    data: {
      brand_name: 'Augmentin',
      active_ingredient: 'Amoxicillin + Clavulanic Acid',
      manufacturer: 'GlaxoSmithKline Pakistan Limited',
      registration_number: '012345',
      batch_number: 'GSK-88192',
      mfg_date_text: 'JAN 2024',
      expiry_date_text: 'DEC 2028',
      strength: '625 mg',
      dosage_form: 'tablet',
      barcode_or_qr: '8964000123456',
      visual_packaging_flags: [],
      image_quality_issues: [],
      altered_label_flags: [],
    },
  },
  {
    label: 'DRAP Recalled Batch (Augmentin #PK-AUG-991)',
    description: 'Class 1 counterfeit alert issued by DRAP',
    data: {
      brand_name: 'Augmentin',
      active_ingredient: 'Amoxicillin + Clavulanic Acid',
      manufacturer: 'GlaxoSmithKline Pakistan Limited',
      registration_number: '012345',
      batch_number: 'PK-AUG-991',
      mfg_date_text: 'JAN 2024',
      expiry_date_text: 'DEC 2028',
      strength: '625 mg',
      dosage_form: 'tablet',
      barcode_or_qr: '8964000123456',
      visual_packaging_flags: [],
      image_quality_issues: [],
      altered_label_flags: [],
    },
  },
  {
    label: 'Suspicious Mismatched Manufacturer',
    description: 'Registered brand with fake lab label',
    data: {
      brand_name: 'Augmentin',
      active_ingredient: 'Amoxicillin + Clavulanic Acid',
      manufacturer: 'Counterfeit Pharma Lab',
      registration_number: '012345',
      batch_number: 'CP-4401',
      mfg_date_text: 'FEB 2024',
      expiry_date_text: 'DEC 2028',
      strength: '625 mg',
      dosage_form: 'tablet',
      barcode_or_qr: '8964000999999',
      visual_packaging_flags: ['Hologram missing from carton flap'],
      image_quality_issues: [],
      altered_label_flags: ['Font style irregular compared to manufacturer standards'],
    },
  },
  {
    label: 'Expired Medicine (Panadol 500mg)',
    description: 'Expiry date in the past',
    data: {
      brand_name: 'Panadol',
      active_ingredient: 'Paracetamol',
      manufacturer: 'GlaxoSmithKline Pakistan Limited',
      registration_number: '005432',
      batch_number: 'GSK-1102',
      mfg_date_text: 'JAN 2021',
      expiry_date_text: 'DEC 2023',
      strength: '500 mg',
      dosage_form: 'tablet',
      barcode_or_qr: '8964000555555',
      visual_packaging_flags: [],
      image_quality_issues: [],
      altered_label_flags: [],
    },
  },
];

const OUTCOME_STYLES = {
  verified_authoritative: {
    bg: 'bg-emerald-50 border-emerald-300 text-emerald-900',
    badge: 'bg-emerald-600 text-white',
    icon: ShieldCheck,
    title: 'Verified through an authoritative source',
  },
  registered_unconfirmed: {
    bg: 'bg-blue-50 border-blue-300 text-blue-900',
    badge: 'bg-blue-600 text-white',
    icon: Shield,
    title: 'Registered product found — package authenticity unconfirmed',
  },
  potentially_suspicious: {
    bg: 'bg-amber-50 border-amber-300 text-amber-900',
    badge: 'bg-amber-600 text-white',
    icon: AlertTriangle,
    title: 'Potentially suspicious',
  },
  possible_recall: {
    bg: 'bg-rose-50 border-rose-300 text-rose-900',
    badge: 'bg-rose-700 text-white',
    icon: AlertOctagon,
    title: 'Possible recall or safety alert',
  },
  expired: {
    bg: 'bg-orange-50 border-orange-300 text-orange-900',
    badge: 'bg-orange-600 text-white',
    icon: CalendarX,
    title: 'Expired',
  },
  inconclusive: {
    bg: 'bg-slate-50 border-slate-300 text-slate-800',
    badge: 'bg-slate-600 text-white',
    icon: HelpCircle,
    title: 'Inconclusive — more information needed',
  },
};

export default function VerificationPage() {
  const navigate = useNavigate();

  // Workflow steps: 'upload' | 'review' | 'result'
  const [step, setStep] = useState('upload');
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [error, setError] = useState(null);

  // Extracted and reviewed packaging values
  const [formData, setFormData] = useState({
    brand_name: '',
    active_ingredient: '',
    manufacturer: '',
    registration_number: '',
    batch_number: '',
    mfg_date_text: '',
    expiry_date_text: '',
    strength: '',
    dosage_form: '',
    barcode_or_qr: '',
    visual_packaging_flags: [],
    image_quality_issues: [],
    altered_label_flags: [],
  });

  const [hasVisualFlagInput, setHasVisualFlagInput] = useState(false);
  const [customFlagText, setCustomFlagText] = useState('');

  // Assessment results from backend
  const [verificationResult, setVerificationResult] = useState(null);

  const handleFileSelected = async (file) => {
    setSelectedFile(file);
    setError(null);
    if (file) {
      setPreviewUrl(URL.createObjectURL(file));
      setLoading(true);
      setLoadingMessage('Extracting packaging details and scanning text with AI vision...');
      try {
        const extracted = await extractPackage(file);
        setFormData({
          brand_name: extracted.brand_name || '',
          active_ingredient: extracted.active_ingredient || '',
          manufacturer: extracted.manufacturer || '',
          registration_number: extracted.registration_number || '',
          batch_number: extracted.batch_number || '',
          mfg_date_text: extracted.mfg_date_text || '',
          expiry_date_text: extracted.expiry_date_text || '',
          strength: extracted.strength || '',
          dosage_form: extracted.dosage_form || '',
          barcode_or_qr: extracted.barcode_or_qr || '',
          visual_packaging_flags: extracted.visual_packaging_flags || [],
          image_quality_issues: extracted.image_quality_issues || [],
          altered_label_flags: extracted.altered_label_flags || [],
        });
        setStep('review');
      } catch (err) {
        setError(err.message || 'Failed to extract information from packaging image. You can enter details manually.');
        setStep('review');
      } finally {
        setLoading(false);
      }
    }
  };

  const loadSample = (sample) => {
    setError(null);
    setFormData({ ...sample.data });
    setStep('review');
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleAddCustomFlag = () => {
    if (customFlagText.trim()) {
      setFormData((prev) => ({
        ...prev,
        altered_label_flags: [...prev.altered_label_flags, customFlagText.trim()],
      }));
      setCustomFlagText('');
    }
  };

  const handleRemoveFlag = (index, field) => {
    setFormData((prev) => ({
      ...prev,
      [field]: prev[field].filter((_, i) => i !== index),
    }));
  };

  const handleVerify = async (e) => {
    if (e) e.preventDefault();
    setLoading(true);
    setLoadingMessage('Cross-referencing DRAP official records, recalls, and manufacturer batches...');
    setError(null);

    try {
      const payload = {
        patient_id: 1,
        brand_name: formData.brand_name || null,
        active_ingredient: formData.active_ingredient || null,
        manufacturer: formData.manufacturer || null,
        registration_number: formData.registration_number || null,
        batch_number: formData.batch_number || null,
        mfg_date_text: formData.mfg_date_text || null,
        expiry_date_text: formData.expiry_date_text || null,
        strength: formData.strength || null,
        dosage_form: formData.dosage_form || null,
        barcode_or_qr: formData.barcode_or_qr || null,
        visual_packaging_flags: formData.visual_packaging_flags || [],
        image_quality_issues: formData.image_quality_issues || [],
        altered_label_flags: formData.altered_label_flags || [],
      };

      const result = await verifyPackage(payload);
      setVerificationResult(result);
      setStep('result');
    } catch (err) {
      setError(err.message || 'Verification service failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setStep('upload');
    setSelectedFile(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setVerificationResult(null);
    setError(null);
    setFormData({
      brand_name: '',
      active_ingredient: '',
      manufacturer: '',
      registration_number: '',
      batch_number: '',
      mfg_date_text: '',
      expiry_date_text: '',
      strength: '',
      dosage_form: '',
      barcode_or_qr: '',
      visual_packaging_flags: [],
      image_quality_issues: [],
      altered_label_flags: [],
    });
  };

  const outcomeKey = verificationResult?.outcome || 'inconclusive';
  const outcomeConfig = OUTCOME_STYLES[outcomeKey] || OUTCOME_STYLES.inconclusive;
  const OutcomeIcon = outcomeConfig.icon;

  return (
    <div className="max-w-5xl mx-auto space-y-8 pb-16">
      {/* Page Header */}
      <div className="bg-gradient-to-r from-teal-900 to-emerald-900 text-white rounded-2xl p-6 md:p-8 shadow-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-700/60 text-emerald-100 border border-emerald-500/30">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-300" />
                Pakistan DRAP Verified Catalog
              </span>
              <span className="text-xs text-emerald-200/80 font-medium">Batch & Recall Monitoring</span>
            </div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Medicine Authenticity Checker</h1>
            <p className="text-emerald-100/90 text-sm md:text-base mt-1 max-w-2xl">
              Upload photographs of medicine boxes, blister foils, bottles, or labels to inspect packaging markings against official Drug Regulatory Authority of Pakistan (DRAP) registration and recall records.
            </p>
          </div>
          {step !== 'upload' && (
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 self-start md:self-auto px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm font-medium transition border border-white/20 shadow-sm"
            >
              <RotateCcw className="w-4 h-4" />
              Check Another Medicine
            </button>
          )}
        </div>
      </div>

      {/* Progress Steps Header */}
      <div className="grid grid-cols-3 gap-2 text-center text-xs md:text-sm font-medium border-b border-gray-200 pb-3">
        <div className={`flex items-center justify-center gap-2 pb-1 border-b-2 ${step === 'upload' ? 'border-teal-600 text-teal-700 font-bold' : 'border-transparent text-gray-500'}`}>
          <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold bg-teal-100 text-teal-800">1</span>
          Upload Packaging Photo
        </div>
        <div className={`flex items-center justify-center gap-2 pb-1 border-b-2 ${step === 'review' ? 'border-teal-600 text-teal-700 font-bold' : 'border-transparent text-gray-500'}`}>
          <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold bg-teal-100 text-teal-800">2</span>
          Review Extracted Fields
        </div>
        <div className={`flex items-center justify-center gap-2 pb-1 border-b-2 ${step === 'result' ? 'border-teal-600 text-teal-700 font-bold' : 'border-transparent text-gray-500'}`}>
          <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold bg-teal-100 text-teal-800">3</span>
          Authenticity Assessment
        </div>
      </div>

      {error && <ErrorMessage message={error} onDismiss={() => setError(null)} />}

      {/* STEP 1: UPLOAD */}
      {step === 'upload' && (
        <div className="space-y-8">
          {loading ? (
            <div className="bg-white rounded-2xl p-12 border border-gray-200 shadow-sm text-center">
              <LoadingState message={loadingMessage} />
            </div>
          ) : (
            <>
              <div className="bg-white rounded-2xl p-6 md:p-8 border border-gray-200 shadow-sm space-y-6">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Step 1 — Upload Medicine Packaging Image</h2>
                  <p className="text-sm text-gray-600 mt-1">
                    Take a clear photo of the medicine box front, side panel, blister pack foil, or label showing the registration number, brand name, and batch information.
                  </p>
                </div>

                <FileUploader
                  id="packaging-file-uploader"
                  label="Drop packaging photograph here or click to browse"
                  accept="image/jpeg,image/png,image/webp"
                  maxSizeBytes={5 * 1024 * 1024}
                  onFileSelected={handleFileSelected}
                />

                <div className="bg-amber-50 rounded-xl p-4 border border-amber-200 flex gap-3 text-xs md:text-sm text-amber-900">
                  <Info className="w-5 h-5 text-amber-700 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold">Photography Tips for Higher Accuracy:</span> Ensure adequate lighting, avoid glare on glossy blister foil, and frame the camera so the DRAP Registration Number (e.g., Reg. No. 012345), batch code, and expiry date are sharp and legible.
                  </div>
                </div>
              </div>

              {/* Sample Packaging Quick-Select */}
              <div className="bg-gray-50 rounded-2xl p-6 border border-gray-200 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-emerald-600" />
                      Quick Demo Packaging Samples
                    </h3>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Test the authenticity checker immediately without uploading your own file:
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {SAMPLES.map((sample, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => loadSample(sample)}
                      className="text-left p-3.5 rounded-xl border border-gray-200 bg-white hover:border-teal-500 hover:shadow-sm transition group"
                    >
                      <div className="font-medium text-xs md:text-sm text-gray-900 group-hover:text-teal-700 flex items-center justify-between">
                        {sample.label}
                        <span className="text-xs text-teal-600 font-semibold group-hover:underline">Load &rarr;</span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">{sample.description}</div>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* STEP 2: REVIEW & EDIT */}
      {step === 'review' && (
        <form onSubmit={handleVerify} className="space-y-6">
          {loading ? (
            <div className="bg-white rounded-2xl p-12 border border-gray-200 shadow-sm text-center">
              <LoadingState message={loadingMessage} />
            </div>
          ) : (
            <div className="bg-white rounded-2xl p-6 md:p-8 border border-gray-200 shadow-sm space-y-6">
              <div className="flex items-center justify-between border-b border-gray-100 pb-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Step 2 — Review & Confirm Extracted Packaging Fields</h2>
                  <p className="text-xs md:text-sm text-gray-600 mt-0.5">
                    Verify transcribed medicine details. Correct any illegible or misread numbers before initiating regulatory verification.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setStep('upload')}
                  className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back to Upload
                </button>
              </div>

              {/* Photo preview thumbnail if available */}
              {previewUrl && (
                <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-xl border border-gray-200">
                  <img src={previewUrl} alt="Uploaded packaging" className="w-16 h-16 object-cover rounded-lg border border-gray-300" />
                  <div className="text-xs text-gray-600">
                    <p className="font-medium text-gray-800">Uploaded Photograph Loaded</p>
                    <p className="text-gray-500">File: {selectedFile?.name || 'Package Photo'}</p>
                  </div>
                </div>
              )}

              {/* Form Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label htmlFor="brand_name" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Medicine / Brand Name *
                  </label>
                  <input
                    type="text"
                    id="brand_name"
                    name="brand_name"
                    required
                    value={formData.brand_name}
                    onChange={handleInputChange}
                    placeholder="e.g. Augmentin, Panadol, Brufen"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="active_ingredient" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Active Ingredient / Generic
                  </label>
                  <input
                    type="text"
                    id="active_ingredient"
                    name="active_ingredient"
                    value={formData.active_ingredient}
                    onChange={handleInputChange}
                    placeholder="e.g. Amoxicillin + Clavulanic Acid"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="strength" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Strength
                  </label>
                  <input
                    type="text"
                    id="strength"
                    name="strength"
                    value={formData.strength}
                    onChange={handleInputChange}
                    placeholder="e.g. 625 mg, 500 mg, 400 mg"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="dosage_form" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Dosage Form
                  </label>
                  <input
                    type="text"
                    id="dosage_form"
                    name="dosage_form"
                    value={formData.dosage_form}
                    onChange={handleInputChange}
                    placeholder="e.g. tablet, capsule, syrup"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="manufacturer" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Manufacturer *
                  </label>
                  <input
                    type="text"
                    id="manufacturer"
                    name="manufacturer"
                    required
                    value={formData.manufacturer}
                    onChange={handleInputChange}
                    placeholder="e.g. GlaxoSmithKline Pakistan Limited"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="registration_number" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    DRAP Registration Number
                  </label>
                  <input
                    type="text"
                    id="registration_number"
                    name="registration_number"
                    value={formData.registration_number}
                    onChange={handleInputChange}
                    placeholder="e.g. 012345 (DRAP Reg. No.)"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">Printed on carton as &quot;Reg. No. 0xxxxx&quot; or &quot;DRAP Reg No.&quot;</p>
                </div>

                <div>
                  <label htmlFor="batch_number" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Batch / Lot Number
                  </label>
                  <input
                    type="text"
                    id="batch_number"
                    name="batch_number"
                    value={formData.batch_number}
                    onChange={handleInputChange}
                    placeholder="e.g. PK-AUG-991, BATCH-1"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="barcode_or_qr" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Barcode or QR Data
                  </label>
                  <input
                    type="text"
                    id="barcode_or_qr"
                    name="barcode_or_qr"
                    value={formData.barcode_or_qr}
                    onChange={handleInputChange}
                    placeholder="e.g. 8964000123456 (GTIN or 2D matrix)"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="mfg_date_text" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Manufacturing Date (MFG)
                  </label>
                  <input
                    type="text"
                    id="mfg_date_text"
                    name="mfg_date_text"
                    value={formData.mfg_date_text}
                    onChange={handleInputChange}
                    placeholder="e.g. JAN 2024 or 2024-01-15"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label htmlFor="expiry_date_text" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Expiry Date (EXP)
                  </label>
                  <input
                    type="text"
                    id="expiry_date_text"
                    name="expiry_date_text"
                    value={formData.expiry_date_text}
                    onChange={handleInputChange}
                    placeholder="e.g. DEC 2028 or 2028-12-31"
                    className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
              </div>

              {/* Physical Packaging Anomaly Flag Section */}
              <div className="border-t border-gray-200 pt-5 space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4 text-amber-600" />
                    Observed Physical Packaging Anomalies (Optional)
                  </label>
                  <button
                    type="button"
                    onClick={() => setHasVisualFlagInput(!hasVisualFlagInput)}
                    className="text-xs text-teal-600 hover:text-teal-800 font-medium"
                  >
                    {hasVisualFlagInput ? 'Hide' : '+ Report Visual Issue'}
                  </button>
                </div>

                {hasVisualFlagInput && (
                  <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 space-y-3">
                    <p className="text-xs text-gray-600">
                      Did you notice broken tamper seals, spelling errors, peeling stickers, or unusual blister foil thickness? Add them here for authenticity evaluation.
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={customFlagText}
                        onChange={(e) => setCustomFlagText(e.target.value)}
                        placeholder="e.g. Misaligned font, missing security hologram, foil damaged"
                        className="flex-1 px-3 py-2 text-xs border border-gray-300 rounded-lg focus:ring-teal-500 focus:border-teal-500"
                      />
                      <button
                        type="button"
                        onClick={handleAddCustomFlag}
                        className="px-3 py-2 bg-gray-800 text-white rounded-lg text-xs font-medium hover:bg-gray-900"
                      >
                        Add Anomaly
                      </button>
                    </div>

                    {formData.altered_label_flags.length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-2">
                        {formData.altered_label_flags.map((flag, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs bg-amber-100 text-amber-800 border border-amber-200"
                          >
                            {flag}
                            <button
                              type="button"
                              onClick={() => handleRemoveFlag(idx, 'altered_label_flags')}
                              className="text-amber-700 hover:text-amber-900 font-bold ml-1"
                            >
                              &times;
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Submit Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  id="submit-verification-btn"
                  className="px-6 py-2.5 bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold rounded-lg shadow-sm transition flex items-center gap-2"
                >
                  <ShieldCheck className="w-4 h-4" />
                  Verify Packaging Authenticity
                </button>
              </div>
            </div>
          )}
        </form>
      )}

      {/* STEP 3: RESULTS DISPLAY */}
      {step === 'result' && verificationResult && (
        <div className="space-y-6">
          {/* Main Outcome Card */}
          <div className={`rounded-2xl p-6 md:p-8 border shadow-sm ${outcomeConfig.bg}`}>
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className={`p-3 rounded-2xl ${outcomeConfig.badge}`}>
                  <OutcomeIcon className="w-8 h-8" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${outcomeConfig.badge}`}>
                      {verificationResult.outcome || 'Assessment Result'}
                    </span>
                    <span className="text-xs text-gray-600">Verification ID #{verificationResult.verification_id}</span>
                  </div>
                  <h2 className="text-xl md:text-2xl font-bold mt-1 text-gray-950">
                    {verificationResult.outcome_label || outcomeConfig.title}
                  </h2>
                  <p className="text-sm mt-1 max-w-2xl text-gray-800">
                    {verificationResult.summary_message || 'Verification complete against available regulatory records.'}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Mandatory Regulatory & Medical Safety Limitation Banner */}
          <div className="bg-amber-50 rounded-2xl p-5 border border-amber-200 text-xs md:text-sm text-amber-950 flex gap-3 shadow-sm">
            <AlertTriangle className="w-5 h-5 text-amber-700 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-bold text-amber-900">Essential Safety & Authenticity Limitation Notice</p>
              <p className="leading-relaxed">
                {verificationResult.limitations ||
                  'A photograph, packaging inspection, or registration number match does not guarantee that a physical pharmaceutical product is genuine or therapeutically safe. Laboratory chemical assay is required for definitive authenticity testing. Never consume suspected or recalled medicines. Always consult a licensed pharmacist or contact the Drug Regulatory Authority of Pakistan (DRAP) if you observe any discrepancy.'}
              </p>
            </div>
          </div>

          {/* Discrepancies Alert (if any detected) */}
          {verificationResult.discrepancies && verificationResult.discrepancies.length > 0 && (
            <div className="bg-rose-50 rounded-2xl p-6 border border-rose-200 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-rose-950 flex items-center gap-2">
                <AlertOctagon className="w-4 h-4 text-rose-700" />
                Detected Packaging Discrepancies & Anomalies ({verificationResult.discrepancies.length})
              </h3>
              <ul className="space-y-2">
                {verificationResult.discrepancies.map((disc, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-xs md:text-sm text-rose-900">
                    <span className="font-bold text-rose-700">&bull;</span>
                    <span>{disc}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Evidence Grid & Regulatory Sources */}
          <div className="bg-white rounded-2xl p-6 md:p-8 border border-gray-200 shadow-sm space-y-6">
            <div>
              <h3 className="text-base font-bold text-gray-900">Supporting Verification Evidence</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Evaluated against official Pakistan DRAP registry, manufacturer packaging specifications, and alert registers.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {verificationResult.evidence && verificationResult.evidence.length > 0 ? (
                verificationResult.evidence.map((item, idx) => (
                  <div
                    key={idx}
                    className={`p-4 rounded-xl border text-xs md:text-sm ${item.is_critical ? 'bg-rose-50/70 border-rose-200 text-rose-950' : 'bg-gray-50 border-gray-200 text-gray-800'}`}
                  >
                    <div className="flex items-center justify-between text-xs font-semibold mb-1">
                      <span className="uppercase tracking-wider text-gray-500">{item.category.replace(/_/g, ' ')}</span>
                      <span className="text-gray-600 font-medium">{item.source}</span>
                    </div>
                    <p className="mt-1">{item.detail}</p>
                    {item.source_url && (
                      <a
                        href={item.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-teal-700 hover:underline mt-2 font-medium"
                      >
                        Official Authority Reference <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                ))
              ) : (
                <div className="col-span-2 text-center text-xs text-gray-500 py-4">No specific evidence records available.</div>
              )}
            </div>

            {/* DRAP Source Links */}
            {verificationResult.source_links && verificationResult.source_links.length > 0 && (
              <div className="border-t border-gray-100 pt-4 flex flex-wrap items-center gap-4 text-xs">
                <span className="font-semibold text-gray-700">Official Regulatory Links:</span>
                {verificationResult.source_links.map((link, idx) => (
                  <a
                    key={idx}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-teal-700 hover:text-teal-900 hover:underline"
                  >
                    {link.title} <ExternalLink className="w-3 h-3" />
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Recommended Next Steps */}
          {verificationResult.recommended_next_steps && verificationResult.recommended_next_steps.length > 0 && (
            <div className="bg-white rounded-2xl p-6 md:p-8 border border-gray-200 shadow-sm space-y-4">
              <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-teal-700" />
                Recommended Next Steps for Patient Safety
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {verificationResult.recommended_next_steps.map((step, idx) => (
                  <div key={idx} className="flex items-start gap-2.5 p-3 rounded-xl bg-teal-50/50 border border-teal-100 text-xs md:text-sm text-teal-950">
                    <span className="w-5 h-5 rounded-full bg-teal-700 text-white flex-shrink-0 flex items-center justify-center text-xs font-bold mt-0.5">
                      {idx + 1}
                    </span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Bar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-gray-50 p-6 rounded-2xl border border-gray-200">
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-gray-300 rounded-xl text-sm font-semibold text-gray-700 hover:bg-gray-100 transition shadow-sm w-full sm:w-auto justify-center"
            >
              <RotateCcw className="w-4 h-4" /> Check Another Medicine
            </button>

            <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
              <button
                type="button"
                id="prepare-drap-report-btn"
                onClick={() => navigate(`/reporting?verification_id=${verificationResult.verification_id}`)}
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-teal-700 hover:bg-teal-800 text-white rounded-xl text-sm font-semibold shadow-sm transition w-full sm:w-auto justify-center"
              >
                <FilePenLine className="w-4 h-4" /> Prepare DRAP Complaint Draft
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
