import React, { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { getProducts, getCategories } from '../services/productService'
import { createOrder } from '../services/orderService'
import Card from '../components/Card'

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
  const [form,           setForm]           = useState({ email: '', notes: '' })
  const [placing,        setPlacing]        = useState(false)
  const [orderSuccess,   setOrderSuccess]   = useState(null)

  useEffect(() => {
    if (!tableNumber) { navigate('/home'); return }
    fetchData()
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

  const handlePlaceOrder = async () => {
    if (!form.email || cart.length === 0) return
    setPlacing(true)
    try {
      const res = await createOrder({
        email:          form.email,
        address:        `Table ${tableNumber}`,
        notes:          form.notes,
        payment_method: 'counter',
        order_type:     'dine_in',
        table_number:   tableNumber,
        items:          cart.map(i => ({ product: i.id, quantity: i.qty })),
      })
      setOrderSuccess(res.data)
      setCart([])
    } catch (err) {
      console.error(err)
    } finally {
      setPlacing(false)
    }
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
                  placeholder='Your email (for receipt)'
                  value={form.email}
                  onChange={e => setForm(prev => ({ ...prev, email: e.target.value }))}
                  className='w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[#C4A882] mb-2'
                />
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
                <p className='text-gray-400 text-xs mb-3 text-center'>💳 Pay at the counter after ordering</p>
                <button
                  onClick={handlePlaceOrder}
                  disabled={placing || !form.email}
                  className='w-full bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 text-[#2C1503] font-bold py-3 rounded-xl text-sm transition'
                >
                  {placing ? 'Placing Order...' : '→ PLACE ORDER'}
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