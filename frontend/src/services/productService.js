import api from '../api'

export const getProducts = (params) =>
    api.get('/api/products/', { params })

export const getCategories = () =>
    api.get('/api/categories/')

export const getProduct = (id) =>
    api.get(`/api/products/${id}/`)

export const getReviews = (productId) =>
    api.get(`/api/products/${productId}/reviews/`)

export const createReview = (productId, data) =>
    api.post(`/api/products/${productId}/reviews/`, data)