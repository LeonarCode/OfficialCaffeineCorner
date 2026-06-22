import api from '../api'

export const getCart = () =>
    api.get('/api/cart/')

export const addToCart = (data) =>
    api.post('/api/cart/add/', data)

export const updateCart = (id, quantity) =>
    api.patch(`/api/cart/${id}/update/`, { quantity })

export const deleteFromCart = (id) =>
    api.delete(`/api/cart/${id}/delete/`)