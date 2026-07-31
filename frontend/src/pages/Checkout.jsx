import React, { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { createOrder, getLoyaltyPoints } from '../services/orderService.js'
import { getCart } from '../services/cartService.js'
import { getMe } from '../services/authService.js'
import { getZones } from '../services/orderService.js'
import { useAuth } from '../context/AuthContext'

const STEPS = ['Order Type', 'Delivery', 'Payment']
const GLOBAL_MIN_ORDER = 1000

const Checkout = () => {
  const [cartItems,      setCartItems]      = useState([])
  const [quantity,       setQuantity]       = useState(1)
  const [paymentMethod,  setPaymentMethod]  = useState('cod')
  const [loading,        setLoading]        = useState(false)
  const [fetching,       setFetching]       = useState(true)
  const [showSuccess,    setShowSuccess]    = useState(false)
  const [orderData,      setOrderData]      = useState(null)
  const [orderType,      setOrderType]      = useState('regular')
  const [eventDate,      setEventDate]      = useState('')
  const [pax,            setPax]            = useState('')
  const [loyalty,        setLoyalty]        = useState(null)
  const [pointsToUse,    setPointsToUse]    = useState(0)
  const [usePoints,      setUsePoints]      = useState(false)
  const [showSummary,    setShowSummary]    = useState(false)
  const [errors,         setErrors]         = useState({})
  const [currentStep,    setCurrentStep]    = useState(0)
  const [zones,          setZones]          = useState([])
  const [selectedZone,   setSelectedZone]   = useState(null)
  const [loadingZones,   setLoadingZones]   = useState(false)
  const { isAuthenticated }                 = useAuth()
  const [form, setForm] = useState({ email: '', address: '', notes: '' })

  const location   = useLocation()
  const navigate   = useNavigate()
  const buyNowData = location.state

  useEffect(() => {
    const init = async () => {
      try {
        const res = await getMe()
        setForm(prev => ({ ...prev, email: res.data.email }))
      } catch {}

      try {
        const res = await getLoyaltyPoints()
        setLoyalty(res.data)
      } catch {}

      setLoadingZones(true)
      try {
        const res = await getZones()
        setZones(res.data)
      } catch (err) {
        console.error('Failed to fetch zones', err)
      } finally {
        setLoadingZones(false)
      }

      if (buyNowData?.product) {
        setFetching(false)
      } else {
        fetchCart()
      }
    }
    init()
  }, [])

  const fetchCart = async () => {
    setFetching(true)
    try {
      const res = await getCart()
      setCartItems(res.data)
    } catch {}
    finally { setFetching(false) }
  }

  const subtotal = buyNowData?.product
    ? buyNowData.price * quantity
    : cartItems.reduce((sum, item) => sum + parseFloat(item.product_price) * item.quantity, 0)

  const deliveryFee    = selectedZone ? parseFloat(selectedZone.delivery_fee) : 0
  const pointsDiscount = usePoints && loyalty ? Math.min(pointsToUse * 0.1, subtotal) : 0
  const downpayment    = orderType === 'bulk' ? (subtotal + deliveryFee - pointsDiscount) * 0.5 : 0
  const total          = subtotal + deliveryFee - pointsDiscount
  const belowMinOrder  = subtotal < GLOBAL_MIN_ORDER
  const amountToMin    = GLOBAL_MIN_ORDER - subtotal

  const validate = () => {
    const e = {}
    if (!form.email)   e.email   = 'Email is required'
    if (!form.address) e.address = 'Delivery address is required'
    if (orderType === 'bulk' && !eventDate) e.eventDate = 'Event date is required'
    if (!selectedZone) e.zone = 'Please select your delivery zone'

    if (belowMinOrder) {
      e.minOrder = `Minimum order amount is ₱${GLOBAL_MIN_ORDER.toFixed(2)}. Add ₱${amountToMin.toFixed(2)} more.`
    } else if (selectedZone && subtotal < selectedZone.min_order_amount) {
      e.zone = `Minimum order for ${selectedZone.name} is ₱${parseFloat(selectedZone.min_order_amount).toFixed(2)}`
    }

    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    setLoading(true)
    try {
      const data = {
        email:          form.email,
        address:        form.address,
        notes:          form.notes,
        payment_method: paymentMethod,
        order_type:     orderType,
        event_date:     orderType === 'bulk' ? eventDate : null,
        pax:            orderType === 'bulk' ? parseInt(pax) || 0 : 0,
        points_to_use:  usePoints ? pointsToUse : 0,
        zone_id:        selectedZone?.id || null,
        items: buyNowData?.product
          ? [{ product: buyNowData.product, quantity }]
          : cartItems.map(item => ({
              product:  item.product,
              variant:  item.variant || null,
              quantity: item.quantity,
            })),
      }
      const res = await createOrder(data)
      setOrderData(res.data)
      setShowSuccess(true)
    } catch (err) {
      setErrors(prev => ({ ...prev, submit: err.response?.data?.error || 'Failed to place order.' }))
      console.error('Failed to place order', err)
    } finally {
      setLoading(false)
    }
  }

  const isFormValid = form.email && form.address && selectedZone &&
    (orderType !== 'bulk' || eventDate) &&
    !belowMinOrder &&
    subtotal >= (selectedZone?.min_order_amount || 0)

  return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0]'>

      {/* Success Modal */}
      {showSuccess && orderData && (
        <div className='fixed inset-0 z-50 flex items-center justify-center p-4'>
          <div className='absolute inset-0 bg-black/50 backdrop-blur-sm' style={{ animation: 'fadeIn 0.3s ease' }} />
          <div className='relative bg-white rounded-3xl w-full max-w-sm overflow-hidden shadow-2xl' style={{ animation: 'slideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)' }}>
            <div className='bg-[#2C1503] px-6 pt-8 pb-6 flex flex-col items-center'>
              <div className='w-16 h-16 rounded-full border-2 border-[#C4A882] flex items-center justify-center mb-4' style={{ animation: 'popIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 0.2s both' }}>
                <svg className='w-8 h-8 text-[#C4A882]' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2.5}>
                  <path strokeLinecap='round' strokeLinejoin='round' d='M5 13l4 4L19 7' />
                </svg>
              </div>
              <h2 className='text-white text-2xl font-bold'>
                Order <em className='text-[#C4A882] italic font-serif'>Placed!</em>
              </h2>
              <p className='text-[#C4A882]/60 text-xs tracking-widest uppercase mt-1'>
                {orderType === 'bulk' ? 'Bulk order received →' : "We're preparing your order →"}
              </p>
            </div>
            <div className='px-6 py-5 flex flex-col gap-3'>
              <div className='flex justify-between items-center'>
                <span className='text-gray-400 text-xs'>Order ID</span>
                <span className='text-[#2C1503] text-xs font-bold'>#CC-{String(orderData.id).padStart(5, '0')}</span>
              </div>
              <div className='flex justify-between items-center'>
                <span className='text-gray-400 text-xs'>Type</span>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${orderType === 'bulk' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'}`}>
                  {orderType === 'bulk' ? '🍽️ Bulk / Catering' : '📦 Regular'}
                </span>
              </div>
              {selectedZone && (
                <div className='flex justify-between items-center'>
                  <span className='text-gray-400 text-xs'>Zone</span>
                  <span className='text-[#2C1503] text-xs font-semibold'>{selectedZone.name}</span>
                </div>
              )}
              <div className='flex justify-between items-center'>
                <span className='text-gray-400 text-xs'>Payment</span>
                <span className='text-[#2C1503] text-xs font-semibold'>
                  {paymentMethod === 'cod' ? '🏦 Cash on Delivery' : '📱 GCash'}
                </span>
              </div>
              <hr className='border-gray-100' />
              <div className='flex justify-between items-center'>
                <span className='text-gray-400 text-xs'>Subtotal</span>
                <span className='text-[#2C1503] text-xs font-semibold'>₱{subtotal.toFixed(2)}</span>
              </div>
              {deliveryFee > 0 && (
                <div className='flex justify-between items-center'>
                  <span className='text-gray-400 text-xs'>Delivery Fee</span>
                  <span className='text-[#2C1503] text-xs font-semibold'>₱{deliveryFee.toFixed(2)}</span>
                </div>
              )}
              {pointsDiscount > 0 && (
                <div className='flex justify-between items-center'>
                  <span className='text-green-600 text-xs'>Points Discount</span>
                  <span className='text-green-600 text-xs font-bold'>-₱{pointsDiscount.toFixed(2)}</span>
                </div>
              )}
              {orderType === 'bulk' && (
                <>
                  <div className='flex justify-between items-center'>
                    <span className='text-amber-600 text-xs font-semibold'>Downpayment (50%)</span>
                    <span className='text-amber-600 text-sm font-bold'>₱{downpayment.toFixed(2)}</span>
                  </div>
                  <div className='flex justify-between items-center'>
                    <span className='text-gray-400 text-xs'>Remaining Balance</span>
                    <span className='text-[#2C1503] text-xs font-semibold'>₱{downpayment.toFixed(2)}</span>
                  </div>
                </>
              )}
              <div className='flex justify-between items-center'>
                <span className='text-gray-500 text-sm font-semibold'>Total</span>
                <span className='text-[#2C1503] text-xl font-bold'>₱{total.toFixed(2)}</span>
              </div>
              {orderType === 'bulk' && (
                <div className='bg-amber-50 border border-amber-200 rounded-xl px-3 py-2'>
                  <p className='text-amber-700 text-xs font-semibold'>⚠️ Please pay the 50% downpayment to confirm your bulk order.</p>
                </div>
              )}
              <div className='flex items-center gap-2 bg-green-50 rounded-xl px-3 py-2'>
                <span className='w-2 h-2 rounded-full bg-green-400 shrink-0' />
                <p className='text-green-600 text-xs'>Confirmation sent to {form.email}</p>
              </div>
            </div>
            <div className='px-6 pb-6 flex flex-col gap-2'>
              <button onClick={() => navigate('/orders')} className='w-full bg-[#2C1503] hover:bg-[#5a2f00] text-white font-bold text-sm py-3 rounded-xl transition'>
                → TRACK MY ORDER
              </button>
              <button onClick={() => navigate('/home')} className='w-full border border-gray-200 text-gray-500 font-semibold text-sm py-3 rounded-xl hover:bg-gray-50 transition'>
                CONTINUE SHOPPING
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes fadeIn  { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(40px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }
        @keyframes popIn   { from { opacity: 0; transform: scale(0); } to { opacity: 1; transform: scale(1); } }
      `}</style>

      {/* Header Banner */}
      <div className='bg-[#3D1F00] px-6 sm:px-20 py-8'>
        <div className='flex items-center gap-2 text-[#C4A882]/60 text-xs font-semibold tracking-widest uppercase mb-3'>
          <Link to='/home' className='hover:text-[#C4A882] transition'>Home</Link>
          <span>›</span>
          <span className='text-[#C4A882]'>Checkout</span>
        </div>
        <h1 className='text-white text-3xl font-bold'>
          Complete Your <em className='text-[#C4A882] italic font-serif'>Order</em>
        </h1>
        {form.email && <p className='text-[#C4A882]/50 text-xs mt-1'>Ordering as {form.email}</p>}

        {/* Step Indicator */}
        <div className='flex items-center gap-2 mt-5'>
          {STEPS.map((step, i) => (
            <React.Fragment key={step}>
              <div className='flex items-center gap-1.5'>
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition
                  ${i <= currentStep ? 'bg-[#C4A882] text-[#2C1503]' : 'bg-white/20 text-white/40'}`}>
                  {i < currentStep ? '✓' : i + 1}
                </div>
                <span className={`text-xs font-semibold transition ${i <= currentStep ? 'text-[#C4A882]' : 'text-white/40'}`}>
                  {step}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`flex-1 h-px transition ${i < currentStep ? 'bg-[#C4A882]/60' : 'bg-white/20'}`} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className='flex flex-col lg:flex-row gap-6 px-4 sm:px-16 py-10 max-w-6xl mx-auto w-full'>

        {/* Left Column */}
        <div className='flex flex-col gap-5 flex-1'>

          {/* Step 1 — Order Type */}
          <div className='bg-white rounded-2xl overflow-hidden shadow-sm'>
            <button
              className='w-full flex items-center justify-between p-5'
              onClick={() => setCurrentStep(currentStep === 0 ? -1 : 0)}
            >
              <div className='flex items-center gap-3'>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition
                  ${currentStep >= 0 ? 'bg-[#3D1F00] text-[#C4A882]' : 'bg-gray-100 text-gray-400'}`}>
                  1
                </div>
                <h2 className='text-[#2C1503] font-semibold text-sm'>Order Type</h2>
                {orderType === 'bulk' && (
                  <span className='text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-semibold'>Bulk</span>
                )}
              </div>
              <span className='text-gray-400 text-sm'>{currentStep === 0 ? '↑' : '↓'}</span>
            </button>

            {currentStep === 0 && (
              <div className='px-5 pb-5'>
                <div className='flex gap-3 mb-3'>
                  <label className={`flex items-center gap-3 border rounded-xl px-4 py-3 cursor-pointer transition flex-1 ${orderType === 'regular' ? 'border-[#C4A882] bg-[#FAF6F0]' : 'border-gray-200'}`}>
                    <input type='radio' name='orderType' value='regular' checked={orderType === 'regular'} onChange={() => setOrderType('regular')} className='accent-[#3D1F00]' />
                    <div>
                      <p className='text-[#2C1503] text-sm font-semibold'>📦 Regular Order</p>
                      <p className='text-gray-400 text-xs'>Standard delivery order</p>
                    </div>
                  </label>
                  <label className={`flex items-center gap-3 border rounded-xl px-4 py-3 cursor-pointer transition flex-1 ${orderType === 'bulk' ? 'border-[#C4A882] bg-[#FAF6F0]' : 'border-gray-200'}`}>
                    <input type='radio' name='orderType' value='bulk' checked={orderType === 'bulk'} onChange={() => setOrderType('bulk')} className='accent-[#3D1F00]' />
                    <div>
                      <p className='text-[#2C1503] text-sm font-semibold'>🍽️ Bulk / Catering</p>
                      <p className='text-gray-400 text-xs'>50% downpayment required</p>
                    </div>
                  </label>
                </div>

                {/* Min order note — applies to both regular and bulk */}
                <p className='text-gray-400 text-[11px] mb-3'>
                  ℹ️ Minimum order amount is <span className='font-semibold text-[#6f4e37]'>₱{GLOBAL_MIN_ORDER.toFixed(2)}</span> for delivery orders.
                </p>

                {orderType === 'bulk' && (
                  <div className='flex flex-col gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4'>
                    <p className='text-amber-700 text-xs font-semibold'>⚠️ Bulk orders require 50% downpayment. Remaining balance upon delivery.</p>
                    <div>
                      <label className='text-[#2C1503] text-xs font-semibold uppercase mb-1.5 block'>
                        Event Date <span className='text-red-400'>*</span>
                      </label>
                      <input
                        type='date'
                        value={eventDate}
                        onChange={e => { setEventDate(e.target.value); setErrors(prev => ({ ...prev, eventDate: '' })) }}
                        className={`w-full border rounded-xl px-4 py-3 text-sm outline-none transition bg-white
                          ${errors.eventDate ? 'border-red-400' : 'border-gray-200 focus:border-[#C4A882]'}`}
                      />
                      {errors.eventDate && <p className='text-red-400 text-xs mt-1'>{errors.eventDate}</p>}
                    </div>
                    <div>
                      <label className='text-[#2C1503] text-xs font-semibold uppercase mb-1.5 block'>Number of Persons (Pax)</label>
                      <input
                        type='number' min='1' value={pax}
                        onChange={e => setPax(e.target.value)}
                        placeholder='e.g. 50'
                        className='w-full border border-gray-200 rounded-xl px-4 py-3 text-sm outline-none focus:border-[#C4A882] transition bg-white'
                      />
                    </div>
                  </div>
                )}
                <button
                  onClick={() => setCurrentStep(1)}
                  className='w-full bg-[#3D1F00] text-white font-semibold text-sm py-2.5 rounded-xl mt-4 hover:bg-[#5a2f00] transition'
                >
                  Continue →
                </button>
              </div>
            )}
          </div>

          {/* Step 2 — Delivery */}
          <div className='bg-white rounded-2xl overflow-hidden shadow-sm'>
            <button
              className='w-full flex items-center justify-between p-5'
              onClick={() => setCurrentStep(currentStep === 1 ? -1 : 1)}
            >
              <div className='flex items-center gap-3'>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition
                  ${currentStep >= 1 ? 'bg-[#3D1F00] text-[#C4A882]' : 'bg-gray-100 text-gray-400'}`}>
                  {form.email && form.address && selectedZone ? '✓' : '2'}
                </div>
                <h2 className='text-[#2C1503] font-semibold text-sm'>Contact & Delivery</h2>
              </div>
              <span className='text-gray-400 text-sm'>{currentStep === 1 ? '↑' : '↓'}</span>
            </button>

            {currentStep === 1 && (
              <div className='px-5 pb-5 flex flex-col gap-4'>

                {/* Zone Selector */}
                <div>
                  <label className='text-[#2C1503] text-xs font-semibold uppercase mb-1.5 block'>
                    Delivery Zone <span className='text-red-400'>*</span>
                  </label>
                  {loadingZones ? (
                    <div className='h-12 bg-gray-100 rounded-xl animate-pulse' />
                  ) : zones.length === 0 ? (
                    <p className='text-gray-400 text-xs bg-gray-50 rounded-xl px-4 py-3'>
                      No delivery zones available at the moment.
                    </p>
                  ) : (
                    <div className='flex flex-col gap-2'>
                      {zones.map(zone => (
                        <label
                          key={zone.id}
                          className={`flex items-center justify-between border rounded-xl px-4 py-3 cursor-pointer transition
                            ${selectedZone?.id === zone.id ? 'border-[#C4A882] bg-[#FAF6F0]' : 'border-gray-200 hover:border-gray-300'}`}
                        >
                          <div className='flex items-center gap-3'>
                            <input
                              type='radio'
                              name='zone'
                              checked={selectedZone?.id === zone.id}
                              onChange={() => { setSelectedZone(zone); setErrors(p => ({ ...p, zone: '' })) }}
                              className='accent-[#3D1F00]'
                            />
                            <div>
                              <p className='text-[#2C1503] text-sm font-semibold'>{zone.name}</p>
                              <div className='flex items-center gap-2 text-xs text-gray-400'>
                                {zone.estimated_time && <span>⏱ {zone.estimated_time}</span>}
                                {zone.min_order_amount > 0 && (
                                  <span>· Min. ₱{parseFloat(zone.min_order_amount).toFixed(0)}</span>
                                )}
                              </div>
                            </div>
                          </div>
                          <p className='text-[#6f4e37] text-sm font-bold shrink-0'>
                            {parseFloat(zone.delivery_fee) === 0 ? 'Free' : `₱${parseFloat(zone.delivery_fee).toFixed(2)}`}
                          </p>
                        </label>
                      ))}
                    </div>
                  )}
                  {errors.zone && <p className='text-red-400 text-xs mt-1'>{errors.zone}</p>}
                </div>

                <div>
                  <label className='text-[#2C1503] text-xs font-semibold uppercase mb-1.5 block'>
                    Email Address <span className='text-red-400'>*</span>
                  </label>
                  <input
                    type='email'
                    value={form.email}
                    onChange={e => { !isAuthenticated && setForm({ ...form, email: e.target.value }); setErrors(p => ({ ...p, email: '' })) }}
                    readOnly={isAuthenticated}
                    className={`w-full border rounded-xl px-4 py-3 text-sm outline-none transition
                      ${isAuthenticated ? 'border-gray-100 bg-gray-50 text-gray-400 cursor-not-allowed'
                        : errors.email ? 'border-red-400 bg-[#FAF6F0]'
                        : 'border-gray-200 bg-[#FAF6F0] focus:border-[#C4A882]'}`}
                  />
                  {errors.email
                    ? <p className='text-red-400 text-xs mt-1'>{errors.email}</p>
                    : <p className='text-gray-400 text-xs mt-1'>{isAuthenticated ? '✓ Logged in — email cannot be changed.' : 'Order confirmation will be sent here.'}</p>
                  }
                </div>
                <div>
                  <label className='text-[#2C1503] text-xs font-semibold uppercase mb-1.5 block'>
                    Delivery Address <span className='text-red-400'>*</span>
                  </label>
                  <textarea
                    placeholder='House No., Street, Barangay'
                    value={form.address}
                    onChange={e => { setForm({ ...form, address: e.target.value }); setErrors(p => ({ ...p, address: '' })) }}
                    rows={3}
                    className={`w-full border rounded-xl px-4 py-3 text-sm text-gray-600 outline-none transition bg-[#FAF6F0] resize-none
                      ${errors.address ? 'border-red-400' : 'border-gray-200 focus:border-[#C4A882]'}`}
                  />
                  {errors.address && <p className='text-red-400 text-xs mt-1'>{errors.address}</p>}
                </div>
                <div>
                  <label className='text-[#2C1503] text-xs font-semibold uppercase mb-1.5 block'>
                    Order Notes <span className='text-gray-400 normal-case font-normal'>(optional)</span>
                  </label>
                  <textarea
                    placeholder='Any special instructions...'
                    value={form.notes}
                    onChange={e => setForm({ ...form, notes: e.target.value })}
                    rows={2}
                    className='w-full border border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-600 outline-none focus:border-[#C4A882] transition bg-[#FAF6F0] resize-none'
                  />
                </div>
                <button
                  onClick={() => setCurrentStep(2)}
                  className='w-full bg-[#3D1F00] text-white font-semibold text-sm py-2.5 rounded-xl hover:bg-[#5a2f00] transition'
                >
                  Continue →
                </button>
              </div>
            )}
          </div>

          {/* Step 3 — Payment */}
          <div className='bg-white rounded-2xl overflow-hidden shadow-sm'>
            <button
              className='w-full flex items-center justify-between p-5'
              onClick={() => setCurrentStep(currentStep === 2 ? -1 : 2)}
            >
              <div className='flex items-center gap-3'>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition
                  ${currentStep >= 2 ? 'bg-[#3D1F00] text-[#C4A882]' : 'bg-gray-100 text-gray-400'}`}>
                  3
                </div>
                <h2 className='text-[#2C1503] font-semibold text-sm'>Payment Method</h2>
              </div>
              <span className='text-gray-400 text-sm'>{currentStep === 2 ? '↑' : '↓'}</span>
            </button>

            {currentStep === 2 && (
              <div className='px-5 pb-5 flex flex-col gap-3'>
                <label className={`flex items-center gap-4 border rounded-xl px-4 py-4 cursor-pointer transition ${paymentMethod === 'cod' ? 'border-[#C4A882] bg-[#FAF6F0]' : 'border-gray-200'}`}>
                  <input type='radio' name='payment' value='cod' checked={paymentMethod === 'cod'} onChange={() => setPaymentMethod('cod')} className='accent-[#3D1F00]' />
                  <span className='text-lg'>🏦</span>
                  <div>
                    <p className='text-[#2C1503] text-sm font-semibold'>Cash on Delivery</p>
                    <p className='text-gray-400 text-xs'>Pay when your order arrives</p>
                  </div>
                </label>
                <label className={`flex items-center gap-4 border rounded-xl px-4 py-4 cursor-pointer transition ${paymentMethod === 'gcash' ? 'border-[#C4A882] bg-[#FAF6F0]' : 'border-gray-200'}`}>
                  <input type='radio' name='payment' value='gcash' checked={paymentMethod === 'gcash'} onChange={() => setPaymentMethod('gcash')} className='accent-[#3D1F00]' />
                  <span className='text-lg'>📱</span>
                  <div>
                    <p className='text-[#2C1503] text-sm font-semibold'>GCash</p>
                    <p className='text-gray-400 text-xs'>Send payment via GCash</p>
                  </div>
                </label>

                {/* Loyalty Points */}
                {isAuthenticated && loyalty && loyalty.redeemable_points > 0 && (
                  <div className={`border rounded-xl p-4 transition ${usePoints ? 'border-[#C4A882] bg-[#FAF6F0]' : 'border-gray-200'}`}>
                    <div className='flex items-center justify-between mb-2'>
                      <div className='flex items-center gap-2'>
                        <span className='text-lg'>🎁</span>
                        <div>
                          <p className='text-[#2C1503] text-sm font-semibold'>Use Loyalty Points</p>
                          <p className='text-gray-400 text-xs'>{loyalty.points} pts available (₱{loyalty.discount_value} value)</p>
                        </div>
                      </div>
                      <button
                        onClick={() => { setUsePoints(!usePoints); setPointsToUse(0) }}
                        className={`w-10 h-5 rounded-full transition-all duration-200 relative ${usePoints ? 'bg-[#3D1F00]' : 'bg-gray-300'}`}
                      >
                        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all duration-200 ${usePoints ? 'left-5' : 'left-0.5'}`} />
                      </button>
                    </div>
                    {usePoints && (
                      <div className='mt-2'>
                        <input
                          type='range'
                          min='0'
                          max={loyalty.redeemable_points}
                          value={pointsToUse}
                          onChange={e => setPointsToUse(parseInt(e.target.value))}
                          className='w-full accent-[#3D1F00]'
                        />
                        <div className='flex justify-between text-xs mt-1'>
                          <span className='text-gray-400'>0 pts</span>
                          <span className='text-[#6f4e37] font-semibold'>{pointsToUse} pts = ₱{(pointsToUse * 0.1).toFixed(2)} off</span>
                          <span className='text-gray-400'>{loyalty.redeemable_points} pts</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

        </div>

        {/* Right Column — Order Summary */}
        <div className='w-full lg:w-80 shrink-0'>
          <div className='bg-[#3D1F00] rounded-2xl p-6 shadow-sm lg:sticky lg:top-24'>

            {/* Mobile toggle */}
            <button
              className='w-full flex items-center justify-between lg:cursor-default mb-4'
              onClick={() => setShowSummary(!showSummary)}
            >
              <h2 className='text-white font-semibold text-sm'>Order Summary</h2>
              <span className='text-[#C4A882] text-xs lg:hidden'>{showSummary ? '↑ Hide' : '↓ Show'}</span>
            </button>

            <div className={`${showSummary ? 'block' : 'hidden'} lg:block`}>
              <div className='flex flex-col gap-3 mb-5'>
                {fetching ? (
                  <div className='h-16 bg-white/10 rounded-xl animate-pulse' />
                ) : buyNowData?.product ? (
                  <div className='flex items-center gap-3'>
                    <div className='w-14 h-14 rounded-xl bg-white/10 overflow-hidden shrink-0'>
                      {buyNowData.image && <img src={buyNowData.image} alt={buyNowData.name} className='w-full h-full object-cover' />}
                    </div>
                    <div>
                      <p className='text-white text-sm font-semibold'>{buyNowData.name}</p>
                      <p className='text-[#C4A882]/60 text-xs'>₱{buyNowData.price?.toFixed(2)}</p>
                    </div>
                  </div>
                ) : (
                  cartItems.map(item => (
                    <div key={item.id} className='flex items-center gap-3'>
                      <div className='w-12 h-12 rounded-xl overflow-hidden shrink-0 bg-white/10'>
                        {item.product_image && <img src={item.product_image} alt={item.product_name} className='w-full h-full object-cover' />}
                      </div>
                      <div className='flex-1 min-w-0'>
                        <p className='text-white text-xs font-semibold truncate'>{item.product_name}</p>
                        <p className='text-[#C4A882]/60 text-xs'>₱{parseFloat(item.product_price).toFixed(2)} × {item.quantity}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {buyNowData?.product && (
                <div className='flex items-center justify-between mb-4'>
                  <p className='text-[#C4A882]/70 text-xs font-semibold uppercase tracking-widest'>Qty</p>
                  <div className='flex items-center gap-3'>
                    <button onClick={() => setQuantity(q => Math.max(1, q - 1))} className='w-7 h-7 rounded-lg bg-white/10 hover:bg-white/20 text-white font-bold transition flex items-center justify-center'>−</button>
                    <span className='text-white text-sm font-bold w-4 text-center'>{quantity}</span>
                    <button onClick={() => setQuantity(q => q + 1)} className='w-7 h-7 rounded-lg bg-white/10 hover:bg-white/20 text-white font-bold transition flex items-center justify-center'>+</button>
                  </div>
                </div>
              )}

              <div className='h-px bg-white/10 mb-3' />

              <div className='flex flex-col gap-2 mb-3'>
                <div className='flex justify-between'>
                  <p className='text-[#C4A882]/60 text-xs'>Subtotal</p>
                  <p className='text-white text-xs font-semibold'>₱{subtotal.toFixed(2)}</p>
                </div>
                {pointsDiscount > 0 && (
                  <div className='flex justify-between'>
                    <p className='text-green-400 text-xs'>Points Discount</p>
                    <p className='text-green-400 text-xs font-semibold'>-₱{pointsDiscount.toFixed(2)}</p>
                  </div>
                )}
                <div className='flex justify-between'>
                  <p className='text-[#C4A882]/60 text-xs'>
                    Delivery {selectedZone && `(${selectedZone.name})`}
                  </p>
                  <p className='text-white text-xs font-semibold'>
                    {!selectedZone ? '—' : deliveryFee === 0 ? 'Free' : `₱${deliveryFee.toFixed(2)}`}
                  </p>
                </div>
                {orderType === 'bulk' && (
                  <>
                    <div className='h-px bg-white/10 my-1' />
                    <div className='flex justify-between'>
                      <p className='text-amber-300 text-xs'>Downpayment (50%)</p>
                      <p className='text-amber-300 text-xs font-bold'>₱{downpayment.toFixed(2)}</p>
                    </div>
                    <div className='flex justify-between'>
                      <p className='text-[#C4A882]/60 text-xs'>Remaining</p>
                      <p className='text-white text-xs font-semibold'>₱{downpayment.toFixed(2)}</p>
                    </div>
                  </>
                )}
              </div>

              <div className='h-px bg-white/10 mb-3' />

              <div className='flex justify-between items-center mb-4'>
                <p className='text-white font-semibold text-sm'>Total</p>
                <p className='text-white font-bold text-xl'>₱{total.toFixed(2)}</p>
              </div>

              {/* Minimum order warning banner */}
              {subtotal > 0 && belowMinOrder && (
                <div className='bg-amber-500/20 border border-amber-400/30 rounded-xl px-3 py-2.5 mb-3'>
                  <p className='text-amber-200 text-xs font-semibold'>
                    ⚠️ Add ₱{amountToMin.toFixed(2)} more to reach the ₱{GLOBAL_MIN_ORDER.toFixed(2)} minimum order.
                  </p>
                </div>
              )}

              <div className='flex items-center gap-2 bg-white/10 rounded-xl px-3 py-2 mb-4'>
                <span className='text-sm'>{paymentMethod === 'cod' ? '🏦' : '📱'}</span>
                <p className='text-white text-xs font-semibold'>
                  {paymentMethod === 'cod' ? 'Cash on Delivery' : 'GCash'}
                </p>
              </div>
            </div>

            {errors.minOrder && (
              <p className='text-red-300 text-xs text-center mb-2'>{errors.minOrder}</p>
            )}
            {errors.submit && (
              <p className='text-red-300 text-xs text-center mb-2'>{errors.submit}</p>
            )}

            <button
              onClick={handleSubmit}
              disabled={loading || !isFormValid}
              className='w-full flex items-center justify-center gap-2 bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 disabled:cursor-not-allowed text-[#2C1503] font-bold text-sm py-3 rounded-xl transition-all duration-200'
            >
              {loading ? (
                <span className='flex items-center gap-2'>
                  <svg className='animate-spin h-4 w-4' viewBox='0 0 24 24' fill='none'>
                    <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'/>
                    <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z'/>
                  </svg>
                  Placing Order...
                </span>
              ) : orderType === 'bulk' ? '→ PLACE BULK ORDER' : '→ PLACE ORDER'}
            </button>
            <p className='text-[#C4A882]/40 text-[10px] text-center mt-3'>Delivery fee varies by zone</p>
          </div>
        </div>

      </div>
    </div>
  )
}

export default Checkout