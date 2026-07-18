/**
 * build.js — Pipeline de build de assets frontend.
 *
 * Dos fases:
 *   1. Tailwind CSS: compila tailwind.input.css → public/tailwind.css (minificado,
 *      con purge automático usando los templates HTML como source).
 *   2. Terser JS:    minifica cada *.js en frontend/js/ → frontend/js/*.min.js.
 *
 * En producción, los templates sirven los *.min.js (vía js_suffix) y el
 * tailwind.css compilado. En desarrollo se sirven los .js originales y el
 * CSS se puede generar con `npm run build:css` (o usar el CDN temporalmente).
 *
 * Uso:
 *   cd frontend && npm install && npm run build
 */
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const Terser = require("terser");

const ROOT = __dirname;
const JS_DIR = path.join(ROOT, "js");
const PUBLIC_DIR = path.join(ROOT, "public");
const TAILWIND_INPUT = path.join(ROOT, "tailwind.input.css");
const TAILWIND_OUTPUT = path.join(PUBLIC_DIR, "tailwind.css");

// En desarrollo local, main.py (backend/app/main.py) resuelve FRONTEND_PUBLIC
// como backend/frontend/public/. Copiamos ahí también para que el dev local
// sirva el CSS sin necesidad de Docker.
const BACKEND_FRONTEND_PUBLIC = path.join(ROOT, "..", "backend", "frontend", "public");

// ----------------------------------------------------------------
//  Fase 1: Tailwind CSS (compilar + purge + minificar)
// ----------------------------------------------------------------
function buildTailwind() {
  console.log("\n=== Fase 1: Tailwind CSS ===");

  if (!fs.existsSync(TAILWIND_INPUT)) {
    console.warn(`  ⚠ Falta ${TAILWIND_INPUT} — se omite el build de CSS.`);
    console.warn("    (los templates seguirán cargando el CSS existente o el CDN)");
    return;
  }

  // Asegurar que public/ exista (Tailwind no lo crea solo)
  fs.mkdirSync(PUBLIC_DIR, { recursive: true });

  // Invocar el CLI de Tailwind directamente vía node (evita problemas de spawn
  // con .cmd en Windows). Resolvemos el CLI desde node_modules locales.
  const tailwindCli = path.join(ROOT, "node_modules", "tailwindcss", "lib", "cli.js");
  try {
    execFileSync(
      process.execPath, // ruta al binario de node
      [tailwindCli, "-i", TAILWIND_INPUT, "-o", TAILWIND_OUTPUT, "--minify"],
      { cwd: ROOT, stdio: "inherit" }
    );
  } catch (e) {
    console.error("  ✗ Tailwind CSS build fallido:", e.message);
    process.exit(1);
  }

  if (fs.existsSync(TAILWIND_OUTPUT)) {
    const sizeKB = (fs.statSync(TAILWIND_OUTPUT).size / 1024).toFixed(1);
    console.log(`  ✓ tailwind.css generado (${sizeKB} KB) → public/tailwind.css`);

    // Copiar al espejo backend/frontend/public/ para que el servidor de
    // desarrollo local (uvicorn en backend/) pueda servirlo en
    // /static/frontend/tailwind.css sin necesidad de Docker.
    try {
      if (fs.existsSync(BACKEND_FRONTEND_PUBLIC)) {
        fs.copyFileSync(TAILWIND_OUTPUT, path.join(BACKEND_FRONTEND_PUBLIC, "tailwind.css"));
        console.log(`  ✓ copia espejo → backend/frontend/public/tailwind.css`);
      }
    } catch (e) {
      console.warn(`  ⚠ No se pudo copiar al espejo backend/frontend/public/: ${e.message}`);
    }
  } else {
    console.error("  ✗ No se generó public/tailwind.css");
    process.exit(1);
  }
}

// ----------------------------------------------------------------
//  Fase 2: Terser JS (minificar *.js → *.min.js)
// ----------------------------------------------------------------
async function buildJs() {
  console.log("\n=== Fase 2: Terser JS ===");

  if (!fs.existsSync(JS_DIR)) {
    console.error(`Directorio no encontrado: ${JS_DIR}`);
    process.exit(1);
  }

  const files = fs.readdirSync(JS_DIR).filter((f) => f.endsWith(".js") && !f.endsWith(".min.js"));

  if (files.length === 0) {
    console.log("No hay archivos .js para minificar.");
    return;
  }

  console.log(`Minificando ${files.length} archivo(s) JS...`);

  let ok = 0;
  let fail = 0;

  for (const file of files) {
    const inputPath = path.join(JS_DIR, file);
    const outputPath = path.join(JS_DIR, file.replace(/\.js$/, ".min.js"));

    try {
      const code = fs.readFileSync(inputPath, "utf8");
      const result = await Terser.minify(code, {
        compress: {
          drop_console: false, // mantener console.error/log por ahora
          drop_debugger: true,
        },
        mangle: true,
        format: {
          comments: false,
        },
      });

      if (result.error) {
        throw result.error;
      }

      fs.writeFileSync(outputPath, result.code, "utf8");
      const ratio = ((1 - Buffer.byteLength(result.code) / Buffer.byteLength(code)) * 100).toFixed(1);
      console.log(`  ✓ ${file} → ${path.basename(outputPath)} (${ratio}% menor)`);
      ok++;
    } catch (err) {
      console.error(`  ✗ ${file}: ${err.message}`);
      fail++;
    }
  }

  console.log(`\nDone JS: ${ok} OK, ${fail} fallidos.`);
  if (fail > 0) process.exit(1);
}

// ----------------------------------------------------------------
//  Orquestador
// ----------------------------------------------------------------
(async function main() {
  console.log("🔨 Build de assets frontend (Tailwind CSS + Terser JS)\n");
  buildTailwind();
  await buildJs();
  console.log("\n✅ Build completo.");
})();