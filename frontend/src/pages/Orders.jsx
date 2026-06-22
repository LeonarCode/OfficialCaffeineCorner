import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getOrders } from '../services/orderService'

const STATUS_CONFIG = {
  pending:    { label: 'Pending',    color: 'bg-yellow-100 text-yellow-700',  dot: 'bg-yellow-400',  step: 1 },
  confirmed:  { label: 'Confirmed',  color: 'bg-blue-100 text-blue-700',      dot: 'bg-blue-400',    step: 2 },
  processing: { label: 'Processing', color: 'bg-purple-100 text-purple-700',  dot: 'bg-purple-400',  step: 3 },
  delivered:  { label: 'Delivered',  color: 'bg-green-100 text-green-700',    dot: 'bg-green-400',   step: 4 },
  cancelled:  { label: 'Cancelled',  color: 'bg-red-100 text-red-700',        dot: 'bg-red-400',     step: 0 },
}

const PAYMENT_STATUS_CONFIG = {
  unpaid:      { label: '⏳ Unpaid',            color: 'text-yellow-600' },
  downpayment: { label: '⚡ Downpayment Paid',  color: 'text-amber-600' },
  paid:        { label: '✓ Paid',               color: 'text-green-600' },
  failed:      { label: '✗ Failed',             color: 'text-red-600' },
  refunded:    { label: '↩ Refunded',           color: 'text-gray-500' },
}

const ORDER_TYPE_CONFIG = {
  regular: { label: '📦 Regular',        color: 'bg-gray-100 text-gray-600' },
  bulk:    { label: '🍽️ Bulk/Catering',  color: 'bg-amber-100 text-amber-700' },
  dine_in: { label: '🪑 Dine-in',        color: 'bg-teal-100 text-teal-700' },
}

const STEPS = [
  { key: 'pending',    label: 'Order Placed', icon: '📋' },
  { key: 'confirmed',  label: 'Confirmed',    icon: '✅' },
  { key: 'processing', label: 'Processing',   icon: '☕' },
  { key: 'delivered',  label: 'Delivered',    icon: '🎉' },
]

const FILTERS = ['All', 'Pending', 'Confirmed', 'Processing', 'Delivered', 'Cancelled']

