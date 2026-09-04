import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { riderRegister } from '../../services/authService.js'

const RiderRegister = () => {
  const [form, setForm] = useState({
    email: '', username: '', phone: '', password: '', confirm_password: ''
  })
  const [loading, setLoading]   = useState(false)
  const [errors, setErrors]     = useState({})
  const [success, setSuccess]   = useState(false)
  const navigate = useNavigate()

  const validatePhone = (phone) => /^(09\d{9}|\+639\d{9})$/.test(phone.replace(/[\s\-]/g, ''))

  const validate = () => {
    const e = {}
    if (!form.email) e.email = 'Email is required'
    if (!form.username) e.username = 'Username is required'
    if (!form.phone) {
      e.phone = 'Phone number is required'
    } else if (!validatePhone(form.phone)) {
      e.phone = 'Enter a valid Philippine mobile number'
    }
    if (!form.password) {
      e.password = 'Password is required'
    } else if (form.password.length < 8) {
      e.password = 'Password must be at least 8 characters'
    }
    if (form.password !== form.confirm_password) {
      e.confirm_password = 'Passwords do not match'
    }
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    setLoading(true)
    try {
      await riderRegister({
        ...form,
        phone: form.phone.replace(/[\s\-]/g, ''),
      })
      setSuccess(true)
    } catch (err) {
      const data = err.response?.data
      if (data) setErrors(data)
    } finally {
      setLoading(false)
    }
  }

  if (success) return (
    <div className='min-h-screen bg-[#2C1503] flex items-center justify-center p-5'>
      <div className='w-full max-w-sm bg-white/5 backdrop-blur-xl rounded-3xl p-6 border border-white/10 text-center'>
        <div className='text-5xl mb-4'>⏳</div>
        <h1 className='text-white text-xl font-bold mb-2'>Registration Submitted!</h1>
        <p className='text-[#C4A882]/60 text-sm leading-relaxed mb-6'>
          Your rider application is pending admin approval. You'll be able to log in once approved.
        </p>
        <Link to='/rider/login' className='block w-full bg-[#C4A882] text-[#2C1503] font-bold text-sm py-3 rounded-xl'>
          Back to Login
        </Link>
      </div>
    </div>
  )

  return (
    <div className='min-h-screen bg-[#2C1503] flex items-center justify-center p-5'>
      <div className='w-full max-w-sm bg-white/5 backdrop-blur-xl rounded-3xl p-6 border border-white/10'>

        <div className='text-center mb-6'>
          <div className='w-16 h-16 bg-[#C4A882] rounded-2xl flex items-center justify-center mx-auto mb-3 text-2xl'>
            🏍️
          </div>
          <h1 className='text-white text-xl font-bold'>Become a Rider</h1>
          <p className='text-[#C4A882]/60 text-xs mt-1'>Caffeine Corner Delivery</p>
        </div>

        <div className='flex flex-col gap-3'>
          <div>
            <input
              type='text'
              placeholder='Full Name'
              value={form.username}
              onChange={e => { setForm({ ...form, username: e.target.value }); setErrors(p => ({ ...p, username: '' })) }}
              className={`w-full bg-white/10 border rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/30 outline-none
                ${errors.username ? 'border-red-400' : 'border-white/15 focus:border-[#C4A882]/60'}`}
            />
            {errors.username && <p className='text-red-300 text-xs mt-1'>{errors.username}</p>}
          </div>

          <div>
            <input
              type='email'
              placeholder='Email Address'
              value={form.email}
              onChange={e => { setForm({ ...form, email: e.target.value }); setErrors(p => ({ ...p, email: '' })) }}
              className={`w-full bg-white/10 border rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/30 outline-none
                ${errors.email ? 'border-red-400' : 'border-white/15 focus:border-[#C4A882]/60'}`}
            />
            {errors.email && <p className='text-red-300 text-xs mt-1'>{errors.email[0] || errors.email}</p>}
          </div>

          <div>
            <input
              type='tel'
              inputMode='numeric'
              placeholder='Phone Number (09XXXXXXXXX)'
              value={form.phone}
              onChange={e => { setForm({ ...form, phone: e.target.value.replace(/[^\d+]/g, '') }); setErrors(p => ({ ...p, phone: '' })) }}
              maxLength={13}
              className={`w-full bg-white/10 border rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/30 outline-none
                ${errors.phone ? 'border-red-400' : 'border-white/15 focus:border-[#C4A882]/60'}`}
            />
            {errors.phone && <p className='text-red-300 text-xs mt-1'>{errors.phone}</p>}
          </div>

          <div>
            <input
              type='password'
              placeholder='Password (min. 8 characters)'
              value={form.password}
              onChange={e => { setForm({ ...form, password: e.target.value }); setErrors(p => ({ ...p, password: '' })) }}
              className={`w-full bg-white/10 border rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/30 outline-none
                ${errors.password ? 'border-red-400' : 'border-white/15 focus:border-[#C4A882]/60'}`}
            />
            {errors.password && <p className='text-red-300 text-xs mt-1'>{errors.password}</p>}
          </div>

          <div>
            <input
              type='password'
              placeholder='Confirm Password'
              value={form.confirm_password}
              onChange={e => { setForm({ ...form, confirm_password: e.target.value }); setErrors(p => ({ ...p, confirm_password: '' })) }}
              className={`w-full bg-white/10 border rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/30 outline-none
                ${errors.confirm_password ? 'border-red-400' : 'border-white/15 focus:border-[#C4A882]/60'}`}
            />
            {errors.confirm_password && <p className='text-red-300 text-xs mt-1'>{errors.confirm_password}</p>}
          </div>

          <button
            onClick={handleSubmit}
            disabled={loading}
            className='w-full flex items-center justify-center gap-2 bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 text-[#2C1503] font-bold text-sm py-3.5 rounded-xl transition mt-2'
          >
            {loading ? 'Submitting...' : 'Register as Rider'}
          </button>
        </div>

        <p className='text-white/40 text-xs text-center mt-5'>
          Already have an account?{' '}
          <Link to='/rider/login' className='text-[#C4A882] font-semibold hover:underline'>Login</Link>
        </p>

      </div>
    </div>
  )
}

export default RiderRegister