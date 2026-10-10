import { useEffect, useId, useRef, useState } from 'react';
import { ImagePlus, X } from 'lucide-react';

export const MAX_IMAGE_SIZE = 5 * 1024 * 1024;
const acceptedTypes = new Set(['image/png', 'image/jpeg']);

// This component only selects a local file. HTTP uploads belong in services/api.js.
export default function FileUploader({ onFileSelect, label = 'Upload an image', disabled = false }) {
  const id = useId();
  const inputRef = useRef(null);
  const dragDepth = useRef(0);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview({ file, url });
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFiles(files) {
    if (disabled || !files?.length) return;
    if (files.length !== 1) {
      setError('Choose one image at a time.');
      return;
    }
    const nextFile = files[0];
    if (!acceptedTypes.has(nextFile.type)) {
      setError('Choose a PNG or JPEG image.');
      return;
    }
    if (nextFile.size === 0) {
      setError('This file is empty. Choose a PNG or JPEG image.');
      return;
    }
    if (nextFile.size > MAX_IMAGE_SIZE) {
      setError('The image must be 5 MB or smaller.');
      return;
    }
    setError('');
    setFile(nextFile);
    onFileSelect?.(nextFile);
  }

  function removeFile() {
    setFile(null);
    setPreview(null);
    setError('');
    onFileSelect?.(null);
    inputRef.current?.focus();
  }

  return (
    <div className="space-y-3">
      <label htmlFor={id} className="block text-sm font-semibold text-slate-900">{label}</label>
      <div
        className={`rounded-2xl border-2 border-dashed p-5 transition-colors sm:p-6 ${disabled ? 'border-slate-200 bg-slate-100' : dragging ? 'border-teal-600 bg-teal-50' : 'border-slate-300 bg-white'}`}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) { dragDepth.current += 1; setDragging(true); }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = disabled ? 'none' : 'copy';
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          selectFiles(event.dataTransfer.files);
        }}
      >
        <ImagePlus size={28} className="mb-3 text-teal-700" aria-hidden="true" />
        <p className="text-sm font-medium text-slate-800">Drag and drop an image, or choose a file.</p>
        <p id={`${id}-help`} className="mt-1 text-sm text-slate-600">PNG or JPEG · One image · Maximum 5 MB</p>
        <input ref={inputRef} id={id} type="file" accept="image/png,image/jpeg" disabled={disabled}
          aria-describedby={`${id}-help${error ? ` ${id}-error` : ''}`} aria-invalid={Boolean(error)}
          className="mt-4 block min-h-11 w-full min-w-0 rounded-lg text-base text-slate-600 file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-lg file:border-0 file:bg-teal-50 file:px-4 file:font-semibold file:text-teal-900 disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
          onChange={(event) => {
            selectFiles(event.target.files);
            // Allow selecting the same file again after a rejection or removal.
            event.target.value = '';
          }}
        />
      </div>
      <p id={`${id}-error`} role="alert" aria-live="assertive" aria-atomic="true" className={error ? 'text-sm font-medium text-rose-700' : 'sr-only'}>{error}</p>
      <p role="status" aria-live="polite" aria-atomic="true" className="text-sm text-slate-600 wrap-anywhere">
        {file ? `Selected: ${file.name}` : 'No image selected.'}
      </p>
      {file && <div className="rounded-2xl border border-slate-200 bg-white p-4">
        {preview?.file === file && <img key={preview.url} src={preview.url} alt={`Preview of ${file.name}`}
          className="max-h-72 w-full rounded-lg object-contain"
          onError={() => {
            setFile(null);
            setPreview(null);
            setError('This image could not be previewed. Choose another PNG or JPEG image.');
            onFileSelect?.(null);
          }}
        />}
        <button type="button" disabled={disabled} onClick={removeFile}
          className="button-secondary mt-4 gap-2 disabled:cursor-not-allowed disabled:opacity-60">
          <X size={16} aria-hidden="true" />Remove image
        </button>
      </div>}
    </div>
  );
}