const Orders = () => {
  const [orders,   setOrders]   = useState([])
  const [loading,  setLoading]  = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [filter,   setFilter]   = useState('All')

  useEffect(() => { fetchOrders() }, [])

  const fetchOrders = async () => {
    setLoading(true)
    try {
      const res = await getOrders()
      setOrders(res.data)
    } catch (err) {
      console.error('Failed to fetch orders', err)
    } finally {
      setLoading(false)
    }
  }

  const filteredOrders = filter === 'All'
    ? orders
    : orders.filter(o => o.status === filter.toLowerCase())

  return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0]'>

      {/* Header Banner */}
      <div className='bg-[#3D1F00] px-6 sm:px-20 py-8'>
        <div className='flex items-center gap-2 text-[#C4A882]/60 text-xs font-semibold tracking-widest uppercase mb-3'>
          <Link to='/home' className='hover:text-[#C4A882] transition'>Home</Link>
          <span>›</span>
          <span className='text-[#C4A882]'>My Orders</span>
        </div>
        <h1 className='text-white text-3xl font-bold'>
          My <em className='text-[#C4A882] italic font-serif'>Orders</em>
        </h1>
        <p className='text-[#C4A882]/50 text-xs mt-1'>
          {orders.length} order{orders.length !== 1 ? 's' : ''} total
        </p>
      </div>

      {/* Filter Tabs */}
      {!loading && orders.length > 0 && (
        <div className='max-w-4xl mx-auto w-full px-4 sm:px-6 pt-6'>
          <div className='flex gap-2 overflow-x-auto pb-2'>
            {FILTERS.map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-1.5 rounded-full text-xs font-bold whitespace-nowrap transition
                  ${filter === f
                    ? 'bg-[#3D1F00] text-white'
                    : 'bg-white text-[#6f4e37] border border-gray-200 hover:border-[#C4A882]'
                  }`}
              >
                {f}
                {f !== 'All' && (
                  <span className='ml-1 opacity-60'>
                    {orders.filter(o => o.status === f.toLowerCase()).length}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Content */}
      <div className='max-w-4xl mx-auto w-full px-4 sm:px-6 py-6'>

        {loading ? (
          <div className='flex flex-col gap-4'>
            {[1, 2, 3].map(i => (
              <div key={i} className='bg-white rounded-2xl p-5 animate-pulse'>
                <div className='h-4 bg-gray-200 rounded w-1/4 mb-3' />
                <div className='h-3 bg-gray-100 rounded w-1/2' />
              </div>
            ))}
          </div>
        ) : orders.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-20 gap-4'>
            <p className='text-5xl'>☕</p>
            <p className='text-[#2C1503] font-semibold text-lg'>No orders yet</p>
            <p className='text-gray-400 text-sm'>Start shopping to place your first order</p>
            <Link to='/home' className='bg-[#3D1F00] text-white text-sm font-semibold px-6 py-2.5 rounded-xl hover:bg-[#5a2f00] transition'>
              Browse Products
            </Link>
          </div>
        ) : filteredOrders.length === 0 ? (
          <div className='flex flex-col items-center justify-center py-16 gap-3'>
            <p className='text-3xl'>🔍</p>
            <p className='text-gray-400 text-sm'>No {filter.toLowerCase()} orders found</p>
            <button onClick={() => setFilter('All')} className='text-[#6f4e37] text-xs font-semibold hover:underline'>
              Show all orders
            </button>
          </div>
        ) : (
          <div className='flex flex-col gap-4'>
            {filteredOrders.map((order) => {
              const status      = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending
              const isExpanded  = expanded === order.id
              const isCancelled = order.status === 'cancelled'
              const progressPct = ((status.step - 1) / (STEPS.length - 1)) * 100
              const orderType   = ORDER_TYPE_CONFIG[order.order_type] || ORDER_TYPE_CONFIG.regular
              const payStatus   = PAYMENT_STATUS_CONFIG[order.payment_status] || PAYMENT_STATUS_CONFIG.unpaid

              return (
                <div key={order.id} className='bg-white rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-shadow'>

                  {/* Order Header */}
                  <div
                    className='flex items-center justify-between p-5 cursor-pointer'
                    onClick={() => setExpanded(isExpanded ? null : order.id)}
                  >
                    <div className='flex flex-col gap-1.5'>
                      <div className='flex items-center gap-2 flex-wrap'>
                        <span className='text-[#2C1503] font-bold text-sm'>
                          #CC-{String(order.id).padStart(5, '0')}
                        </span>
                        <span className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full ${status.color}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
                          {status.label}
                        </span>
                        <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${orderType.color}`}>
                          {orderType.label}
                        </span>
                      </div>
                      <p className='text-gray-400 text-xs'>
                        {new Date(order.created_at).toLocaleDateString('en-PH', {
                          year: 'numeric', month: 'long', day: 'numeric'
                        })}
                      </p>
                    </div>

                    <div className='flex items-center gap-4'>
                      <div className='text-right'>
                        <p className='text-[#2C1503] font-bold text-sm'>
                          ₱{parseFloat(order.total_price).toFixed(2)}
                        </p>
                        <p className='text-gray-400 text-xs'>
                          {order.item_count} item{order.item_count !== 1 ? 's' : ''}
                        </p>
                      </div>
                      <span className={`text-gray-400 text-lg transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}>
                        ↓
                      </span>
                    </div>
                  </div>

                  {/* Expanded Content */}
                  {isExpanded && (
                    <div className='border-t border-gray-100 px-5 pb-5'>

                      {/* Progress Tracker */}
                      {!isCancelled ? (
                        <div className='py-6'>
                          <div className='relative flex items-start justify-between'>
                            <div className='absolute top-5 left-5 right-5 h-0.5 bg-gray-200' />
                            <div
                              className='absolute top-5 left-5 h-0.5 bg-[#6f4e37] transition-all duration-500'
                              style={{ width: `calc(${progressPct}% - 2.5rem)` }}
                            />
                            {STEPS.map((step) => {
                              const stepConfig  = STATUS_CONFIG[step.key]
                              const isCompleted = status.step > stepConfig.step
                              const isCurrent   = status.step === stepConfig.step
                              return (
                                <div key={step.key} className='flex flex-col items-center gap-2 z-10 w-16'>
                                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-base border-2 transition-all duration-300
                                    ${isCompleted
                                      ? 'bg-[#6f4e37] border-[#6f4e37] text-white'
                                      : isCurrent
                                        ? 'bg-white border-[#6f4e37] shadow-md scale-110'
                                        : 'bg-white border-gray-200'
                                    }`}
                                  >
                                    {isCompleted ? '✓' : step.icon}
                                  </div>
                                  <span className={`text-xs font-semibold text-center leading-tight
                                    ${isCurrent || isCompleted ? 'text-[#6f4e37]' : 'text-gray-300'}`}
                                  >
                                    {step.label}
                                  </span>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      ) : (
                        <div className='flex items-center gap-2 bg-red-50 rounded-xl px-4 py-3 my-4'>
                          <span className='text-lg'>❌</span>
                          <p className='text-red-600 text-sm font-semibold'>This order has been cancelled.</p>
                        </div>
                      )}

                      {/* Bulk Order Details */}
                      {order.order_type === 'bulk' && (
                        <div className='bg-amber-50 border border-amber-200 rounded-xl p-4 mb-4'>
                          <p className='text-amber-700 text-xs font-bold uppercase tracking-wide mb-2'>🍽️ Bulk Order Details</p>
                          <div className='grid grid-cols-2 gap-2'>
                            {order.event_date && (
                              <div>
                                <p className='text-amber-600/70 text-xs'>Event Date</p>
                                <p className='text-amber-800 text-sm font-semibold'>
                                  {new Date(order.event_date).toLocaleDateString('en-PH', { month: 'long', day: 'numeric', year: 'numeric' })}
                                </p>
                              </div>
                            )}
                            {order.pax > 0 && (
                              <div>
                                <p className='text-amber-600/70 text-xs'>Pax</p>
                                <p className='text-amber-800 text-sm font-semibold'>{order.pax} persons</p>
                              </div>
                            )}
                            {parseFloat(order.downpayment_amount) > 0 && (
                              <>
                                <div>
                                  <p className='text-amber-600/70 text-xs'>Downpayment (50%)</p>
                                  <p className='text-amber-800 text-sm font-semibold'>₱{parseFloat(order.downpayment_amount).toFixed(2)}</p>
                                </div>
                                <div>
                                  <p className='text-amber-600/70 text-xs'>Remaining Balance</p>
                                  <p className='text-amber-800 text-sm font-semibold'>₱{parseFloat(order.remaining_balance).toFixed(2)}</p>
                                </div>
                              </>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Dine-in Details */}
                      {order.order_type === 'dine_in' && (
                        <div className='bg-teal-50 border border-teal-200 rounded-xl p-4 mb-4'>
                          <p className='text-teal-700 text-xs font-bold uppercase tracking-wide mb-1'>🪑 Dine-in Order</p>
                          <p className='text-teal-800 text-sm font-semibold'>Table {order.table_number || order.address?.replace('Table ', '')}</p>
                          <p className='text-teal-600/70 text-xs mt-1'>Pay at the counter after your meal.</p>
                        </div>
                      )}

                      {/* Order Items */}
                      <div className='flex flex-col gap-2 mb-4'>
                        <p className='text-[#2C1503] text-xs font-semibold uppercase tracking-wide mb-1'>Items</p>
                        {order.items?.map((item) => (
                          <div key={item.id} className='flex items-center gap-3 bg-[#FAF6F0] rounded-xl p-3'>
                            <div className='w-12 h-12 rounded-lg overflow-hidden shrink-0 bg-gray-200'>
                              {item.product_image && (
                                <img src={item.product_image} alt={item.product_name} className='w-full h-full object-cover' />
                              )}
                            </div>
                            <div className='flex-1'>
                              <p className='text-[#2C1503] text-sm font-semibold'>{item.product_name}</p>
                              {item.variant_size && (
                                <p className='text-gray-400 text-xs capitalize'>{item.variant_size}</p>
                              )}
                            </div>
                            <div className='text-right'>
                              <p className='text-[#2C1503] text-sm font-bold'>₱{parseFloat(item.subtotal).toFixed(2)}</p>
                              <p className='text-gray-400 text-xs'>×{item.quantity}</p>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Order Info Grid */}
                      <div className='grid grid-cols-2 gap-3 mb-4'>
                        <div className='bg-[#FAF6F0] rounded-xl p-3'>
                          <p className='text-gray-400 text-xs mb-1'>Payment Method</p>
                          <p className='text-[#2C1503] text-sm font-semibold'>
                            {order.payment_method === 'cod'     ? '🏦 Cash on Delivery'
                            : order.payment_method === 'gcash'  ? '📱 GCash'
                            : '🏪 Pay at Counter'}
                          </p>
                        </div>
                        <div className='bg-[#FAF6F0] rounded-xl p-3'>
                          <p className='text-gray-400 text-xs mb-1'>Payment Status</p>
                          <p className={`text-sm font-semibold ${payStatus.color}`}>
                            {payStatus.label}
                          </p>
                        </div>
                        {order.order_type !== 'dine_in' && (
                          <div className='bg-[#FAF6F0] rounded-xl p-3 col-span-2'>
                            <p className='text-gray-400 text-xs mb-1'>Delivery Address</p>
                            <p className='text-[#2C1503] text-sm font-semibold'>{order.address}</p>
                          </div>
                        )}
                        {order.notes && (
                          <div className='bg-[#FAF6F0] rounded-xl p-3 col-span-2'>
                            <p className='text-gray-400 text-xs mb-1'>Notes</p>
                            <p className='text-[#2C1503] text-sm'>{order.notes}</p>
                          </div>
                        )}
                        {order.points_earned > 0 && (
                          <div className='bg-green-50 rounded-xl p-3 col-span-2'>
                            <p className='text-green-600 text-xs font-semibold'>
                              🎉 +{order.points_earned} loyalty points earned from this order!
                            </p>
                          </div>
                        )}
                      </div>

                      {/* Total */}
                      <div className='flex justify-between items-center border-t border-gray-100 pt-4'>
                        <p className='text-gray-500 text-sm font-semibold'>Total</p>
                        <p className='text-[#2C1503] font-bold text-lg'>
                          ₱{parseFloat(order.total_price).toFixed(2)}
                        </p>
                      </div>

                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

export default Orders