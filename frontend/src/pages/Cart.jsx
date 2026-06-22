import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { HiOutlineTrash, HiOutlineShoppingBag } from 'react-icons/hi'
import { getCart, updateCart, deleteFromCart } from '../services/cartService'
import { getProducts } from '../services/productService'
import { useAuth } from '../context/AuthContext'
import Card from '../components/Card'

const Cart = () => {
  const [cartItems,    setCartItems]    = useState([])
  const [loading,      setLoading]      = useState(true)
  const [deleting,     setDeleting]     = useState(null)
  const [updating,     setUpdating]     = useState(null)
  const [recommended,  setRecommended]  = useState([])
  const [selectedIds,  setSelectedIds]  = useState([])
  const navigate = useNavigate()
  const { fetchCartCount } = useAuth()

  useEffect(() => {
    fetchCart()
  }, [])

  const fetchCart = async () => {
    setLoading(true)
    try {
      const res = await getCart()
      setCartItems(res.data)
      setSelectedIds(res.data.map(i => i.id))
      if (res.data.length > 0) fetchRecommended()
    } catch (err) {
      console.error('Failed to fetch cart', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchRecommended = async () => {
    try {
      const res = await getProducts({ featured: true })
      setRecommended(res.data.slice(0, 4))
    } catch {}
  }

  const handleUpdateQuantity = async (id, quantity) => {
    if (quantity < 1) return
    setUpdating(id)
    try {
      await updateCart(id, quantity)
      setCartItems(prev => prev.map(item => item.id === id ? { ...item, quantity } : item))
      fetchCartCount()
    } catch (err) {
      console.error('Failed to update cart', err)
    } finally {
      setUpdating(null)
    }
  }

  const handleDelete = async (id) => {
    setDeleting(id)
    try {
      await deleteFromCart(id)
      setCartItems(prev => prev.filter(item => item.id !== id))
      setSelectedIds(prev => prev.filter(i => i !== id))
      fetchCartCount()
    } catch (err) {
      console.error('Failed to delete cart item', err)
    } finally {
      setDeleting(null)
    }
  }

  const handleClearCart = async () => {
    if (!window.confirm('Clear all items from cart?')) return
    for (const item of cartItems) {
      await deleteFromCart(item.id)
    }
    setCartItems([])
    setSelectedIds([])
    fetchCartCount()
  }

  const toggleSelect = (id) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const toggleSelectAll = () => {
    setSelectedIds(
      selectedIds.length === cartItems.length ? [] : cartItems.map(i => i.id)
    )
  }

  const selectedItems = cartItems.filter(i => selectedIds.includes(i.id))
  const subtotal      = selectedItems.reduce((sum, item) => sum + parseFloat(item.product_price) * item.quantity, 0)
  const totalItems    = selectedItems.reduce((sum, item) => sum + item.quantity, 0)

  return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0]'>

      {/* Header Banner */}
      <div className='bg-[#3D1F00] px-6 sm:px-20 py-6 sm:py-8'>
        <div className='flex items-center gap-2 text-[#C4A882]/60 text-xs font-semibold tracking-widest uppercase mb-3'>
          <Link to='/home' className='hover:text-[#C4A882] transition'>Home</Link>
          <span>›</span>
          <span className='text-[#C4A882]'>My Cart</span>
        </div>
        <div className='flex items-center justify-between'>
          <div>
            <h1 className='text-white text-3xl font-bold'>
              My <em className='text-[#C4A882] italic font-serif'>Cart</em>
            </h1>
            <p className='text-[#C4A882]/50 text-xs mt-1'>
              {cartItems.length > 0
                ? `${cartItems.length} item${cartItems.length > 1 ? 's' : ''} in your cart`
                : 'Your cart is empty'}
            </p>
          </div>
          {cartItems.length > 0 && (
            <div className='bg-[#C4A882]/20 rounded-xl px-4 py-2 text-center'>
              <p className='text-[#C4A882] text-[10px] uppercase tracking-widest'>Items</p>
              <p className='text-white text-2xl font-bold'>{cartItems.length}</p>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className='flex flex-col lg:flex-row gap-6 px-4 sm:px-16 py-6 sm:py-10 max-w-6xl mx-auto w-full'>

        {/* Cart Items */}
        <div className='flex flex-col gap-4 flex-1'>

          {loading ? (
            [...Array(2)].map((_, i) => (
              <div key={i} className='bg-white rounded-2xl p-4 flex gap-4 shadow-sm animate-pulse'>
                <div className='w-24 h-24 rounded-xl bg-gray-200 shrink-0' />
                <div className='flex flex-col gap-2 flex-1'>
                  <div className='h-4 bg-gray-200 rounded w-1/2' />
                  <div className='h-3 bg-gray-100 rounded w-full' />
                  <div className='h-3 bg-gray-100 rounded w-3/4' />
                </div>
              </div>
            ))
          ) : cartItems.length > 0 ? (
            <>
              {/* Select All + Clear */}
              <div className='flex items-center justify-between bg-white rounded-xl px-4 py-2.5 shadow-sm'>
                <label className='flex items-center gap-2 cursor-pointer'>
                  <input
                    type='checkbox'
                    checked={selectedIds.length === cartItems.length}
                    onChange={toggleSelectAll}
                    className='accent-[#3D1F00] w-4 h-4'
                  />
                  <span className='text-[#2C1503] text-xs font-semibold'>
                    Select All ({cartItems.length})
                  </span>
                </label>
                {selectedIds.length > 0 && (
                  <button
                    onClick={handleClearCart}
                    className='text-red-400 hover:text-red-600 text-xs font-semibold flex items-center gap-1 transition'
                  >
                    <HiOutlineTrash size={14} />
                    Clear Cart
                  </button>
                )}
              </div>

              {/* Cart Items List */}
              {cartItems.map((item) => (
                <div
                  key={item.id}
                  className={`bg-white rounded-2xl p-4 flex gap-4 shadow-sm transition-all duration-200
                    ${deleting === item.id ? 'opacity-50 scale-95' : 'hover:shadow-md'}
                    ${!selectedIds.includes(item.id) ? 'opacity-60' : ''}
                  `}
                >
                  {/* Checkbox */}
                  <div className='flex items-start pt-1'>
                    <input
                      type='checkbox'
                      checked={selectedIds.includes(item.id)}
                      onChange={() => toggleSelect(item.id)}
                      className='accent-[#3D1F00] w-4 h-4'
                    />
                  </div>

                  {/* Image */}
                  <Link to={`/product/${item.product}`} className='w-24 h-24 rounded-xl overflow-hidden shrink-0 block'>
                    {item.product_image
                      ? <img src={item.product_image} alt={item.product_name} className='w-full h-full object-cover hover:scale-105 transition-transform duration-300' />
                      : <div className='w-full h-full bg-gray-200 flex items-center justify-center text-2xl'>☕</div>
                    }
                  </Link>

                  {/* Details */}
                  <div className='flex flex-col flex-1 gap-1 min-w-0'>
                    <div className='flex justify-between items-start gap-2'>
                      <div className='min-w-0'>
                        <Link to={`/product/${item.product}`}>
                          <h3 className='text-[#2C1503] font-semibold text-sm hover:text-[#6f4e37] transition truncate'>
                            {item.product_name}
                          </h3>
                        </Link>
                        {item.variant_size && (
                          <span className='text-xs text-[#C4A882] bg-[#FAF6F0] px-2 py-0.5 rounded-full capitalize'>
                            {item.variant_size}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => handleDelete(item.id)}
                        disabled={deleting === item.id}
                        className='text-gray-300 hover:text-red-400 transition shrink-0 p-1 rounded-lg hover:bg-red-50'
                      >
                        <HiOutlineTrash size={16} />
                      </button>
                    </div>

                    {/* Quantity + Price */}
                    <div className='flex items-center justify-between mt-auto pt-2 flex-wrap gap-2'>
                      <div className='flex items-center gap-1.5'>
                        <button
                          onClick={() => handleUpdateQuantity(item.id, item.quantity - 1)}
                          disabled={updating === item.id || item.quantity <= 1}
                          className='w-7 h-7 rounded-lg border border-gray-200 text-[#2C1503] font-bold text-sm hover:bg-gray-100 disabled:opacity-40 transition flex items-center justify-center'
                        >
                          −
                        </button>
                        <span className={`text-sm font-bold text-[#2C1503] w-6 text-center ${updating === item.id ? 'opacity-50' : ''}`}>
                          {item.quantity}
                        </span>
                        <button
                          onClick={() => handleUpdateQuantity(item.id, item.quantity + 1)}
                          disabled={updating === item.id}
                          className='w-7 h-7 rounded-lg border border-gray-200 text-[#2C1503] font-bold text-sm hover:bg-gray-100 disabled:opacity-40 transition flex items-center justify-center'
                        >
                          +
                        </button>
                        <span className='text-gray-400 text-xs ml-1'>
                          ₱{parseFloat(item.product_price).toFixed(2)} each
                        </span>
                      </div>
                      <p className='text-[#2C1503] font-bold text-sm'>
                        ₱{(parseFloat(item.product_price) * item.quantity).toFixed(2)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}

              {/* Continue Shopping */}
              <Link to='/home' className='flex items-center gap-1.5 text-[#6f4e37] text-xs font-semibold hover:underline mt-1'>
                ← CONTINUE SHOPPING
              </Link>
            </>
          ) : (
            <div className='flex flex-col items-center justify-center py-20 gap-4'>
              <div className='w-20 h-20 rounded-full bg-[#3D1F00]/10 flex items-center justify-center'>
                <HiOutlineShoppingBag size={36} className='text-[#3D1F00]/40' />
              </div>
              <p className='text-[#2C1503] font-semibold text-lg'>Your cart is empty</p>
              <p className='text-gray-400 text-sm'>Add some products to get started</p>
              <Link
                to='/home'
                className='bg-[#3D1F00] text-white text-sm font-semibold px-6 py-2.5 rounded-xl hover:bg-[#5a2f00] transition'
              >
                Browse Products
              </Link>
            </div>
          )}

          {/* Recommended Products */}
          {recommended.length > 0 && (
            <div className='mt-6'>
              <div className='flex items-center gap-2 mb-4'>
                <div className='flex-1 h-px bg-[#6f4e37]/10' />
                <p className='text-[#6f4e37] text-xs font-semibold tracking-widest uppercase'>You Might Also Like</p>
                <div className='flex-1 h-px bg-[#6f4e37]/10' />
              </div>
              <div className='grid grid-cols-2 sm:grid-cols-4 gap-4'>
                {recommended.map(product => (
                  <Card
                    key={product.id}
                    productId={product.id}
                    image={product.image || null}
                    name={product.name}
                    description={product.description}
                    price={parseFloat(product.price)}
                    rating={product.average_rating || 0}
                    reviewCount={product.rating_count || 0}
                    premium={product.is_featured}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Order Summary */}
        {cartItems.length > 0 && (
          <div className='w-full lg:w-80 shrink-0'>
            <div className='bg-[#3D1F00] rounded-2xl p-5 sm:p-6 shadow-sm lg:sticky lg:top-24'>
              <h2 className='text-white font-semibold text-sm mb-4'>Order Summary</h2>

              {/* Selected items */}
              <div className='flex flex-col gap-2 mb-4'>
                <p className='text-[#C4A882]/50 text-xs mb-1'>
                  {selectedItems.length} of {cartItems.length} item{cartItems.length > 1 ? 's' : ''} selected
                </p>
                {selectedItems.map(item => (
                  <div key={item.id} className='flex justify-between'>
                    <p className='text-[#C4A882]/70 text-xs truncate flex-1 mr-2'>{item.product_name} ×{item.quantity}</p>
                    <p className='text-white text-xs font-semibold shrink-0'>
                      ₱{(parseFloat(item.product_price) * item.quantity).toFixed(2)}
                    </p>
                  </div>
                ))}
              </div>

              <div className='h-px bg-white/10 mb-4' />

              <div className='flex flex-col gap-2 mb-4'>
                <div className='flex justify-between'>
                  <p className='text-[#C4A882]/60 text-xs'>Subtotal ({totalItems} items)</p>
                  <p className='text-white text-xs font-semibold'>₱{subtotal.toFixed(2)}</p>
                </div>
                <div className='flex justify-between'>
                  <p className='text-[#C4A882]/60 text-xs'>Delivery</p>
                  <p className='text-green-400 text-xs font-semibold'>Free</p>
                </div>
              </div>

              <div className='h-px bg-white/10 mb-4' />

              <div className='flex justify-between items-center mb-5'>
                <p className='text-white font-semibold text-sm'>Total</p>
                <p className='text-white font-bold text-xl'>₱{subtotal.toFixed(2)}</p>
              </div>

              {/* Checkout Button */}
              <button
                onClick={() => navigate('/checkout')}
                disabled={selectedItems.length === 0}
                className='w-full flex items-center justify-center gap-2 bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 disabled:cursor-not-allowed text-[#2C1503] font-bold text-sm py-3 rounded-xl transition-all duration-200'
              >
                → PROCEED TO CHECKOUT
              </button>

              {selectedItems.length === 0 && (
                <p className='text-[#C4A882]/40 text-[10px] text-center mt-2'>Select items to checkout</p>
              )}

              <p className='text-[#C4A882]/40 text-[10px] text-center mt-2'>Secure checkout · Free delivery</p>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}

export default Cart