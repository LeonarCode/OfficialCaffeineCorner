import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getProfile, updateProfile } from '../services/authService'
import { getOrders, getLoyaltyPoints } from '../services/orderService'
import { useAuth } from '../context/AuthContext'
import {
  HiOutlinePencil, HiOutlineCheck, HiOutlineX,
  HiOutlineShoppingBag, HiOutlineStar, HiOutlineUser,
  HiOutlineLogout, HiOutlineClipboardList
} from 'react-icons/hi'

const STATUS_COLOR = {
  pending:    'bg-yellow-100 text-yellow-700',
  confirmed:  'bg-blue-100 text-blue-700',
  processing: 'bg-purple-100 text-purple-700',
  delivered:  'bg-green-100 text-green-700',
  cancelled:  'bg-red-100 text-red-700',
}

const ORDER_TYPE_ICON = {
  regular: '📦',
  bulk:    '🍽️',
  dine_in: '🪑',
}

const Profile = () => {
  const [profile,  setProfile]  = useState(null)
  const [orders,   setOrders]   = useState([])
  const [loyalty,  setLoyalty]  = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [editing,  setEditing]  = useState(false)
  const [username, setUsername] = useState('')
  const [saving,   setSaving]   = useState(false)
  const [activeTab,setActiveTab]= useState('overview')
  const { logout } = useAuth()
  const navigate   = useNavigate()

  useEffect(() => { fetchAll() }, [])

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [profileRes, ordersRes, loyaltyRes] = await Promise.all([
        getProfile(), getOrders(), getLoyaltyPoints(),
      ])
      setProfile(profileRes.data)
      setUsername(profileRes.data.username || '')
      setOrders(ordersRes.data)
      setLoyalty(loyaltyRes.data)
    } catch (err) {
      console.error('Failed to fetch profile', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await updateProfile({ username })
      setProfile(res.data)
      setEditing(false)
    } catch (err) {
      console.error('Failed to update profile', err)
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = () => { logout(); navigate('/signin') }

  const totalSpent    = orders.filter(o => o.payment_status === 'paid').reduce((s, o) => s + parseFloat(o.total_price), 0)
  const deliveredCount = orders.filter(o => o.status === 'delivered').length

  if (loading) return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0]'>
      <div className='bg-[#3D1F00] h-48 animate-pulse' />
      <div className='max-w-4xl mx-auto w-full px-6 py-10 flex flex-col gap-4'>
        {[1,2,3].map(i => <div key={i} className='h-24 bg-white rounded-2xl animate-pulse' />)}
      </div>
    </div>
  )

  return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0]'>

      {/* Header Banner */}
      <div className='bg-[#3D1F00] px-6 sm:px-20 py-8 relative overflow-hidden'>
        <div className='absolute inset-0 bg-[radial-gradient(ellipse_at_80%_50%,rgba(196,168,130,0.10)_0%,transparent_70%)]' />
        <div className='flex items-center gap-2 text-[#C4A882]/60 text-xs font-semibold tracking-widest uppercase mb-6'>
          <Link to='/home' className='hover:text-[#C4A882] transition'>Home</Link>
          <span>›</span>
          <span className='text-[#C4A882]'>My Profile</span>
        </div>

        {/* Profile Hero */}
        <div className='flex flex-col sm:flex-row items-start sm:items-center gap-5 relative z-10'>
          {/* Avatar */}
          <div className='relative'>
            <div className='w-20 h-20 rounded-full bg-[#C4A882]/20 border-2 border-[#C4A882]/40 flex items-center justify-center'>
              <span className='text-[#C4A882] text-3xl font-bold'>
                {profile?.email?.[0]?.toUpperCase()}
              </span>
            </div>
            <div className='absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-green-400 border-2 border-[#3D1F00]' />
          </div>

          <div className='flex-1'>
            <h1 className='text-white text-2xl font-bold'>
              {profile?.username || 'Coffee Lover'}
            </h1>
            <p className='text-[#C4A882]/60 text-xs mt-0.5'>{profile?.email}</p>
            <p className='text-[#C4A882]/40 text-xs mt-1'>
              Member since {new Date(profile?.date_joined).toLocaleDateString('en-PH', { month: 'long', year: 'numeric' })}
            </p>
          </div>

          {/* Quick Stats */}
          <div className='flex gap-3 flex-wrap'>
            {[
              { label: 'Orders',    value: orders.length,                  icon: '📦' },
              { label: 'Delivered', value: deliveredCount,                 icon: '✅' },
              { label: 'Points',    value: loyalty?.points || 0,           icon: '⭐' },
              { label: 'Spent',     value: `₱${totalSpent.toFixed(0)}`,   icon: '💰' },
            ].map(stat => (
              <div key={stat.label} className='bg-white/10 rounded-xl px-3 py-2 text-center min-w-16'>
                <p className='text-lg leading-none mb-0.5'>{stat.icon}</p>
                <p className='text-white text-sm font-bold'>{stat.value}</p>
                <p className='text-[#C4A882]/50 text-[10px]'>{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className='bg-white border-b border-gray-100 sticky top-0 z-30'>
        <div className='max-w-4xl mx-auto px-4 sm:px-6 flex gap-0'>
          {[
            { key: 'overview', label: 'Overview',      icon: <HiOutlineUser size={14} /> },
            { key: 'orders',   label: 'Orders',        icon: <HiOutlineClipboardList size={14} /> },
            { key: 'loyalty',  label: 'Loyalty',       icon: <HiOutlineStar size={14} /> },
            { key: 'settings', label: 'Settings',      icon: <HiOutlinePencil size={14} /> },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-3.5 text-xs font-semibold border-b-2 transition -mb-px
                ${activeTab === tab.key
                  ? 'border-[#3D1F00] text-[#2C1503]'
                  : 'border-transparent text-gray-400 hover:text-gray-600'
                }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className='max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 flex flex-col gap-5'>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <>
            {/* Loyalty Summary */}
            {loyalty && (
              <div className='bg-[#3D1F00] rounded-2xl p-5 shadow-sm'>
                <div className='flex items-center justify-between mb-4'>
                  <div>
                    <p className='text-[#C4A882]/60 text-xs uppercase tracking-widest mb-0.5'>Loyalty Status</p>
                    <p className='text-white font-bold text-lg'>
                      {loyalty.points >= 500 ? '🥇 Gold Member' : loyalty.points >= 200 ? '🥈 Silver Member' : '☕ Regular Member'}
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveTab('loyalty')}
                    className='text-[#C4A882] text-xs font-semibold hover:underline'
                  >
                    View details →
                  </button>
                </div>

                {/* Points Progress */}
                <div className='mb-3'>
                  <div className='flex justify-between text-xs mb-1'>
                    <span className='text-[#C4A882]/60'>{loyalty.points} pts</span>
                    <span className='text-[#C4A882]/60'>
                      {loyalty.points < 200 ? `${200 - loyalty.points} pts to Silver` :
                       loyalty.points < 500 ? `${500 - loyalty.points} pts to Gold` : '🥇 Max Level'}
                    </span>
                  </div>
                  <div className='h-2 bg-white/10 rounded-full overflow-hidden'>
                    <div
                      className='h-full bg-[#C4A882] rounded-full transition-all duration-500'
                      style={{ width: `${Math.min((loyalty.points / 500) * 100, 100)}%` }}
                    />
                  </div>
                </div>

                <div className='grid grid-cols-3 gap-3'>
                  {[
                    { label: 'Total Points',   value: loyalty.points },
                    { label: 'Redeemable',     value: loyalty.redeemable_points },
                    { label: 'Cash Value',     value: `₱${loyalty.discount_value}` },
                  ].map(({ label, value }) => (
                    <div key={label} className='bg-white/10 rounded-xl p-3 text-center'>
                      <p className='text-[#C4A882]/50 text-[10px] mb-1'>{label}</p>
                      <p className='text-white font-bold text-lg'>{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recent Orders */}
            <div className='bg-white rounded-2xl p-5 shadow-sm'>
              <div className='flex items-center justify-between mb-4'>
                <h2 className='text-[#2C1503] font-semibold text-sm'>Recent Orders</h2>
                <button onClick={() => setActiveTab('orders')} className='text-[#6f4e37] text-xs font-semibold hover:underline'>
                  View all →
                </button>
              </div>
              {orders.length === 0 ? (
                <div className='text-center py-8'>
                  <p className='text-3xl mb-2'>☕</p>
                  <p className='text-gray-400 text-sm'>No orders yet</p>
                  <Link to='/home' className='text-[#6f4e37] text-xs font-semibold hover:underline mt-1 block'>
                    Start shopping →
                  </Link>
                </div>
              ) : (
                <div className='flex flex-col gap-2'>
                  {orders.slice(0, 3).map(order => (
                    <div key={order.id} className='flex items-center justify-between bg-[#FAF6F0] rounded-xl px-4 py-3 hover:bg-[#f0e8df] transition'>
                      <div className='flex items-center gap-3'>
                        <span className='text-lg'>{ORDER_TYPE_ICON[order.order_type] || '📦'}</span>
                        <div>
                          <p className='text-[#2C1503] text-sm font-semibold'>#CC-{String(order.id).padStart(5, '0')}</p>
                          <p className='text-gray-400 text-xs'>
                            {new Date(order.created_at).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })}
                          </p>
                        </div>
                      </div>
                      <div className='flex items-center gap-2'>
                        <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${STATUS_COLOR[order.status]}`}>
                          {order.status}
                        </span>
                        <p className='text-[#2C1503] text-sm font-bold'>₱{parseFloat(order.total_price).toFixed(2)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Quick Links */}
            <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
              {[
                { label: 'Browse Menu',    icon: '☕', to: '/home' },
                { label: 'My Orders',      icon: '📋', to: '/orders' },
                { label: 'Cart',           icon: '🛒', to: '/cart' },
                { label: 'Checkout',       icon: '💳', to: '/checkout' },
              ].map(link => (
                <Link
                  key={link.label}
                  to={link.to}
                  className='bg-white rounded-2xl p-4 text-center shadow-sm hover:shadow-md transition hover:bg-[#FAF6F0]'
                >
                  <p className='text-2xl mb-1'>{link.icon}</p>
                  <p className='text-[#2C1503] text-xs font-semibold'>{link.label}</p>
                </Link>
              ))}
            </div>
          </>
        )}

        {/* Orders Tab */}
        {activeTab === 'orders' && (
          <div className='bg-white rounded-2xl p-5 shadow-sm'>
            <div className='flex items-center justify-between mb-4'>
              <h2 className='text-[#2C1503] font-semibold text-sm'>All Orders ({orders.length})</h2>
              <Link to='/orders' className='text-[#6f4e37] text-xs font-semibold hover:underline'>
                Full View →
              </Link>
            </div>
            {orders.length === 0 ? (
              <div className='text-center py-8'>
                <p className='text-3xl mb-2'>📦</p>
                <p className='text-gray-400 text-sm'>No orders yet</p>
              </div>
            ) : (
              <div className='flex flex-col gap-2'>
                {orders.map(order => (
                  <div key={order.id} className='flex items-center justify-between bg-[#FAF6F0] rounded-xl px-4 py-3'>
                    <div className='flex items-center gap-3'>
                      <span className='text-lg'>{ORDER_TYPE_ICON[order.order_type] || '📦'}</span>
                      <div>
                        <p className='text-[#2C1503] text-sm font-semibold'>#CC-{String(order.id).padStart(5, '0')}</p>
                        <p className='text-gray-400 text-xs'>
                          {order.item_count} item{order.item_count !== 1 ? 's' : ''} · {new Date(order.created_at).toLocaleDateString('en-PH', { month: 'short', day: 'numeric' })}
                        </p>
                      </div>
                    </div>
                    <div className='flex items-center gap-2 flex-wrap justify-end'>
                      <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${STATUS_COLOR[order.status]}`}>
                        {order.status}
                      </span>
                      <p className='text-[#2C1503] text-sm font-bold'>₱{parseFloat(order.total_price).toFixed(2)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Loyalty Tab */}
        {activeTab === 'loyalty' && loyalty && (
          <>
            <div className='bg-[#3D1F00] rounded-2xl p-6 shadow-sm'>
              <p className='text-[#C4A882]/60 text-xs uppercase tracking-widest mb-1'>Your Status</p>
              <p className='text-white text-2xl font-bold mb-4'>
                {loyalty.points >= 500 ? '🥇 Gold Member' : loyalty.points >= 200 ? '🥈 Silver Member' : '☕ Regular Member'}
              </p>

              <div className='h-3 bg-white/10 rounded-full overflow-hidden mb-2'>
                <div
                  className='h-full bg-gradient-to-r from-[#C4A882] to-amber-400 rounded-full transition-all duration-700'
                  style={{ width: `${Math.min((loyalty.points / 500) * 100, 100)}%` }}
                />
              </div>
              <div className='flex justify-between text-xs text-[#C4A882]/40 mb-6'>
                <span>0</span><span>Silver (200)</span><span>Gold (500)</span>
              </div>

              <div className='grid grid-cols-3 gap-3'>
                {[
                  { label: 'Total Points',   value: loyalty.points, icon: '⭐' },
                  { label: 'Redeemable',     value: loyalty.redeemable_points, icon: '🎁' },
                  { label: 'Cash Value',     value: `₱${loyalty.discount_value}`, icon: '💰' },
                ].map(({ label, value, icon }) => (
                  <div key={label} className='bg-white/10 rounded-xl p-4 text-center'>
                    <p className='text-2xl mb-1'>{icon}</p>
                    <p className='text-white font-bold text-xl'>{value}</p>
                    <p className='text-[#C4A882]/50 text-xs mt-0.5'>{label}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className='bg-white rounded-2xl p-5 shadow-sm'>
              <h3 className='text-[#2C1503] font-semibold text-sm mb-4'>How Points Work</h3>
              <div className='flex flex-col gap-3'>
                {[
                  { icon: '🛒', title: 'Earn Points',    desc: 'Get 1 point for every ₱10 spent on orders' },
                  { icon: '🎁', title: 'Redeem Points',  desc: '100 points = ₱10 discount on your next order' },
                  { icon: '🥇', title: 'Level Up',       desc: 'Reach 200 pts for Silver, 500 pts for Gold status' },
                ].map(item => (
                  <div key={item.title} className='flex items-start gap-3 bg-[#FAF6F0] rounded-xl p-4'>
                    <span className='text-xl shrink-0'>{item.icon}</span>
                    <div>
                      <p className='text-[#2C1503] text-sm font-semibold'>{item.title}</p>
                      <p className='text-gray-400 text-xs mt-0.5'>{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <>
            <div className='bg-white rounded-2xl p-5 shadow-sm'>
              <div className='flex items-start justify-between mb-4'>
                <h2 className='text-[#2C1503] font-semibold text-sm'>Account Info</h2>
                {!editing ? (
                  <button
                    onClick={() => setEditing(true)}
                    className='flex items-center gap-1 text-[#6f4e37] text-xs font-semibold hover:underline'
                  >
                    <HiOutlinePencil size={14} /> Edit
                  </button>
                ) : (
                  <div className='flex gap-2'>
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className='flex items-center gap-1 bg-[#3D1F00] text-white text-xs font-semibold px-3 py-1.5 rounded-lg'
                    >
                      <HiOutlineCheck size={14} /> {saving ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={() => { setEditing(false); setUsername(profile.username || '') }}
                      className='flex items-center gap-1 border border-gray-200 text-gray-500 text-xs font-semibold px-3 py-1.5 rounded-lg'
                    >
                      <HiOutlineX size={14} /> Cancel
                    </button>
                  </div>
                )}
              </div>
              <div className='flex flex-col gap-3'>
                <div>
                  <label className='text-gray-400 text-xs uppercase tracking-wide font-semibold block mb-1'>Email</label>
                  <p className='text-[#2C1503] text-sm bg-gray-50 rounded-xl px-4 py-2.5 border border-gray-100'>{profile?.email}</p>
                </div>
                <div>
                  <label className='text-gray-400 text-xs uppercase tracking-wide font-semibold block mb-1'>Username</label>
                  {editing ? (
                    <input
                      type='text'
                      value={username}
                      onChange={e => setUsername(e.target.value)}
                      className='w-full text-[#2C1503] text-sm bg-[#FAF6F0] rounded-xl px-4 py-2.5 border border-[#C4A882] outline-none'
                      placeholder='Enter username'
                    />
                  ) : (
                    <p className='text-[#2C1503] text-sm bg-gray-50 rounded-xl px-4 py-2.5 border border-gray-100'>
                      {profile?.username || <span className='text-gray-300'>Not set</span>}
                    </p>
                  )}
                </div>
                <div>
                  <label className='text-gray-400 text-xs uppercase tracking-wide font-semibold block mb-1'>Member Since</label>
                  <p className='text-[#2C1503] text-sm bg-gray-50 rounded-xl px-4 py-2.5 border border-gray-100'>
                    {new Date(profile?.date_joined).toLocaleDateString('en-PH', { year: 'numeric', month: 'long', day: 'numeric' })}
                  </p>
                </div>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className='w-full flex items-center justify-center gap-2 border border-red-200 text-red-500 font-semibold text-sm py-3 rounded-xl hover:bg-red-50 transition'
            >
              <HiOutlineLogout size={16} /> Sign Out
            </button>
          </>
        )}

      </div>
    </div>
  )
}

export default Profile