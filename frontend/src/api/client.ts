import axios from 'axios'

// Relative default so the same production build works from any origin
// (Tailscale hostname, LAN reverse proxy, localhost). Dev overrides via
// VITE_API_URL in .env to hit the uvicorn port directly.
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

// No default Content-Type — axios derives it from the body: plain objects go
// out as application/json, FormData as multipart with a browser-set boundary.
// A forced JSON default here makes axios serialize FormData *as JSON* (the
// File becomes "{}"), so every upload site had to override it per-call — and
// the one that forgot (snapshots) shipped broken. client.contentType.test.ts
// pins both behaviours.
export const apiClient = axios.create({
  baseURL: BASE_URL,
})

// Attach access token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Auto-refresh on 401; broadcast network reachability for OfflineBanner
apiClient.interceptors.response.use(
  (res) => {
    window.dispatchEvent(new Event('igab:network-ok'))
    return res
  },
  async (error) => {
    if (error.code === 'ERR_NETWORK') {
      window.dispatchEvent(new Event('igab:network-error'))
    } else if (error.response) {
      // Server responded (even with an error status) — it's reachable
      window.dispatchEvent(new Event('igab:network-ok'))
    }
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        const token = await refreshAccessToken()
        if (token) {
          original.headers.Authorization = `Bearer ${token}`
          return apiClient(original)
        }
      }
    }
    return Promise.reject(error)
  }
)

/**
 * Swap the refresh token for a new access token, or sign out.
 *
 * Extracted from the 401 interceptor because the chat stream needs it too:
 * that call goes out through `fetch` rather than axios (axios cannot read a
 * stream), so without this there would be two answers to "how do we
 * authenticate" and only one of them would recover from an expired token.
 *
 * Returns the new token, or null when the session is over — in which case it
 * has already cleared storage and sent the browser to /login.
 */
export async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem('refresh_token')
  if (!refresh) return null
  try {
    const { data } = await axios.post(`${BASE_URL}/auth/refresh`, { refresh_token: refresh })
    localStorage.setItem('access_token', data.access_token)
    return data.access_token as string
  } catch {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
    return null
  }
}

/** The base URL every request goes to, for callers that bypass axios. */
export const API_BASE_URL = BASE_URL

/**
 * Human-readable message from an API error.
 *
 * FastAPI's `detail` is usually a string, but an endpoint that needs to hand
 * the client structured data alongside the message (the duplicate-receipt 409
 * returns the existing transaction id) sends an object instead. Reading
 * `detail` blindly then renders "[object Object]" at the user. Every call site
 * used to do its own unchecked cast; this is the one place that has to know.
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message) return message
  }
  return fallback
}
