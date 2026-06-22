import React from 'react'
import { Link } from 'react-router-dom'
import logo from '../assets/Logo.jpg'
import { HiOutlineMail, HiOutlineLocationMarker, HiOutlinePhone } from 'react-icons/hi'
import { FaFacebook, FaInstagram, FaTiktok } from 'react-icons/fa'

const Footer = () => {
  return (
    <footer className='bg-[#2C1503] text-white'>

      {/* Main Footer */}
      <div className='max-w-6xl mx-auto px-6 sm:px-10 py-12'>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10'>

          {/* Brand */}
          <div className='flex flex-col gap-4'>
            <div className='flex items-center gap-3'>
              <img src={logo} alt='Caffeine Corner' className='h-12 w-12 rounded-full object-cover' />
              <div>
                <p className='text-white font-bold tracking-widest text-sm'>CAFFEINE</p>
                <p className='text-white font-bold tracking-widest text-sm'>CORNER</p>
              </div>
            </div>
            <p className='text-[#C4A882]/60 text-xs leading-relaxed'>
              Your favorite coffee shop in Garcia Hernandez, Bohol. Crafting premium blends with love since day one.
            </p>
            {/* Social Links */}
            <div className='flex items-center gap-3 mt-1'>
              <a href='#' className='w-8 h-8 rounded-full bg-white/10 hover:bg-[#C4A882]/30 flex items-center justify-center transition'>
                <FaFacebook size={14} className='text-[#C4A882]' />
              </a>
              <a href='#' className='w-8 h-8 rounded-full bg-white/10 hover:bg-[#C4A882]/30 flex items-center justify-center transition'>
                <FaInstagram size={14} className='text-[#C4A882]' />
              </a>
              <a href='#' className='w-8 h-8 rounded-full bg-white/10 hover:bg-[#C4A882]/30 flex items-center justify-center transition'>
                <FaTiktok size={14} className='text-[#C4A882]' />
              </a>
            </div>
          </div>

          {/* Quick Links */}
          <div className='flex flex-col gap-3'>
            <p className='text-[#C4A882] text-xs font-bold tracking-widest uppercase mb-1'>Quick Links</p>
            {[
              { label: 'Home', to: '/home' },
              { label: 'My Orders', to: '/orders' },
              { label: 'My Cart', to: '/cart' },
              { label: 'My Profile', to: '/profile' },
              { label: 'Sign In', to: '/signin' },
            ].map((link) => (
              <Link
                key={link.label}
                to={link.to}
                className='text-[#C4A882]/60 hover:text-[#C4A882] text-xs transition flex items-center gap-1.5'
              >
                <span className='text-[#C4A882]/30'>›</span> {link.label}
              </Link>
            ))}
          </div>

          {/* Menu Categories */}
          <div className='flex flex-col gap-3'>
            <p className='text-[#C4A882] text-xs font-bold tracking-widest uppercase mb-1'>Our Menu</p>
            {[
              'Coffee',
              'Non-Coffee',
              'Frappe',
              'Pastry',
              'Foods',
            ].map((cat) => (
              <Link
                key={cat}
                to={`/home?search=${cat}`}
                className='text-[#C4A882]/60 hover:text-[#C4A882] text-xs transition flex items-center gap-1.5'
              >
                <span className='text-[#C4A882]/30'>›</span> {cat}
              </Link>
            ))}
          </div>

          {/* Contact */}
          <div className='flex flex-col gap-4'>
            <p className='text-[#C4A882] text-xs font-bold tracking-widest uppercase mb-1'>Contact Us</p>
            <div className='flex items-start gap-3'>
              <HiOutlineLocationMarker size={16} className='text-[#C4A882] shrink-0 mt-0.5' />
              <p className='text-[#C4A882]/60 text-xs leading-relaxed'>
                Garcia Hernandez, Bohol, Philippines
              </p>
            </div>
            <div className='flex items-center gap-3'>
              <HiOutlinePhone size={16} className='text-[#C4A882] shrink-0' />
              <p className='text-[#C4A882]/60 text-xs'>+63 XXX XXX XXXX</p>
            </div>
            <div className='flex items-center gap-3'>
              <HiOutlineMail size={16} className='text-[#C4A882] shrink-0' />
              <p className='text-[#C4A882]/60 text-xs'>caffeinecorner@gmail.com</p>
            </div>

            {/* Store Hours */}
            <div className='bg-white/5 rounded-xl p-3 mt-1'>
              <p className='text-[#C4A882] text-xs font-semibold mb-2'>Store Hours</p>
              <div className='flex justify-between'>
                <p className='text-[#C4A882]/50 text-xs'>Mon - Fri</p>
                <p className='text-[#C4A882]/70 text-xs font-semibold'>7:00 AM - 9:00 PM</p>
              </div>
              <div className='flex justify-between mt-1'>
                <p className='text-[#C4A882]/50 text-xs'>Sat - Sun</p>
                <p className='text-[#C4A882]/70 text-xs font-semibold'>8:00 AM - 10:00 PM</p>
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* Divider */}
      <div className='border-t border-white/10' />

      {/* Bottom Bar */}
      <div className='max-w-6xl mx-auto px-6 sm:px-10 py-5 flex flex-col sm:flex-row items-center justify-between gap-2'>
        <p className='text-[#C4A882]/40 text-xs'>
          © {new Date().getFullYear()} Caffeine Corner. All rights reserved.
        </p>
        <p className='text-[#C4A882]/40 text-xs'>
          Made with ☕ in Bohol, Philippines
        </p>
      </div>

    </footer>
  )
}

export default Footer