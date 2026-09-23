import React, { useState, useEffect, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { getProducts, getCategories } from '../services/productService'
import { createOrder, createPayMongoSource, verifyPaymongoPayment } from '../services/orderService'
import Card from '../components/Card'

// The order a customer is paying for in GCash. GCash sends them to another site and back, and
// this page is rebuilt on the way (the cart is gone), so what we need to finish the trip —
// which order, which table, how much — waits here. Dine-in customers usually aren't signed in,
// so unlike regular checkout this can't lean on the Orders page.
const PENDING_KEY = 'pending_dinein_order'

const PAYMENT_OPTIONS = [
  { id: 'counter', icon: '💳', label: 'At the counter' },
  { id: 'gcash',   icon: '📱', label: 'GCash' },
]

// What the customer is told when they come back from (or can't get to) GCash.
const GCASH_VIEWS = {
  checking: { icon: '⏳', title: 'Confirming your payment…', text: 'One moment — we are checking with GCash.' },
  paid:     { icon: '☕', title: 'Order Placed!',            text: 'Payment received via GCash. Your order is being prepared.' },
  pending:  { icon: '🕒', title: 'Order Placed',             text: "We haven't received GCash's confirmation yet. If you already paid, show this order number to our staff — they'll check it." },
  failed:   { icon: '⚠️', title: 'Payment not completed',    text: 'Your order is saved, but the GCash payment did not go through.' },
  error:    { icon: '⚠️', title: 'Order Placed',             text: "We couldn't open GCash just now." },
}

const DineInMenu = () => {
  const [searchParams]  = useSearchParams()
  const tableNumber     = searchParams.get('table')
  const navigate        = useNavigate()

  const [products,       setProducts]       = useState([])
  const [categories,     setCategories]     = useState([])
  const [activeCategory, setActiveCategory] = useState('All')
  const [loading,        setLoading]        = useState(true)
  const [cart,           setCart]           = useState([])
  const [showCart,       setShowCart]       = useState(false)
  const [form,           setForm]           = useState({ email: '', phone: '', notes: '' })
  const [paymentMethod,  setPaymentMethod]  = useState('counter')
  const [placing,        setPlacing]        = useState(false)
  const [orderSuccess,   setOrderSuccess]   = useState(null)
  const [gcash,          setGcash]          = useState(null)   // the GCash trip: { state, order, retrying }
  const [errors,         setErrors]         = useState({})
  const returnHandled = useRef(false)                            // (dev StrictMode runs effects twice)

  useEffect(() => {
    if (!tableNumber) { navigate('/home'); return }
    fetchData()
    const outcome = searchParams.get('payment')
    if ((outcome === 'success' || outcome === 'failed') && !returnHandled.current) {
      returnHandled.current = true
      returnFromGcash(outcome)
    }
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const [prodRes, catRes] = await Promise.all([getProducts(), getCategories()])
      setProducts(prodRes.data)
      setCategories(catRes.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleCategoryFilter = async (cat) => {
    setActiveCategory(cat)
    setLoading(true)
    try {
      const res = await getProducts(cat === 'All' ? {} : { category: cat })
      setProducts(res.data)
    } finally {
      setLoading(false)
    }
  }

  const addToCart = (product) => {
    setCart(prev => {
      const existing = prev.find(i => i.id === product.id)
      if (existing) return prev.map(i => i.id === product.id ? { ...i, qty: i.qty + 1 } : i)
      return [...prev, { ...product, qty: 1 }]
    })
  }

  const removeFromCart = (id) => setCart(prev => prev.filter(i => i.id !== id))

  const updateQty = (id, qty) => {
    if (qty < 1) { removeFromCart(id); return }
    setCart(prev => prev.map(i => i.id === id ? { ...i, qty } : i))
  }

  const subtotal = cart.reduce((sum, i) => sum + parseFloat(i.price) * i.qty, 0)

  const validatePhone = (phone) => /^(09\d{9}|\+639\d{9})$/.test(phone.replace(/[\s\-]/g, ''))

  // Phone is optional for dine-in — the customer's already at the table, so
  // it doesn't carry the "how do we reach them" weight it does for
  // delivery/pickup (see Checkout.jsx, where it's required). Still format-
  // checked if they do type one in, same as the backend (CreateOrderSerializer).
  const isFormValid = form.email && (!form.phone || validatePhone(form.phone)) && cart.length > 0

  // Sends the customer to GCash to pay for `order` ({ id, table, total }). The amount isn't sent:
  // the server works out what to charge from the order itself.
  const startGcash = async (order) => {
    const res = await createPayMongoSource({
      order_id:    order.id,
      success_url: `${window.location.origin}/menu?table=${tableNumber}&payment=success`,
      failed_url:  `${window.location.origin}/menu?table=${tableNumber}&payment=failed`,
    })
    const url = res.data?.checkout_url
    if (!/^https:\/\//i.test(url || '')) throw new Error('GCash did not give a payment page')
    localStorage.setItem(PENDING_KEY, JSON.stringify(order))
    window.location.href = url            // same tab: on a phone a new tab is easy to lose, and GCash opens its app from here
  }

  const readPendingOrder = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(PENDING_KEY))
      return saved && String(saved.table) === String(tableNumber) ? saved : null
    } catch { return null }
  }

  // The customer is back from GCash (?payment=success|failed in the address).
  const returnFromGcash = async (outcome) => {
    const order = readPendingOrder()
    navigate(`/menu?table=${tableNumber}`, { replace: true })   // so refreshing doesn't do this again
    if (!order) return                                            // a different phone, or cleared storage: just show the menu
    if (outcome === 'failed') { setGcash({ state: 'failed', order }); return }

    setGcash({ state: 'checking', order })
    // GCash can take a few seconds to report the payment: ask a few times before giving up.
    for (let attempt = 0; attempt < 6; attempt++) {
      try {
        const res = await verifyPaymongoPayment(order.id)
        if (['paid', 'downpayment'].includes(res.data.payment_status)) {
          localStorage.removeItem(PENDING_KEY)
          setGcash({ state: 'paid', order })
          return
        }
      } catch { /* the next attempt may get through */ }
      await new Promise(resolve => setTimeout(resolve, 2000))
    }
    setGcash({ state: 'pending', order })
  }

  const retryGcash = async () => {
    setGcash(prev => ({ ...prev, retrying: true }))
    try {
      await startGcash(gcash.order)
    } catch {
      setGcash(prev => ({ ...prev, state: 'error', retrying: false }))
    }
  }

  const handlePlaceOrder = async () => {
    const newErrors = {}
    if (form.phone && !validatePhone(form.phone)) newErrors.phone = 'Enter a valid Philippine mobile number (e.g. 09171234567)'
    if (Object.keys(newErrors).length > 0 || !form.email || cart.length === 0) {
      setErrors(newErrors)
      return
    }

    setPlacing(true)
    setErrors({})
    let leavingForGcash = false
    try {
      const res = await createOrder({
        email:          form.email,
        phone:          form.phone.replace(/[\s\-]/g, ''),
        address:        `Table ${tableNumber}`,
        notes:          form.notes,
        payment_method: paymentMethod,
        order_type:     'dine_in',
        table_number:   tableNumber,
        items:          cart.map(i => ({ product: i.id, quantity: i.qty })),
      })

      if (paymentMethod === 'gcash') {
        const order = { id: res.data.id, table: tableNumber, total: subtotal }
        setCart([])
        setShowCart(false)
        try {
          leavingForGcash = true          // keep the button locked while the browser leaves — no second order
          await startGcash(order)
        } catch {
          leavingForGcash = false
          setGcash({ state: 'error', order })   // the order exists; they can retry or pay at the counter
        }
        return
      }

      setOrderSuccess(res.data)
      setCart([])
    } catch (err) {
      const data = err.response?.data
      const message = data?.phone?.[0] || data?.email?.[0] || data?.payment_method?.[0] || data?.error || 'Failed to place order. Please try again.'
      setErrors({ submit: message })
      console.error(err)
    } finally {
      if (!leavingForGcash) setPlacing(false)
    }
  }

  if (gcash) {
    const view = GCASH_VIEWS[gcash.state]
    const canRetry = gcash.state === 'failed' || gcash.state === 'error'
    return (
      <div className='min-h-screen bg-[#FAF6F0] flex items-center justify-center p-6'>
        <div className='bg-white rounded-3xl p-8 max-w-sm w-full text-center shadow-xl' data-gcash-state={gcash.state}>
          <div className='text-5xl mb-4'>{view.icon}</div>
          <h2 className='text-[#2C1503] text-2xl font-bold mb-1'>{view.title}</h2>
          <p className='text-gray-400 text-sm mb-4'>{view.text}</p>
          <div className='bg-[#FAF6F0] rounded-xl p-4 mb-6 text-left'>
            <div className='flex justify-between text-sm mb-1'>
              <span className='text-gray-400'>Order ID</span>
              <span className='text-[#2C1503] font-bold'>#CC-{String(gcash.order.id).padStart(5, '0')}</span>
            </div>
            <div className='flex justify-between text-sm mb-1'>
              <span className='text-gray-400'>Table</span>
              <span className='text-[#2C1503] font-bold'>Table {gcash.order.table}</span>
            </div>
            <div className='flex justify-between text-sm'>
              <span className='text-gray-400'>Total</span>
              <span className='text-[#2C1503] font-bold'>₱{Number(gcash.order.total).toFixed(2)}</span>
            </div>
          </div>
          {canRetry && (
            <>
              <button
                onClick={retryGcash}
                disabled={gcash.retrying}
                className='w-full bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 text-[#2C1503] font-bold py-3 rounded-xl text-sm transition'
              >
                {gcash.retrying ? 'Opening GCash…' : '📱 Try GCash again'}
              </button>
              <p className='text-[#C4A882] text-xs mt-3'>Or just pay at the counter — tell our staff your order number.</p>
            </>
          )}
          {gcash.state !== 'checking' && (
            <button
              onClick={() => { setGcash(null); fetchData() }}
              className='mt-4 w-full bg-[#2C1503] text-white font-bold py-3 rounded-xl text-sm'
            >
              Order Again
            </button>
          )}
        </div>
      </div>
    )
  }

  if (orderSuccess) return (
    <div className='min-h-screen bg-[#FAF6F0] flex items-center justify-center p-6'>
      <div className='bg-white rounded-3xl p-8 max-w-sm w-full text-center shadow-xl'>
        <div className='text-5xl mb-4'>☕</div>
        <h2 className='text-[#2C1503] text-2xl font-bold mb-1'>Order Placed!</h2>
        <p className='text-gray-400 text-sm mb-4'>Your order is being prepared.</p>
        <div className='bg-[#FAF6F0] rounded-xl p-4 mb-6 text-left'>
          <div className='flex justify-between text-sm mb-1'>
            <span className='text-gray-400'>Order ID</span>
            <span className='text-[#2C1503] font-bold'>#CC-{String(orderSuccess.id).padStart(5, '0')}</span>
          </div>
          <div className='flex justify-between text-sm mb-1'>
            <span className='text-gray-400'>Table</span>
            <span className='text-[#2C1503] font-bold'>Table {tableNumber}</span>
          </div>
          <div className='flex justify-between text-sm'>
            <span className='text-gray-400'>Total</span>
            <span className='text-[#2C1503] font-bold'>₱{subtotal.toFixed(2)}</span>
          </div>
        </div>
        <p className='text-[#C4A882] text-xs'>Please pay at the counter. Thank you! 😊</p>
        <p className='text-gray-400 text-xs mt-2'>📧 We'll email your order details to {form.email}.</p>
        <button
          onClick={() => { setOrderSuccess(null); fetchData() }}
          className='mt-4 w-full bg-[#2C1503] text-white font-bold py-3 rounded-xl text-sm'
        >
          Order Again
        </button>
      </div>
    </div>
  )

  return (
    <div className='min-h-screen bg-[#FAF6F0]'>

      {/* Header */}
      <div className='bg-[#3D1F00] px-6 py-4 flex items-center justify-between sticky top-0 z-40'>
        <div>
          <p className='text-white font-bold text-sm tracking-widest'>CAFFEINE CORNER</p>
          <p className='text-[#C4A882]/60 text-xs'>Table {tableNumber}</p>
        </div>
        <button
          onClick={() => setShowCart(true)}
          className='relative bg-[#C4A882] text-[#2C1503] font-bold text-xs px-4 py-2 rounded-full'
        >
          🛒 Cart
          {cart.length > 0 && (
            <span className='absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center'>
              {cart.reduce((s, i) => s + i.qty, 0)}
            </span>
          )}
        </button>
      </div>

      {/* Categories */}
      <div className='px-4 py-4 flex gap-2 overflow-x-auto'>
        {['All', ...categories.map(c => c.name)].map(cat => (
          <button
            key={cat}
            onClick={() => handleCategoryFilter(cat)}
            className={`px-4 py-1.5 rounded-full text-xs font-bold whitespace-nowrap transition
              ${activeCategory === cat
                ? 'bg-[#3D1F00] text-white'
                : 'bg-white text-[#6f4e37] border border-gray-200'
              }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Products */}
      <div className='px-4 pb-24'>
        {loading ? (
          <div className='grid grid-cols-2 gap-4'>
            {[...Array(6)].map((_, i) => (
              <div key={i} className='bg-white rounded-2xl h-48 animate-pulse' />
            ))}
          </div>
        ) : (
          <div className='grid grid-cols-2 gap-4'>
            {products.map(product => (
              <div key={product.id} className='bg-white rounded-2xl overflow-hidden shadow-sm'>
                <div className='h-32 overflow-hidden'>
                  {product.image
                    ? <img src={product.image} alt={product.name} className='w-full h-full object-cover' />
                    : <div className='w-full h-full bg-gray-200 flex items-center justify-center text-2xl'>☕</div>
                  }
                </div>
                <div className='p-3'>
                  <p className='text-[#2C1503] font-semibold text-sm'>{product.name}</p>
                  <p className='text-gray-400 text-xs line-clamp-1 mb-2'>{product.description}</p>
                  <div className='flex items-center justify-between'>
                    <p className='text-[#2C1503] font-bold text-sm'>₱{parseFloat(product.price).toFixed(2)}</p>
                    <button
                      onClick={() => addToCart(product)}
                      className='bg-[#3D1F00] text-white text-xs font-bold px-3 py-1.5 rounded-lg'
                    >
                      + Add
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Cart Drawer */}
      {showCart && (
        <div className='fixed inset-0 z-50 flex'>
          <div className='flex-1 bg-black/40' onClick={() => setShowCart(false)} />
          <div className='w-80 bg-white h-full flex flex-col shadow-2xl'>
            <div className='bg-[#3D1F00] px-6 py-4 flex justify-between items-center'>
              <p className='text-white font-bold'>Your Cart — Table {tableNumber}</p>
              <button onClick={() => setShowCart(false)} className='text-white text-xl'>✕</button>
            </div>

            <div className='flex-1 overflow-y-auto p-4'>
              {cart.length === 0 ? (
                <p className='text-gray-400 text-sm text-center mt-8'>Cart is empty</p>
              ) : (
                cart.map(item => (
                  <div key={item.id} className='flex items-center gap-3 py-3 border-b border-gray-100'>
                    <div className='flex-1'>
                      <p className='text-[#2C1503] text-sm font-semibold'>{item.name}</p>
                      <p className='text-gray-400 text-xs'>₱{parseFloat(item.price).toFixed(2)}</p>
                    </div>
                    <div className='flex items-center gap-2'>
                      <button onClick={() => updateQty(item.id, item.qty - 1)} className='w-6 h-6 rounded-full border border-gray-200 text-xs font-bold'>−</button>
                      <span className='text-sm font-bold w-4 text-center'>{item.qty}</span>
                      <button onClick={() => updateQty(item.id, item.qty + 1)} className='w-6 h-6 rounded-full border border-gray-200 text-xs font-bold'>+</button>
                    </div>
                    <p className='text-[#2C1503] text-sm font-bold w-16 text-right'>
                      ₱{(parseFloat(item.price) * item.qty).toFixed(2)}
                    </p>
                  </div>
                ))
              )}
            </div>

            {cart.length > 0 && (
              <div className='p-4 border-t border-gray-100'>
                {/* Email input */}
                <input
                  type='email'
                  placeholder='Your email (we send your order details here)'
                  value={form.email}
                  onChange={e => setForm(prev => ({ ...prev, email: e.target.value }))}
                  className='w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[#C4A882] mb-2'
                />
                {/* Phone input — optional for dine-in (see validate() in
                    CreateOrderSerializer), unlike regular/pickup checkout */}
                <input
                  type='tel'
                  placeholder='Phone number (optional)'
                  value={form.phone}
                  onChange={e => {
                    setForm(prev => ({ ...prev, phone: e.target.value }))
                    setErrors(prev => ({ ...prev, phone: '' }))
                  }}
                  className={`w-full border rounded-xl px-4 py-2.5 text-sm outline-none mb-1
                    ${errors.phone ? 'border-red-400' : 'border-gray-200 focus:border-[#C4A882]'}`}
                />
                {errors.phone && <p className='text-red-400 text-xs mb-2'>{errors.phone}</p>}
                <textarea
                  placeholder='Special instructions... (optional)'
                  value={form.notes}
                  onChange={e => setForm(prev => ({ ...prev, notes: e.target.value }))}
                  rows={2}
                  className='w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[#C4A882] resize-none mb-3'
                />
                <div className='flex justify-between mb-3'>
                  <span className='text-gray-500 text-sm font-semibold'>Total</span>
                  <span className='text-[#2C1503] font-bold text-lg'>₱{subtotal.toFixed(2)}</span>
                </div>
                <p className='text-gray-500 text-xs font-semibold mb-2'>How would you like to pay?</p>
                <div className='grid grid-cols-2 gap-2 mb-2' role='group' aria-label='Payment method'>
                  {PAYMENT_OPTIONS.map(option => (
                    <button
                      key={option.id}
                      type='button'
                      onClick={() => setPaymentMethod(option.id)}
                      aria-pressed={paymentMethod === option.id}
                      className={`border rounded-xl py-2.5 text-xs font-bold transition
                        ${paymentMethod === option.id
                          ? 'border-[#C4A882] bg-[#FAF6F0] text-[#2C1503]'
                          : 'border-gray-200 text-gray-400'}`}
                    >
                      {option.icon} {option.label}
                    </button>
                  ))}
                </div>
                <p className='text-gray-400 text-xs mb-3 text-center'>
                  {paymentMethod === 'gcash'
                    ? `You'll be taken to GCash to pay ₱${subtotal.toFixed(2)}. Your order is confirmed once it goes through.`
                    : '💳 Pay at the counter after ordering'}
                </p>
                {errors.submit && (
                  <p className='text-red-400 text-xs text-center mb-2'>{errors.submit}</p>
                )}
                <button
                  onClick={handlePlaceOrder}
                  disabled={placing || !isFormValid}
                  className='w-full bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 text-[#2C1503] font-bold py-3 rounded-xl text-sm transition'
                >
                  {placing ? 'Placing Order...' : paymentMethod === 'gcash' ? '📱 PLACE ORDER & PAY' : '→ PLACE ORDER'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  )
}

export default DineInMenu