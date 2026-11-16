/**
 * levelHistory.js -- the tape's memory: one loudness sample per bar, for
 * both tracks, kept in a fixed-size ring buffer.
 *
 * A ring buffer is an array of fixed length plus a "next slot" index. When
 * the array is full, the next sample overwrites the oldest one, so memory
 * never grows and nothing is ever shifted or re-allocated, which matters
 * for code that runs 60 times a second.
 *
 * Pure (typed arrays only): node tests it (levelHistory.test.js).
 */

export function createLevelHistory(capacity) {
  const times = new Float64Array(capacity); // session seconds of each sample
  const vaani = new Float32Array(capacity); // playback loudness, 0..1
  const you = new Float32Array(capacity);   // mic loudness, 0..1
  let next = 0;  // the slot the next sample goes into
  let size = 0;  // how many slots hold real samples (<= capacity)

  return {
    push(t, vaaniLevel, youLevel) {
      times[next] = t;
      vaani[next] = vaaniLevel;
      you[next] = youLevel;
      next = (next + 1) % capacity;
      size = Math.min(size + 1, capacity);
    },
    /** Calls fn(t, vaani, you) for every sample, oldest first. */
    forEach(fn) {
      const first = (next - size + capacity) % capacity;
      for (let k = 0; k < size; k++) {
        const i = (first + k) % capacity;
        fn(times[i], vaani[i], you[i]);
      }
    },
    clear() {
      next = 0;
      size = 0;
    },
    get size() {
      return size;
    },
  };
}
