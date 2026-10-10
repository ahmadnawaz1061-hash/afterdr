export const MAX_FILE_SIZE = 5 * 1024 * 1024;
export const MAX_UPLOAD_TOTAL = 12 * 1024 * 1024 - 16 * 1024;

export async function validatePackagingFile(file) {
  if (!file || !['image/png', 'image/jpeg'].includes(file.type)) throw new Error('Choose a PNG or JPEG photograph.');
  if (!file.size) throw new Error('This image is empty.');
  if (file.size > MAX_FILE_SIZE) throw new Error('Each photograph must be 5 MB or smaller.');
  const blob = file.slice(0, 12);
  const buffer = blob.arrayBuffer ? await blob.arrayBuffer() : await new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('Could not read this image.')); reader.readAsArrayBuffer(blob);
  });
  const bytes = new Uint8Array(buffer);
  const png = [137, 80, 78, 71, 13, 10, 26, 10].every((value, index) => bytes[index] === value);
  const jpeg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
  if (!png && !jpeg) throw new Error('The file contents are not a PNG or JPEG image.');
  let width, height;
  if (typeof createImageBitmap === 'function') {
    let bitmap;
    try { bitmap = await createImageBitmap(file); width = bitmap.width; height = bitmap.height; }
    catch { throw new Error('This image cannot be decoded. Choose a different photo.'); }
    finally { bitmap?.close(); }
  } else {
    const url = URL.createObjectURL(file);
    try {
      [width, height] = await new Promise((resolve, reject) => {
        const image = new Image(); image.onload = () => resolve([image.naturalWidth, image.naturalHeight]); image.onerror = () => reject(new Error('This image cannot be decoded.')); image.src = url;
      });
    } finally { URL.revokeObjectURL(url); }
  }
  if (width > 6000 || height > 6000) throw new Error('Image dimensions must be no greater than 6000 × 6000 pixels.');
  return file;
}
