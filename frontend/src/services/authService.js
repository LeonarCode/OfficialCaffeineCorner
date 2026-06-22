import api from '../api'

export const sendOTP = (email) =>
    api.post('api/auth/send-otp/', { email })

export const verifyOTP = (email, code) =>
    api.post('api/auth/verify-otp/', { email, code })

export const googleLogin = (accessToken) =>
    api.post('api/auth/google/', { access_token: accessToken })

export const facebookLogin = (accessToken) =>
    api.post('api/auth/facebook/', { access_token: accessToken })

export const getMe = () =>
    api.get('/api/auth/me/')

export const getProfile = () =>
    api.get('/api/auth/profile/')

export const updateProfile = (data) =>
    api.put('/api/auth/profile/', data)