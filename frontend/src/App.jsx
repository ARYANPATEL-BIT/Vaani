/**
 * Root application component.
 *
 * Mounts the RouterProvider with the application route definitions.
 * Any future top-level context providers (e.g., audio session state,
 * error boundaries) will be composed here around the router.
 */

import { RouterProvider } from 'react-router-dom';
import router from './router.jsx';

export default function App() {
  return <RouterProvider router={router} />;
}
