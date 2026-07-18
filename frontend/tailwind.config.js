/** @type {import('tailwindcss').Config} */
/**
 * tailwind.config.js — Configuración ÚNICA de Tailwind para el proyecto.
 *
 * Reemplaza los ~13 bloques `tailwind.config = {...}` duplicados en los
 * templates que usaban el CDN (cdn.tailwindcss.com).
 *
 * Paleta `primary`: marrones/dorados de A&C Eventos (extraída de base.html).
 * Paleta `brand`:   alias corto del color principal (#cf9b62).
 *
 * `content`: rutas donde Tailwind busca clases para el purge (JIT).
 *   - En LOCAL:  ../backend/app/templates/**   (relativo a frontend/)
 *   - En DOCKER: ./templates/**                (copiados al Stage 1 del build)
 * Los paths inexistentes se ignoran silenciosamente, así que listar ambos
 * es seguro para los dos entornos.
 */
module.exports = {
  content: [
    './js/**/*.js',
    './templates/**/*.html',
    '../backend/app/templates/**/*.html',
  ],
  // Safelist: clases construidas dinámicamente vía objetos JS (no detectables
  // por purge porque se "ensamblan" en runtime). Las listamos explícitamente
  // para garantizar que lleguen al CSS final.
  safelist: [
    // Badges de estado (eventos, asignaciones, check-in, nómina)
    'bg-gray-100', 'bg-yellow-100', 'bg-blue-100', 'bg-green-100',
    'bg-red-100', 'bg-orange-100', 'bg-purple-100', 'bg-pink-100',
    'text-gray-700', 'text-yellow-700', 'text-blue-700', 'text-green-700',
    'text-red-700', 'text-orange-700', 'text-purple-700', 'text-pink-700',
    // Barras de progreso
    'bg-green-500', 'bg-yellow-500', 'bg-red-500', 'bg-blue-500', 'bg-gray-500',
    // Toasts (notificaciones)
    'bg-gray-700', 'bg-gray-800',
    // Bordes de tarjetas de roles (dashboard admin)
    'border-blue-500', 'border-green-500', 'border-yellow-500',
    'border-red-500', 'border-purple-500', 'border-gray-500', 'border-orange-500',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#fff2e4',
          100: '#ffebd6',
          200: '#f8d9b6',
          300: '#e3be95',
          400: '#d5aa7b',
          500: '#cf9b62',
          600: '#b48450',
          700: '#976e41',
          800: '#785631',
          900: '#5d4224',
        },
        brand: '#cf9b62',
      },
    },
  },
  // Plugins: ninguno por ahora. El CDN no usaba plugins, así que los estilos
  // base (Preflight) y utilidades son suficientes.
  plugins: [],
};