const MAX_DIMENSION = 1024;
const INITIAL_QUALITY = 0.85;
const MIN_QUALITY = 0.5;
const QUALITY_STEP = 0.1;

function canvasToBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

function withJpegExtension(filename: string): string {
  return `${filename.replace(/\.[^.]+$/, "")}.jpg`;
}

/**
 * Downscales to at most MAX_DIMENSION on the long edge and re-encodes as JPEG,
 * stepping quality down until the result fits maxBytes (or MIN_QUALITY is hit).
 * Falls back to the original file if canvas encoding isn't available.
 */
export async function compressImage(file: File, maxBytes: number): Promise<File> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    bitmap.close();
    return file;
  }
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  let quality = INITIAL_QUALITY;
  let blob = await canvasToBlob(canvas, quality);
  while (blob && blob.size > maxBytes && quality > MIN_QUALITY) {
    quality -= QUALITY_STEP;
    blob = await canvasToBlob(canvas, quality);
  }

  if (!blob) return file;
  return new File([blob], withJpegExtension(file.name), { type: "image/jpeg" });
}
