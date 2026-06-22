import React, { useEffect, useState } from 'react'
import background from '../assets/Background.jpeg'
import logo from '../assets/Logo.jpg'
import { Link } from 'react-router-dom'

const Welcome = () => {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setTimeout(() => setVisible(true), 100)
  }, [])

  return (
    <div
      className='relative h-screen overflow-hidden flex flex-col items-center justify-center p-6'
      style={{ backgroundImage: `url(${background})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
    >
      {/* Dark overlay */}
      <div className='absolute inset-0 bg-black/50' />

      {/* Gradient overlay bottom */}
      <div className='absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20' />

      {/* Content */}
      <div
        className='relative z-10 flex flex-col items-center text-center max-w-2xl w-full'
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(24px)',
          transition: 'opacity 0.8s ease, transform 0.8s ease',
        }}
      >
        {/* Logo */}
        <div className='relative mb-6'>
          <div className='absolute inset-0 rounded-full bg-[#C4A882]/30 blur-xl scale-150' />
          <img
            src={logo}
            alt='Caffeine Corner Logo'
            className='relative h-24 w-24 sm:h-32 sm:w-32 rounded-full object-cover border-4 border-white/30 shadow-2xl'
          />
        </div>

        {/* Brand name */}
        <p className='text-[#C4A882]/80 text-xs font-semibold tracking-[0.4em] uppercase mb-1'>
          Garcia Hernandez, Bohol
        </p>
        <h1 className='text-white text-4xl sm:text-6xl font-bold tracking-widest mb-1'
          style={{ fontFamily: "'Playfair Display', serif", textShadow: '0 2px 20px rgba(0,0,0,0.5)' }}>
          CAFFEINE
        </h1>
        <h1 className='text-[#C4A882] text-4xl sm:text-6xl font-bold tracking-widest mb-6'
          style={{ fontFamily: "'Playfair Display', serif", textShadow: '0 2px 20px rgba(0,0,0,0.5)' }}>
          CORNER
        </h1>

        {/* Divider */}
        <div className='flex items-center gap-3 mb-6 w-48'>
          <div className='flex-1 h-px bg-[#C4A882]/40' />
          <span className='text-[#C4A882] text-lg'>☕</span>
          <div className='flex-1 h-px bg-[#C4A882]/40' />
        </div>

        {/* Tagline */}
        <p className='text-white/80 text-sm sm:text-base leading-relaxed mb-2 max-w-md'>
          Your favorite coffee shop in the heart of Bohol.
        </p>
        <p className='text-white/50 text-xs sm:text-sm leading-relaxed mb-8 max-w-sm'>
          Order online or visit us in store — every cup crafted with love.
        </p>

        {/* Buttons */}
        <div className='flex flex-col sm:flex-row gap-3 w-full sm:w-auto'>
          <Link
            to='/home'
            className='bg-[#C4A882] hover:bg-[#b8976e] text-[#2C1503] font-bold text-sm py-3.5 px-10 rounded-full transition-all duration-300 hover:scale-105 shadow-lg'
          >
            Order Now ☕
          </Link>
          <Link
            to='/signin'
            className='border border-white/40 hover:border-white text-white hover:bg-white/10 font-semibold text-sm py-3.5 px-10 rounded-full transition-all duration-300'
          >
            Sign In
          </Link>
        </div>

        {/* Features */}
        <div className='flex gap-6 mt-10 flex-wrap justify-center'>
          {[
            { icon: '🌿', label: 'Fresh Brews' },
            { icon: '📦', label: 'Online Orders' },
            { icon: '🎁', label: 'Loyalty Points' },
            { icon: '🍽️', label: 'Dine-in' },
          ].map((item, i) => (
            <div key={i} className='flex flex-col items-center gap-1'>
              <span className='text-xl'>{item.icon}</span>
              <p className='text-white/60 text-xs'>{item.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Welcome