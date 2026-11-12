/**
 * Application entry point.
 *
 * Renders the root <App /> component into the DOM inside React.StrictMode.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import './theme/colors.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
