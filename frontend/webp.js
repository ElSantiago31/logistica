/**
 * webp.js — Generación automática de versiones .webp de imágenes estáticas.
 *
 * Se ejecuta como parte de `npm run build` (invocado por build.js y por el
 * Dockerfile en el stage js-builder). Para CADA imagen .jpg/.jpeg/.png bajo
 * public/ genera el hermano .webp (misma ruta, misma base, extensión .webp).
 *
 * Reglas:
 *   - El .webp se regenera solo si no existe o si el original cambió (mtime).
 *   - Si el .webp quedara más pesado que el original, se descarta (nunca empeorar).
 *   - Los .webp NO se commitean (.gitignore) — siempre se generan en build.
 *   - El servidor los sirve automáticamente vía WebPStaticFiles (negociación
 *     por cabecera Accept), así que las plantillas siguen usando las URLs .jpg.
 *
 * Degradación suave: si `sharp` no está instalado, emite un warning y continúa
 * (el build NO falla — simplemente no habrá .webp y se servirán los originales).
 */
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const PUBLIC_DIR = path.join(ROOT, "public");
const SOURCE_EXTS = new Set([".jpg", ".jpeg", ".png"]);
const WEBP_QUALITY = 82;
const MAX_DIM = 1920;

function listRasterImages(dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...listRasterImages(full));
    } else if (SOURCE_EXTS.has(path.extname(entry.name).toLowerCase())) {
      results.push(full);
    }
  }
  return results;
}

async function generateWebp() {
  let sharp;
  try {
    sharp = require("sharp");
  } catch {
    console.warn(
      "  ⚠ sharp no está instalado — se omitió la generación de .webp.\n" +
        "    Instálalo con: cd frontend && npm install"
    );
    return;
  }

  const images = listRasterImages(PUBLIC_DIR);
  if (images.length === 0) {
    console.log("  (no hay imágenes raster para convertir)");
    return;
  }

  let created = 0;
  let skipped = 0;
  for (const imgPath of images) {
    const webpPath = imgPath.replace(/\.[^.]+$/, ".webp");

    // Regenerar solo si no existe o si el original cambió (mtime)
    try {
      if (fs.existsSync(webpPath)) {
        const [srcStat, dstStat] = [fs.statSync(imgPath), fs.statSync(webpPath)];
        if (dstStat.mtimeMs >= srcStat.mtimeMs) {
          skipped++;
          continue;
        }
      }
    } catch {
      /* stat falló: regenerar */
    }

    try {
      const srcSize = fs.statSync(imgPath).size;
      const pipeline = sharp(imgPath);
      const meta = await pipeline.metadata();
      let outPipeline = pipeline;
      if (meta.width && meta.width > MAX_DIM) {
        outPipeline = pipeline.resize({ width: MAX_DIM });
      }
      const info = await outPipeline
        .webp({ quality: WEBP_QUALITY })
        .toFile(webpPath + ".tmp");

      // Nunca empeorar: si el .webp pesa más, descartarlo
      if (info.size >= srcSize) {
        fs.unlinkSync(webpPath + ".tmp");
        skipped++;
        continue;
      }
      fs.renameSync(webpPath + ".tmp", webpPath);
      const saving = ((1 - info.size / srcSize) * 100).toFixed(0);
      console.log(
        `  ✓ ${path.relative(PUBLIC_DIR, imgPath)} → ${path.basename(webpPath)} ` +
          `(${(srcSize / 1024).toFixed(0)}KB → ${(info.size / 1024).toFixed(0)}KB, −${saving}%)`
      );
      created++;
    } catch (err) {
      console.error(`  ✗ ${path.relative(PUBLIC_DIR, imgPath)}: ${err.message}`);
    }
  }
  console.log(`\nDone WebP: ${created} generados, ${skipped} sin cambios.`);
}

module.exports = { generateWebp };

// Ejecución directa: node webp.js
if (require.main === module) {
  (async () => {
    console.log("\n=== Fase WebP: optimización de imágenes ===");
    await generateWebp();
  })();
}