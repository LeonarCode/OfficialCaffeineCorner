import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import background from '../../assets/Background.jpeg'
import logo from '../../assets/Logo.jpg'
import facebook from '../../assets/facebook.svg'
import google from '../../assets/google.svg'
import { HiOutlineMail } from 'react-icons/hi'
import { useGoogleLogin } from '@react-oauth/google'
import { googleLogin, facebookLogin } from '../../services/authService'
import { useAuth } from '../../context/AuthContext'

const Signin = () => {
  const { setIsAuthenticated } = useAuth()
  const navigate = useNavigate()
  const [googleLoading,   setGoogleLoading]   = useState(false)
  const [facebookLoading, setFacebookLoading] = useState(false)
  const [error,           setError]           = useState('')

  const saveTokensAndRedirect = (data) => {
    localStorage.setItem('access', data.access)
    localStorage.setItem('refresh', data.refresh)
    setIsAuthenticated(true)
    navigate('/home')
  }

  const handleGoogleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setGoogleLoading(true)
      setError('')
      try {
        const res = await googleLogin(tokenResponse.access_token)
        saveTokensAndRedirect(res.data)
      } catch (err) {
        setError('Google sign in failed. Please try again.')
        console.error('Google login failed', err)
      } finally {
        setGoogleLoading(false)
      }
    },
    onError: () => {
      setError('Google sign in was cancelled.')
      setGoogleLoading(false)
    },
  })

  const handleFacebookLogin = () => {
    setFacebookLoading(true)
    setError('')
    window.FB.init({
      appId:   import.meta.env.VITE_FACEBOOK_APP_ID,
      cookie:  true,
      xfbml:   true,
      version: 'v19.0'
    })
    window.FB.login(async (response) => {
      if (response.authResponse) {
        try {
          const res = await facebookLogin(response.authResponse.accessToken)
          saveTokensAndRedirect(res.data)
        } catch (err) {
          setError('Facebook sign in failed. Please try again.')
          console.error('Facebook login failed', err)
        } finally {
          setFacebookLoading(false)
        }
      } else {
        setError('Facebook sign in was cancelled.')
        setFacebookLoading(false)
      }
    }, { scope: 'email,public_profile' })
  }

  return (
    <div
      className='min-h-screen flex items-center justify-center p-5 relative'
      style={{ backgroundImage: `url(${background})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
    >
      {/* Overlays */}
      <div className='absolute inset-0 bg-black/50' />
      <div className='absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent' />

      {/* Card */}
      <div className='relative z-10 w-full max-w-sm'>

        {/* Header */}
        <div className='text-center mb-6'>
          <div className='relative inline-block mb-4'>
            <div className='absolute inset-0 rounded-full bg-[#C4A882]/20 blur-xl scale-150' />
            <img src={logo} alt='Caffeine Corner' className='relative h-20 w-20 rounded-full object-cover border-2 border-white/20 shadow-xl' />
          </div>
          <h1 className='text-white text-xl font-bold tracking-wide'>Welcome Back</h1>
          <p className='text-white/50 text-xs mt-1 tracking-widest uppercase'>Caffeine Corner</p>
        </div>

        {/* Main Card */}
        <div className='bg-white/10 backdrop-blur-xl rounded-3xl p-6 border border-white/10 shadow-2xl'>

          {/* Error Message */}
          {error && (
            <div className='bg-red-500/20 border border-red-400/30 rounded-xl px-4 py-2.5 mb-4'>
              <p className='text-red-200 text-xs text-center'>{error}</p>
            </div>
          )}

          <div className='flex flex-col gap-3'>

            {/* Google */}
            <button
              onClick={() => handleGoogleLogin()}
              disabled={googleLoading || facebookLoading}
              className='w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed text-[#2C1503] font-semibold text-sm py-3.5 px-5 rounded-2xl transition-all duration-200 shadow-sm hover:shadow-md hover:scale-[1.01]'
            >
              {googleLoading ? (
                <svg className='animate-spin h-5 w-5 text-gray-400' viewBox='0 0 24 24' fill='none'>
                  <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'/>
                  <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z'/>
                </svg>
              ) : (
                <img src={google} alt='Google' className='h-5 w-5' />
              )}
              {googleLoading ? 'Signing in...' : 'Continue with Google'}
            </button>

            {/* Facebook */}
            <button
              onClick={handleFacebookLogin}
              disabled={googleLoading || facebookLoading}
              className='w-full flex items-center justify-center gap-3 bg-[#1877F2] hover:bg-[#166FE5] disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-sm py-3.5 px-5 rounded-2xl transition-all duration-200 shadow-sm hover:shadow-md hover:scale-[1.01]'
            >
              {facebookLoading ? (
                <svg className='animate-spin h-5 w-5 text-white/60' viewBox='0 0 24 24' fill='none'>
                  <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4'/>
                  <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z'/>
                </svg>
              ) : (
                <img src={facebook} alt='Facebook' className='h-5 w-5' />
              )}
              {facebookLoading ? 'Signing in...' : 'Continue with Facebook'}
            </button>

            {/* Divider */}
            <div className='flex items-center gap-3 my-1'>
              <div className='flex-1 h-px bg-white/15' />
              <span className='text-white/30 text-xs'>or</span>
              <div className='flex-1 h-px bg-white/15' />
            </div>

            {/* Email OTP */}
            <Link
              to='/email-signin'
              className='w-full flex items-center justify-center gap-3 bg-[#C4A882] hover:bg-[#b8976e] text-[#2C1503] font-semibold text-sm py-3.5 px-5 rounded-2xl transition-all duration-200 shadow-sm hover:shadow-md hover:scale-[1.01]'
            >
              <HiOutlineMail size={18} />
              Continue with Email
            </Link>

          </div>

          {/* Footer */}
          <div className='mt-5 flex flex-col items-center gap-2'>
            <Link to='/home' className='text-white/25 text-xs hover:text-white/50 transition'>
              Continue as guest →
            </Link>
          </div>
        </div>

        {/* Bottom text */}
        <p className='text-center text-white/20 text-[10px] mt-4'>
          By signing in, you agree to our Terms & Privacy Policy
        </p>
      </div>
    </div>
  )
}

export default Signin