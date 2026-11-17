/**
 * useIstClock -- the time in India as "hh:mm", for the "On air" header and
 * the footer. Re-reads the clock every CLOCK.everyMs (landingContent.js).
 */

import { useEffect, useState } from 'react';
import { CLOCK } from './landingContent.js';

function readClock() {
  return new Date().toLocaleTimeString('en-GB', {
    timeZone: CLOCK.timeZone,
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function useIstClock() {
  const [time, setTime] = useState(readClock);
  useEffect(() => {
    const id = setInterval(() => setTime(readClock()), CLOCK.everyMs);
    return () => clearInterval(id); // cleanup: no timer outlives the page
  }, []);
  return time;
}
