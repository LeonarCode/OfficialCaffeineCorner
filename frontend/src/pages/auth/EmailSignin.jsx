import React, { useState, useEffect, useRef } from 'react'
import background from '../../assets/Background.jpeg'
import logo from '../../assets/Logo.jpg'
import { HiOutlineMail, HiArrowRight, HiArrowLeft } from 'react-icons/hi'
import { Link, useNavigate } from 'react-router-dom'
import { sendOTP, verifyOTP } from '../../services/authService.js'
import { useAuth } from '../../context/AuthContext.jsx'

const EmailSignin = () => {
  const [step,    setStep]    = useState('email')
  const [email,   setEmail]   = useState('')
  const [otp,     setOtp]     = useState(['', '', '', '', '', ''])
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [resendCountdown, setResendCountdown] = useState(0)
  const [resending, setResending] = useState(false)
  const { setIsAuthenticated } = useAuth()
  const navigate  = useNavigate()
  const inputRefs = useRef([])

  // Countdown timer for resend
  useEffect(() => {
    if (resendCountdown <= 0) return
    const timer = setTimeout(() => setResendCountdown(c => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [resendCountdown])

  const handleOtpChange = (value, index) => {
    if (!/^\d?$/.test(value)) return
    const newOtp = [...otp]
    newOtp[index] = value
    setOtp(newOtp)
    setError('')
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus()
    }
    // Auto verify when all 6 digits entered
    if (value && index === 5) {
      const fullCode = [...newOtp.slice(0, 5), value].join('')
      if (fullCode.length === 6) {
        setTimeout(() => handleVerifyOtp([...newOtp.slice(0, 5), value]), 200)
      }
    }
  }

  const handleOtpKeyDown = (e, index) => {
    if (e.key === 'Backspace') {
      if (otp[index]) {
        const newOtp = [...otp]
        newOtp[index] = ''
        setOtp(newOtp)
      } else if (index > 0) {
        inputRefs.current[index - 1]?.focus()
      }
    }
    if (e.key === 'ArrowLeft' && index > 0) inputRefs.current[index - 1]?.focus()
    if (e.key === 'ArrowRight' && index < 5) inputRefs.current[index + 1]?.focus()
  }

  const handlePaste = (e) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (!pasted) return
    const newOtp = [...otp]
    pasted.split('').forEach((char, i) => { if (i < 6) newOtp[i] = char })
    setOtp(newOtp)
    inputRefs.current[Math.min(pasted.length, 5)]?.focus()
  }

  const handleSendOtp = async () => {
    if (!email) return
    setError('')
    setLoading(true)
    try {
      await sendOTP(email)
      setStep('otp')
      setResendCountdown(60)
      setTimeout(() => inputRefs.current[0]?.focus(), 300)
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to send code. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyOtp = async (otpOverride = null) => {
    const code = (otpOverride || otp).join('')
    if (code.length < 6) return
    setError('')
    setLoading(true)
    try {
      const res = await verifyOTP(email, code)
      localStorage.setItem('access', res.data.access)
      localStorage.setItem('refresh', res.data.refresh)
      setIsAuthenticated(true)
      navigate('/home')
    } catch (err) {
      setError(err.response?.data?.error || 'Invalid or expired code. Please try again.')
      setOtp(['', '', '', '', '', ''])
      setTimeout(() => inputRefs.current[0]?.focus(), 100)
    } finally {
      setLoading(false)
    }
  }

  const handleResend = async () => {
    if (resendCountdown > 0) return
    setResending(true)
    setError('')
    setOtp(['', '', '', '', '', ''])
    try {
      await sendOTP(email)
      setResendCountdown(60)
      setTimeout(() => inputRefs.current[0]?.focus(), 100)
    } catch (err) {
      setError('Failed to resend code. Please try again.')
    } finally {
      setResending(false)
    }
  }

  const filledCount = otp.filter(d => d !== '').length

  return (
    <div
      className='min-h-screen flex items-center justify-center p-5 relative'
      style={{ backgroundImage: `url(${background})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
    >
      {/* Overlays */}
      <div className='absolute inset-0 bg-black/50' />
      <div className='absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent' />

      <div className='relative z-10 w-full max-w-sm'>

        {/* Back to signin */}
        <Link
          to='/signin'
          className='flex items-center gap-1.5 text-white/40 hover:text-white/70 text-xs mb-4 transition w-fit'
        >
          <HiArrowLeft size={14} /> Back to Sign In
        </Link>

        {/* Logo */}
        <div className='text-center mb-6'>
          <div className='relative inline-block mb-4'>
            <div className='absolute inset-0 rounded-full bg-[#C4A882]/20 blur-xl scale-150' />
            <img src={logo} alt='Caffeine Corner' className='relative h-20 w-20 rounded-full object-cover border-2 border-white/20 shadow-xl' />
          </div>
          <h1 className='text-white text-xl font-bold'>
            {step === 'email' ? 'Sign In with Email' : 'Check Your Email'}
          </h1>
          <p className='text-white/40 text-xs mt-1 tracking-widest uppercase'>
            {step === 'email' ? 'No password needed' : `Code sent to ${email}`}
          </p>
        </div>

        {/* Card */}
        <div className='bg-white/10 backdrop-blur-xl rounded-3xl p-6 border border-white/10 shadow-2xl'>

          {/* Error */}
          {error && (
            <div className='bg-red-500/20 border border-red-400/30 rounded-xl px-4 py-2.5 mb-4 flex items-center gap-2'>
              <span className='text-red-300 text-sm'>⚠️</span>
              <p className='text-red-200 text-xs'>{error}</p>
            </div>
          )}

          {step === 'email' ? (
            <div className='flex flex-col gap-4'>
              <p className='text-white/50 text-xs leading-relaxed text-center'>
                Enter your email address and we'll send you a one-time code — no password needed.
              </p>

              {/* Email Input */}
              <div className={`flex items-center gap-3 bg-white/10 border rounded-2xl px-4 py-3.5 transition
                ${error ? 'border-red-400/50' : 'border-white/15 focus-within:border-[#C4A882]/60'}`}>
                <HiOutlineMail size={16} className='text-[#C4A882] shrink-0' />
                <input
                  type='email'
                  placeholder='your@email.com'
                  value={email}
                  onChange={e => { setEmail(e.target.value); setError('') }}
                  onKeyDown={e => e.key === 'Enter' && handleSendOtp()}
                  autoFocus
                  className='bg-transparent text-white text-sm placeholder:text-white/30 outline-none w-full'
                />
              </div>

              <button
                onClick={handleSendOtp}
                disabled={loading || !email}
                className='w-full flex items-center justify-center gap-2 bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 disabled:cursor-not-allowed text-[#2C1503] font-bold text-sm py-3.5 rounded-2xl transition-all hover:scale-[1.01] shadow-sm'
              >
                {loading ? (
                  <span className='flex items-center gap-2'>
                    <svg className='animate-spin h-4 w-4' viewBox='0 0 24 24' fill='none'>
                      <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'/>
                      <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z'/>
                    </svg>
                    Sending Code...
                  </span>
                ) : (
                  <> Send Code <HiArrowRight size={16} /> </>
                )}
              </button>

              <p className='text-white/30 text-[10px] text-center'>
                We'll send a 6-digit code to your email
              </p>
            </div>
          ) : (
            <div className='flex flex-col gap-4'>
              <p className='text-white/50 text-xs leading-relaxed text-center'>
                Enter the 6-digit code sent to{' '}
                <span className='text-[#C4A882] font-semibold'>{email}</span>
              </p>

              {/* OTP Boxes */}
              <div className='flex gap-2 justify-center' onPaste={handlePaste}>
                {otp.map((digit, i) => (
                  <input
                    key={i}
                    id={`otp-${i}`}
                    ref={el => inputRefs.current[i] = el}
                    type='text'
                    inputMode='numeric'
                    maxLength={1}
                    value={digit}
                    onChange={e => handleOtpChange(e.target.value, i)}
                    onKeyDown={e => handleOtpKeyDown(e, i)}
                    className={`w-11 h-12 text-center font-bold text-lg rounded-xl outline-none transition-all duration-200
                      ${digit
                        ? 'bg-[#C4A882] text-[#2C1503] border-2 border-[#C4A882] scale-105'
                        : 'bg-white/10 text-white border border-white/15 focus:border-[#C4A882]/60 focus:bg-white/15'
                      }`}
                  />
                ))}
              </div>

              {/* Progress dots */}
              <div className='flex justify-center gap-1.5'>
                {[...Array(6)].map((_, i) => (
                  <div
                    key={i}
                    className={`w-1.5 h-1.5 rounded-full transition-all duration-200
                      ${i < filledCount ? 'bg-[#C4A882]' : 'bg-white/20'}`}
                  />
                ))}
              </div>

              {/* Verify Button */}
              <button
                onClick={() => handleVerifyOtp()}
                disabled={loading || filledCount < 6}
                className='w-full flex items-center justify-center gap-2 bg-[#C4A882] hover:bg-[#b8976e] disabled:opacity-50 disabled:cursor-not-allowed text-[#2C1503] font-bold text-sm py-3.5 rounded-2xl transition-all hover:scale-[1.01] shadow-sm'
              >
                {loading ? (
                  <span className='flex items-center gap-2'>
                    <svg className='animate-spin h-4 w-4' viewBox='0 0 24 24' fill='none'>
                      <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'/>
                      <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z'/>
                    </svg>
                    Verifying...
                  </span>
                ) : '✓ Verify & Sign In'}
              </button>

              {/* Resend */}
              <div className='text-center'>
                {resendCountdown > 0 ? (
                  <p className='text-white/30 text-xs'>
                    Resend code in <span className='text-[#C4A882]'>{resendCountdown}s</span>
                  </p>
                ) : (
                  <button
                    onClick={handleResend}
                    disabled={resending}
                    className='text-[#C4A882]/60 hover:text-[#C4A882] text-xs transition font-semibold'
                  >
                    {resending ? 'Sending...' : 'Resend Code'}
                  </button>
                )}
              </div>

              {/* Change email */}
              <button
                onClick={() => { setStep('email'); setOtp(['','','','','','']); setError('') }}
                className='text-white/30 hover:text-white/60 text-xs transition text-center'
              >
                ← Change email address
              </button>

            </div>
          )}
        </div>

        {/* Bottom text */}
        <p className='text-center text-white/20 text-[10px] mt-4'>
          By signing in, you agree to our Terms & Privacy Policy
        </p>
      </div>
    </div>
  )
}

export default EmailSignin