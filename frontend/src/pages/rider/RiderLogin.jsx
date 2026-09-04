import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { riderLogin } from '../../services/authService.js'

const RiderLogin = () => {
  const [email,     setEmail]     = useState('')
  const [password,  setPassword]  = useState('')
  const [showPass,  setShowPass]  = useState(false)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState('')
  const navigate = useNavigate()

  const handleLogin = async () => {
    if (!email || !password) return
    setLoading(true)
    setError('')
    try {
      const res = await riderLogin(email, password)
      localStorage.setItem('rider_access',  res.data.access)
      localStorage.setItem('rider_refresh', res.data.refresh)
      localStorage.setItem('rider_name',    res.data.rider_name)
      navigate('/rider/dashboard')
    } catch (err) {
      setError(err.response?.data?.non_field_errors?.[0] || err.response?.data?.error || 'Login failed. Please check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className='min-h-screen bg-[#2C1503] flex items-center justify-center p-5'>
      <div className='w-full max-w-sm bg-white/5 backdrop-blur-xl rounded-3xl p-6 border border-white/10'>

        <div className='text-center mb-6'>
          <div className='w-16 h-16 bg-[#C4A882] rounded-2xl flex items-center justify-center mx-auto mb-3 text-2xl'>
            🏍️
          </div>
          <h1 className='text-white text-xl font-bold'>Rider Portal</h1>
          <p className='text-[#C4A882]/60 text-xs mt-1'>Caffeine Corner Delivery</p>
        </div>

        {error && (
          <div className='bg-red-500/20 border border-red-400/30 rounded-xl px-4 py-2.5 mb-4'>
            <p className='text-red-200 text-xs text-center'>{error}</p>
          </div>
        )}

        <div className='flex flex-col gap-3'>
          <div>
            <label className='text-[#C4A882]/60 text-xs font-semibold uppercase mb-1.5 block'>Email</label>
            <input
              type='email'
              placeholder='rider@caffeinecorner.com'
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
              className='w-full bg-white/10 border border-white/15 rounded-xl px-4 py-3 text-white text-sm placeholder:text-white/30 outline-none focus:border-[#C4A882]/60'
            />
          </div>

          <div>
            <label className='text-[#C4A882]/60 text-xs font-semibold uppercase mb-1.5 block'>Password</label>
            <div className='relative'>
              <input
                type={showPass ? 'text' : 'password'}
                placeholder='••••••••'
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleLogin()}
                className='w-full bg-white/10 border border-white/15 rounded-xl px-4 py-3 pr-11 text-white text-sm placeholder:text-white/30 outline-none focus:border-[#C4A882]/60'
              />
              <button
                type='button'
                onClick={() => setShowPass(!showPass)}
                className='absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/70 text-xs'
              >
                {showPass ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <button
            onClick={handleLogin}
            disabled={loading || !email || !password}
            className='w-full flex items-center justify-center gap-2 bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 disabled:cursor-not-allowed text-[#2C1503] font-bold text-sm py-3.5 rounded-xl transition mt-2'
          >
            {loading ? (
              <span className='flex items-center gap-2'>
                <svg className='animate-spin h-4 w-4' viewBox='0 0 24 24' fill='none'>
                  <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'/>
                  <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z'/>
                </svg>
                Signing in...
              </span>
            ) : 'Login'}
          </button>
        </div>

        <p className='text-white/40 text-xs text-center mt-5'>
          Don't have an account?{' '}
          <Link to='/rider/register' className='text-[#C4A882] font-semibold hover:underline'>Register here</Link>
        </p>

      </div>
    </div>
  )
}

export default RiderLogin