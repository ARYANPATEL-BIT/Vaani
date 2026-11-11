/**
 * NotFoundPage — shown when the URL does not match any defined route.
 *
 * Provides a clear message and a link back to the main conversation page.
 */

import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div style={{ textAlign: 'center', padding: '48px 24px' }}>
      <h1>404</h1>
      <p>This page does not exist.</p>
      <Link to="/" style={{ color: 'var(--accent)', marginTop: '16px', display: 'inline-block' }}>
        Back to Vaani
      </Link>
    </div>
  );
}
