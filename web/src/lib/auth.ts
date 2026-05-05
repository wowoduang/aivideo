import { useCallback, useEffect, useState } from 'react';
import { config } from './config';

const TOKEN_KEY = 'aivideo_token';
const USER_KEY = 'aivideo_user';

export type AuthUser = {
  email: string;
  username?: string;
  name?: string;
  verified?: boolean;
  created_at?: string;
};

export function getStoredToken(): string | null {
  try {
    return typeof window === 'undefined' ? null : localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser(): AuthUser | null {
  try {
    if (typeof window === 'undefined') return null;
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setStoredAuth(token: string, user: AuthUser) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    window.dispatchEvent(new Event('aivideo:auth'));
  } catch {}
}

function withBase(path: string) {
  const base = config.API_BASE_URL || '';
  if (!base) return path;
  return `${base.replace(/\/$/, '')}${path}`;
}

async function notifyLogout(token: string | null) {
  if (!token) return;
  try {
    await fetch(withBase('/api/v1/auth/logout'), {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {}
}

export function clearStoredAuth() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem('aivideo_projects_cache');
    window.dispatchEvent(new Event('aivideo:auth'));
    window.dispatchEvent(new Event('aivideo:projects'));
  } catch {}
}

const AUTH_ERROR_MESSAGES = new Set(['invalid_token', 'missing_token', '登录已失效，请重新登录']);

export function isAuthError(error: unknown): boolean {
  return error instanceof Error && AUTH_ERROR_MESSAGES.has((error.message || '').trim());
}

export function normalizeAuthError(error: unknown): Error {
  if (error instanceof Error && AUTH_ERROR_MESSAGES.has((error.message || '').trim())) {
    return new Error('登录已失效，请重新登录');
  }
  return error instanceof Error ? error : new Error('请求失败');
}

export function handleAuthFailure(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const detail = (error.message || '').trim();
  if (detail !== 'invalid_token' && detail !== 'missing_token') return false;
  clearStoredAuth();
  return true;
}

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [token, setToken] = useState<string | null>(() => getStoredToken());

  useEffect(() => {
    const sync = () => {
      setUser(getStoredUser());
      setToken(getStoredToken());
    };
    window.addEventListener('storage', sync);
    window.addEventListener('aivideo:auth', sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener('aivideo:auth', sync);
    };
  }, []);

  const login = useCallback((nextToken: string, nextUser: AuthUser) => {
    setStoredAuth(nextToken, nextUser);
    setToken(nextToken);
    setUser(nextUser);
  }, []);

  const logout = useCallback(async () => {
    await notifyLogout(getStoredToken());
    clearStoredAuth();
    setToken(null);
    setUser(null);
  }, []);

  return { user, token, isAuthenticated: Boolean(token), login, logout };
}
