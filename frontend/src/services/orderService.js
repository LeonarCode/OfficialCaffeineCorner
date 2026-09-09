import api from '../api'

export const getOrders = () =>
    api.get('/api/orders/')

export const createOrder = (data) =>
    api.post('/api/orders/create/', data)

export const getOrder = (id) =>
    api.get(`/api/orders/${id}/`)

export const getLoyaltyPoints = () =>
    api.get('/api/loyalty/')

export const getZones = () =>
    api.get('/api/zones/')

export const createPayMongoSource = (data) =>
    api.post('/api/paymongo/create-source/', data)

export const verifyPaymongoPayment = (orderId) =>
    api.post('/api/paymongo/verify/', { order_id: orderId })