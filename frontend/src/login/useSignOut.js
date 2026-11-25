/**
 * useSignOut -- the "Sign out" action, used by the /talk rail (RailNav.jsx)
 * and the phone settings sheet (StudioHeader.jsx).
 *
 * POST /auth/logout makes the server answer with a Set-Cookie that deletes
 * vaani_session (the page cannot delete an httpOnly cookie itself). Then
 * /login. Leaving /talk unmounts the Studio page, and its hooks' own cleanup
 * closes the mic and the WebSocket.
 *
 * If the logout request gets no answer, we still go to /login: the cookie
 * may survive, and /login will then send the visitor straight back in.
 */

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { logout } from '../api/authApi.js';

export default function useSignOut() {
  const navigate = useNavigate();
  return useCallback(async () => {
    await logout();
    navigate('/login', { replace: true });
  }, [navigate]);
}
