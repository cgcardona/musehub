/**
 * app.ts — MuseHub frontend entry point.
 *
 * Bundled by esbuild into static/app.js (IIFE format).
 * Each module attaches its public API to `window` for use in
 * Jinja2 templates that call e.g. togglePlay(), saveToken(), etc.
 */

import './musehub.ts';
import './audio-player.ts';
import './piano-roll.ts';
