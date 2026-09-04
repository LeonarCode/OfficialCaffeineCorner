import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRiderOrders, getRiderStats } from '../../services/riderService.js'

const ORDER_TYPE_ICON = { regular: '📦', bulk: '🍽️', dine_in: '🪑' }

const RiderDashboard = () => {
  const [orders, setOrders] = useState([])
  const [stats,  setStats]  = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    if (!localStorage.getItem('rider_access')) { navigate('/rider/login'); return }
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const [ordersRes, statsRes] = await Promise.all([getRiderOrders(), getRiderStats()])
      setOrders(ordersRes.data)
      setStats(statsRes.data)
    } catch (err) {
      if (err.response?.status === 403) {
        localStorage.removeItem('rider_access')
        navigate('/rider/login')
      }
    } finally { setLoading(false) }
  }

  const handleLogout = () => {
    localStorage.removeItem('rider_access')
    localStorage.removeItem('rider_refresh')
    navigate('/rider/login')
  }

  return (
    <div className='min-h-screen bg-[#FAF6F0] pb-6'>

      {/* Header */}
      <div className='bg-[#2C1503] px-5 py-6 sticky top-0 z-10'>
        <div className='flex items-center justify-between mb-4'>
          <div>
            <p className='text-[#C4A882]/60 text-xs uppercase tracking-widest'>Rider Portal</p>
            <h1 className='text-white text-lg font-bold'>{stats?.rider_name || 'Loading...'}</h1>
          </div>
          <button onClick={handleLogout} className='text-white/40 text-xs border border-white/20 px-3 py-1.5 rounded-full'>
            Logout
          </button>
        </div>

        {stats && (
          <div className='grid grid-cols-3 gap-2'>
            <div className='bg-white/10 rounded-xl p-3 text-center'>
              <p className='text-white text-xl font-bold'>{stats.pending_count}</p>
              <p className='text-[#C4A882]/50 text-[10px]'>Pending</p>
            </div>
            <div className='bg-white/10 rounded-xl p-3 text-center'>
              <p className='text-white text-xl font-bold'>{stats.delivered_today}</p>
              <p className='text-[#C4A882]/50 text-[10px]'>Today</p>
            </div>
            <div className='bg-white/10 rounded-xl p-3 text-center'>
              <p className='text-white text-xl font-bold'>{stats.delivered_total}</p>
              <p className='text-[#C4A882]/50 text-[10px]'>All Time</p>
            </div>
          </div>
        )}
      </div>

      {/* Orders List */}
      <div className='px-4 pt-4'>
        <p className='text-[#2C1503] font-semibold text-sm mb-3'>My Deliveries ({orders.length})</p>

        {loading ? (
          <div className='flex flex-col gap-3'>
            {[1,2].map(i => <div key={i} className='h-24 bg-white rounded-2xl animate-pulse' />)}
          </div>
        ) : orders.length === 0 ? (
          <div className='text-center py-16'>
            <p className='text-3xl mb-2'>🏍️</p>
            <p className='text-gray-400 text-sm'>No assigned deliveries right now.</p>
          </div>
        ) : (
          <div className='flex flex-col gap-3'>
            {orders.map(order => (
              <button
                key={order.id}
                onClick={() => navigate(`/rider/order/${order.id}`)}
                className='w-full bg-white rounded-2xl p-4 shadow-sm text-left active:scale-[0.98] transition'
              >
                <div className='flex items-center justify-between mb-2'>
                  <div className='flex items-center gap-2'>
                    <span className='text-lg'>{ORDER_TYPE_ICON[order.order_type] || '📦'}</span>
                    <span className='text-[#2C1503] font-bold text-sm'>#CC-{String(order.id).padStart(5, '0')}</span>
                  </div>
                  <span className='text-[#6f4e37] font-bold text-sm'>₱{parseFloat(order.total_price).toFixed(2)}</span>
                </div>
                <p className='text-gray-500 text-xs mb-1'>📍 {order.address}</p>
                <p className='text-gray-400 text-xs'>📞 {order.phone}</p>
                {order.zone_name && (
                  <span className='inline-block mt-2 text-[10px] bg-[#FAF6F0] text-[#6f4e37] px-2 py-0.5 rounded-full font-semibold'>
                    {order.zone_name}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default RiderDashboard