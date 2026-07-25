import axios from 'axios'

// Relative default so the same production build works from any origin
// (Tailscale hostname, LAN reverse proxy, localhost). Dev overrides via
// VITE_API_URL in .env to hit the uvicorn port directly.
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
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
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
            refresh_token: refresh,
          })
          localStorage.setItem('access_token', data.access_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return apiClient(original)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)
