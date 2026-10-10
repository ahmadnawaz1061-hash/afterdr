import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import FileUploader, { MAX_IMAGE_SIZE } from './FileUploader';

beforeEach(() => {
  let sequence = 0;
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => `blob:preview-${++sequence}`);
    static revokeObjectURL = vi.fn();
  });
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const png = () => new File(['image bytes'], 'prescription.png', { type: 'image/png' });
const input = () => screen.getByLabelText('Upload an image');
const dropZone = () => screen.getByText('Drag and drop an image, or choose a file.').parentElement;

describe('FileUploader', () => {
  it('selects, previews, removes, and reselects an image, cleaning up its URL', () => {
    const onFileSelect = vi.fn();
    const file = png();
    render(<FileUploader onFileSelect={onFileSelect} />);
    expect(input().getAttribute('accept')).toBe('image/png,image/jpeg');
    fireEvent.change(input(), { target: { files: [file] } });
    expect(onFileSelect).toHaveBeenLastCalledWith(file);
    expect(screen.getByRole('img').getAttribute('src')).toBe('blob:preview-1');
    expect(screen.getByRole('status').textContent).toContain(file.name);
    fireEvent.click(screen.getByRole('button', { name: 'Remove image' }));
    expect(onFileSelect).toHaveBeenLastCalledWith(null);
    expect(screen.queryByRole('img')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-1');
    expect(document.activeElement).toBe(input());
    fireEvent.change(input(), { target: { files: [file] } });
    expect(screen.getByRole('img').getAttribute('src')).toBe('blob:preview-2');
  });

  it('accepts a dropped JPEG at the size limit', () => {
    const onFileSelect = vi.fn();
    render(<FileUploader onFileSelect={onFileSelect} />);
    const file = new File([new Uint8Array(MAX_IMAGE_SIZE)], 'package.jpg', { type: 'image/jpeg' });
    fireEvent.drop(dropZone(), { dataTransfer: { files: [file] } });
    expect(onFileSelect).toHaveBeenCalledWith(file);
    expect(screen.getByRole('img').getAttribute('alt')).toContain('package.jpg');
  });

  it.each([
    ['unsupported type', () => [new File(['text'], 'notes.txt', { type: 'text/plain' })], 'Choose a PNG or JPEG image.'],
    ['oversized file', () => [new File([new Uint8Array(MAX_IMAGE_SIZE + 1)], 'large.png', { type: 'image/png' })], 'The image must be 5 MB or smaller.'],
    ['empty file', () => [new File([], 'empty.png', { type: 'image/png' })], 'This file is empty.'],
    ['multiple files', () => [png(), png()], 'Choose one image at a time.'],
  ])('rejects %s for both the picker and drop zone', (_, files, message) => {
    const onFileSelect = vi.fn();
    render(<FileUploader onFileSelect={onFileSelect} />);
    fireEvent.change(input(), { target: { files: files() } });
    expect(screen.getByRole('alert').textContent).toContain(message);
    fireEvent.drop(dropZone(), { dataTransfer: { files: files() } });
    expect(screen.getByRole('alert').textContent).toContain(message);
    expect(input().getAttribute('aria-invalid')).toBe('true');
    expect(input().getAttribute('aria-describedby')).toContain(screen.getByRole('alert').id);
    expect(onFileSelect).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('keeps a valid selection after an invalid replacement and clears errors on a valid one', () => {
    render(<FileUploader />);
    fireEvent.change(input(), { target: { files: [png()] } });
    fireEvent.drop(dropZone(), { dataTransfer: { files: [new File(['bad'], 'bad.pdf', { type: 'application/pdf' })] } });
    expect(screen.getByRole('img').getAttribute('src')).toBe('blob:preview-1');
    fireEvent.change(input(), { target: { files: [png()] } });
    expect(screen.getByRole('alert').textContent).toBe('');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-1');
  });

  it('ignores cancelled selection and drops when disabled', () => {
    const onFileSelect = vi.fn();
    const { rerender } = render(<FileUploader onFileSelect={onFileSelect} />);
    fireEvent.change(input(), { target: { files: [] } });
    rerender(<FileUploader onFileSelect={onFileSelect} disabled />);
    expect(input().disabled).toBe(true);
    fireEvent.drop(dropZone(), { dataTransfer: { files: [png()] } });
    expect(onFileSelect).not.toHaveBeenCalled();
  });

  it('clears unreadable images and releases the preview URL', () => {
    const onFileSelect = vi.fn();
    render(<FileUploader onFileSelect={onFileSelect} />);
    fireEvent.change(input(), { target: { files: [png()] } });
    fireEvent.error(screen.getByRole('img'));
    expect(screen.getByRole('alert').textContent).toContain('could not be previewed');
    expect(screen.queryByRole('img')).toBeNull();
    expect(onFileSelect).toHaveBeenLastCalledWith(null);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-1');
  });

  it('releases every preview URL on replacement and unmount under StrictMode', () => {
    const { unmount } = render(<StrictMode><FileUploader /></StrictMode>);
    fireEvent.change(input(), { target: { files: [png()] } });
    fireEvent.change(input(), { target: { files: [png()] } });
    unmount();
    for (const { value: url } of URL.createObjectURL.mock.results) {
      expect(URL.revokeObjectURL).toHaveBeenCalledWith(url);
    }
  });
});
