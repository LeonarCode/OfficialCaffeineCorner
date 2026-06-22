import axios from 'axios'
import { jwtDecode } from 'jwt-decode'

export const BASE_URL = 'http://localhost:8000'

const api = axios.create({
    baseURL: BASE_URL
})

// ─── Helpers ──────────────────────────────────────────────
const isTokenExpired = (token) => {
    try {
        const decoded = jwtDecode(token)
        return decoded.exp * 1000 < Date.now()
    } catch {
        return true
    }
}

const clearTokens = () => {
    localStorage.removeItem('access')
    localStorage.removeItem('refresh')
}

const refreshAccessToken = async () => {
    const refresh = localStorage.getItem('refresh')
    if (!refresh || isTokenExpired(refresh)) {
        clearTokens()
        return null
    }
    try {
        const res = await axios.post(`${BASE_URL}/api/auth/token/refresh/`, { refresh })
        const newAccess = res.data.access
        localStorage.setItem('access', newAccess)
        return newAccess
    } catch {
        clearTokens()
        return null
    }
}

// ─── Request Interceptor ──────────────────────────────────
api.interceptors.request.use(async (config) => {
    let token = localStorage.getItem('access')

    if (token && isTokenExpired(token)) {
        // Try to refresh
        token = await refreshAccessToken()
        if (!token) {
            // Refresh failed — redirect to signin
            window.location.href = '/signin'
            return Promise.reject(new Error('Session expired'))
        }
    }

    if (token) {
        config.headers.Authorization = `Bearer ${token}`
    }

    return config
})

// ─── Response Interceptor ─────────────────────────────────
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config

        // If 401 and not already retried
        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true

            const newToken = await refreshAccessToken()
            if (newToken) {
                originalRequest.headers.Authorization = `Bearer ${newToken}`
                return api(originalRequest)  // retry original request
            } else {
                clearTokens()
                window.location.href = '/signin'
            }
        }

        return Promise.reject(error)
    }
)

export default api