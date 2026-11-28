/**
 * Centralized API configuration for AI Trading Analyzer frontend.
 * - Production (Vercel / built bundle): uses VITE_API_URL, defaulting to the live Render backend.
 * - Local development (`npm run dev`): uses VITE_API_URL if set, otherwise relative `/api` via Vite proxy.
 */

export const RENDER_BACKEND_URL = 'https://analyzer-adts.onrender.com'

const envApiUrl = (import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || '').trim()

export const API_BASE_URL = (
  envApiUrl || (import.meta.env.PROD ? RENDER_BACKEND_URL : '')
).replace(/\/+$/, '')

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}

export function getWebSocketUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  if (API_BASE_URL) {
    const wsBase = API_BASE_URL.replace(/^https:/i, 'wss:').replace(/^http:/i, 'ws:')
    return `${wsBase}${normalizedPath}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${normalizedPath}`
}
