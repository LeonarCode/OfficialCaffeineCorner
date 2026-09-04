import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getRiderOrders, markOrderDelivered } from '../../services/riderService.js'

const RiderOrderDetail = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [photo, setPhoto] = useState(null)
  const [photoPreview, setPhotoPreview] = useState(null)
  const [paymentReceived, setPaymentReceived] = useState(false)
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)

  useEffect(() => {
    fetchOrder()
  }, [id])

  const fetchOrder = async () => {
    setLoading(true)
    try {
      const res = await getRiderOrders()
      const found = res.data.find(o => o.id === parseInt(id))
      setOrder(found)
    } catch (err) {
      console.error(err)
    } finally { setLoading(false) }
  }

  const handlePhotoSelect = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setPhoto(file)
    setPhotoPreview(URL.createObjectURL(file))
  }

  const handleSubmit = async () => {
    if (!photo) { setError('Please take a photo as proof of delivery.'); return }
    setSubmitting(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('delivery_proof_photo', photo)
      formData.append('payment_received', paymentReceived)
      formData.append('rider_notes', notes)
      await markOrderDelivered(id, formData)
      navigate('/rider/dashboard')
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to mark as delivered.')
    } finally { setSubmitting(false) }
  }

  if (loading) return (
    <div className='min-h-screen bg-[#FAF6F0] flex items-center justify-center'>
      <div className='w-8 h-8 border-2 border-[#3D1F00] border-t-transparent rounded-full animate-spin' />
    </div>
  )

  if (!order) return (
    <div className='min-h-screen bg-[#FAF6F0] flex flex-col items-center justify-center gap-3'>
      <p className='text-gray-400 text-sm'>Order not found.</p>
      <button onClick={() => navigate('/rider/dashboard')} className='text-[#6f4e37] text-sm font-semibold'>← Back</button>
    </div>
  )

  return (
    <div className='min-h-screen bg-[#FAF6F0] pb-6'>

      {/* Header */}
      <div className='bg-[#2C1503] px-5 py-5 flex items-center gap-3 sticky top-0 z-10'>
        <button onClick={() => navigate('/rider/dashboard')} className='text-white text-lg'>←</button>
        <div>
          <p className='text-white font-bold text-sm'>#CC-{String(order.id).padStart(5, '0')}</p>
          <p className='text-[#C4A882]/50 text-xs'>{order.order_type === 'bulk' ? 'Bulk/Catering' : 'Regular'} Order</p>
        </div>
      </div>

      <div className='px-4 py-4 flex flex-col gap-4'>

        {/* Customer Info */}
        <div className='bg-white rounded-2xl p-4 shadow-sm'>
          <p className='text-[#2C1503] font-semibold text-sm mb-3'>Customer Info</p>
          <div className='flex flex-col gap-2 text-sm'>
            <div className='flex items-start gap-2'>
              <span className='text-gray-400 shrink-0'>📍</span>
              <span className='text-[#2C1503]'>{order.address}</span>
            </div>
            <a href={`tel:${order.phone}`} className='flex items-center gap-2 text-[#6f4e37] font-semibold'>
              📞 {order.phone}
            </a>
            {order.notes && (
              <div className='flex items-start gap-2 bg-amber-50 rounded-xl p-2 mt-1'>
                <span>📝</span>
                <span className='text-amber-700 text-xs'>{order.notes}</span>
              </div>
            )}
          </div>
        </div>

        {/* Order Items */}
        <div className='bg-white rounded-2xl p-4 shadow-sm'>
          <p className='text-[#2C1503] font-semibold text-sm mb-3'>Items</p>
          {order.items.map(item => (
            <div key={item.id} className='flex justify-between text-sm py-1.5 border-b border-gray-50 last:border-0'>
              <span className='text-gray-600'>{item.product_name} ×{item.quantity}</span>
              <span className='text-[#2C1503] font-semibold'>₱{parseFloat(item.subtotal).toFixed(2)}</span>
            </div>
          ))}
          <div className='flex justify-between text-sm pt-2 mt-2 border-t border-gray-100'>
            <span className='font-bold text-[#2C1503]'>Total</span>
            <span className='font-bold text-[#2C1503]'>₱{parseFloat(order.total_price).toFixed(2)}</span>
          </div>
          <div className='flex items-center gap-2 mt-2'>
            <span className='text-xs bg-gray-100 px-2 py-0.5 rounded-full'>
              {order.payment_method === 'cod' ? '🏦 COD' : '📱 GCash'}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${order.payment_status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
              {order.payment_status}
            </span>
          </div>
        </div>

        {/* Proof of Delivery */}
        <div className='bg-white rounded-2xl p-4 shadow-sm'>
          <p className='text-[#2C1503] font-semibold text-sm mb-3'>Proof of Delivery</p>

          <input
            type='file'
            accept='image/*'
            capture='environment'
            ref={fileInputRef}
            onChange={handlePhotoSelect}
            className='hidden'
          />

          {photoPreview ? (
            <div className='relative mb-3'>
              <img src={photoPreview} alt='Proof' className='w-full h-48 object-cover rounded-xl' />
              <button
                onClick={() => fileInputRef.current?.click()}
                className='absolute bottom-2 right-2 bg-black/60 text-white text-xs px-3 py-1.5 rounded-full'
              >
                Retake
              </button>
            </div>
          ) : (
            <button
              onClick={() => fileInputRef.current?.click()}
              className='w-full h-40 border-2 border-dashed border-gray-300 rounded-xl flex flex-col items-center justify-center gap-2 text-gray-400 mb-3'
            >
              <span className='text-3xl'>📷</span>
              <span className='text-sm font-semibold'>Take Photo</span>
            </button>
          )}

          {/* Payment Confirmation */}
          <label className='flex items-center justify-between bg-[#FAF6F0] rounded-xl p-3 mb-3 cursor-pointer'>
            <div className='flex items-center gap-2'>
              <span className='text-lg'>💰</span>
              <div>
                <p className='text-[#2C1503] text-sm font-semibold'>Payment Received</p>
                <p className='text-gray-400 text-xs'>Check kung nabayaran na ang order</p>
              </div>
            </div>
            <input
              type='checkbox'
              checked={paymentReceived}
              onChange={e => setPaymentReceived(e.target.checked)}
              className='w-5 h-5 accent-[#3D1F00]'
            />
          </label>

          {/* Notes */}
          <textarea
            placeholder='Delivery notes (optional)'
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={2}
            className='w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[#C4A882] resize-none'
          />

          {error && <p className='text-red-500 text-xs mt-2'>{error}</p>}

          <button
            onClick={handleSubmit}
            disabled={submitting || !photo}
            className='w-full bg-[#2C1503] hover:bg-[#5a2f00] disabled:opacity-50 text-white font-bold text-sm py-3.5 rounded-xl mt-4 transition'
          >
            {submitting ? 'Submitting...' : '✓ Mark as Delivered'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default RiderOrderDetail