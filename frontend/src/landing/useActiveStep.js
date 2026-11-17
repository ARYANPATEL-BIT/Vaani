/**
 * useActiveStep -- which of the story steps is "active": the one crossing
 * the middle of the screen.
 *
 * An IntersectionObserver asks the browser to tell us when an element
 * enters or leaves an area, without us measuring anything on scroll. The
 * area here is the viewport shrunk by `margin` (e.g. -45% top and bottom),
 * which leaves a thin band across the middle. Whichever step is inside
 * that band becomes active.
 *
 * Returns [active, refFor]: refFor(i) is the ref callback for step i.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export default function useActiveStep(margin) {
  const els = useRef([]);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) setActive(els.current.indexOf(e.target));
      }
    }, { rootMargin: margin });
    els.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect(); // cleanup: stop watching when the page goes
  }, [margin]);

  // React calls a ref callback with the element when it appears.
  const refFor = useCallback((i) => (el) => { els.current[i] = el; }, []);
  return [active, refFor];
}
