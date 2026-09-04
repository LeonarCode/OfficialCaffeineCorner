import api from '../api'

export const getRiderOrders        = () => api.get('/api/rider/orders/')
export const getRiderHistory       = () => api.get('/api/rider/orders/history/')
export const getRiderStats         = () => api.get('/api/rider/stats/')
export const markOrderDelivered    = (orderId, formData) =>
    api.post(`/api/rider/orders/${orderId}/deliver/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    })