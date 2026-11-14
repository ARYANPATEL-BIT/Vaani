/**
 * canvasSize.js -- match a canvas's pixel grid to its on-screen size.
 *
 * A canvas has two sizes: how big it looks (CSS pixels, set by the page
 * layout) and how many pixels it actually holds (canvas.width/height). On a
 * "retina" screen one CSS pixel is 2 or 3 real pixels (devicePixelRatio), so
 * a canvas the same size in both looks blurry. We give it more pixels, but
 * cap the ratio: 3x on a phone means 9x the pixels to paint every frame for
 * a glow that is soft anyway.
 *
 * Used by HeroWave.jsx and Preloader.jsx.
 */

// Returns the 2D context, already scaled so drawing code can use CSS pixels,
// plus the CSS width and height. Returns null if the canvas has no size yet
// (not laid out, or hidden), so the caller skips this frame.
export function fitCanvas(canvas, maxDpr, maxPx = Infinity) {
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (!w || !h) return null;
  // The cap: the screen's ratio, but at most maxDpr, and never more than
  // maxPx real pixels across (a 4K-wide window would otherwise be huge).
  const dpr = Math.min(window.devicePixelRatio || 1, maxDpr, maxPx / w);
  const pw = Math.round(w * dpr);
  const ph = Math.round(h * dpr);
  // Setting width/height clears the canvas and reallocates its memory, so
  // only do it when the size really changed (on resize), not every frame.
  if (canvas.width !== pw || canvas.height !== ph) {
    canvas.width = pw;
    canvas.height = ph;
  }
  const g = canvas.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0); // 1 unit in drawing code = 1 CSS px
  return { g, w, h };
}
