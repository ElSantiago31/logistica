/**
 * build.js — Pipeline de minificación de assets JS.
 *
 * Recorre todos los *.js en frontend/js/, los minifica con Terser (renombrando
 * variables locales, eliminando comentarios y espacios) y escribe el resultado
 * en frontend/js/*.min.js.
 *
 * En producción, los templates sirven los *.min.js (vía la variable js_suffix).
 * En desarrollo, los templates sirven los *.js originales (legibles para debug).
 *
 * Uso:
 *   cd frontend && npm install && npm run build
 */
const fs = require("fs");
const path = require("path");
const Terser = require("terser");

const JS_DIR = path.join(__dirname, "js");

async function build() {
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

  console.log(`\nDone: ${ok} OK, ${fail} fallidos.`);
  if (fail > 0) process.exit(1);
}

build();