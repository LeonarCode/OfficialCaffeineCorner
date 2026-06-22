import React, { useState, useEffect, useRef } from 'react'
import logo from '../assets/Logo.jpg'
import { HiOutlineSearch, HiOutlineClipboardList, HiOutlineUser, HiOutlineShoppingCart, HiOutlineX } from 'react-icons/hi'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getProducts } from '../services/productService'

const Navbar = () => {
  const [searchOpen,        setSearchOpen]        = useState(false)
  const [searchQuery,       setSearchQuery]        = useState('')
  const [suggestions,       setSuggestions]        = useState([])
  const [showSuggestions,   setShowSuggestions]    = useState(false)
  const [loadingSuggestions,setLoadingSuggestions] = useState(false)
  const [scrolled,          setScrolled]           = useState(false)
  const { isAuthenticated, logout, cartCount }     = useAuth()
  const navigate    = useNavigate()
  const location    = useLocation()
  const searchRef   = useRef(null)
  const debounceRef = useRef(null)

  // Scroll effect
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Close suggestions on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close search on route change
  useEffect(() => {
    setSearchOpen(false)
    setSearchQuery('')
    setSuggestions([])
    setShowSuggestions(false)
  }, [location.pathname])

  const handleLogout = () => { logout(); navigate('/signin') }

  const handleSearchChange = (value) => {
    setSearchQuery(value)
    clearTimeout(debounceRef.current)
    if (value.trim().length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    setLoadingSuggestions(true)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await getProducts({ search: value.trim() })
        setSuggestions(res.data.slice(0, 5))
        setShowSuggestions(true)
      } catch (err) {
        console.error('Search failed', err)
      } finally {
        setLoadingSuggestions(false)
      }
    }, 400)
  }

  const handleSearch = (e) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      navigate(`/home?search=${encodeURIComponent(searchQuery.trim())}`)
      setShowSuggestions(false)
      setSearchOpen(false)
    }
    if (e.key === 'Escape') {
      setShowSuggestions(false)
      setSearchOpen(false)
    }
  }

  const handleSuggestionClick = (product) => {
    navigate(`/product/${product.id}`)
    setSearchQuery('')
    setSuggestions([])
    setShowSuggestions(false)
    setSearchOpen(false)
  }

  const isActive = (path) => location.pathname === path

  const SearchSuggestions = () => (
    showSuggestions ? (
      <div className='absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden z-50'>
        {loadingSuggestions ? (
          <div className='px-4 py-4 flex items-center gap-2'>
            <div className='w-4 h-4 border-2 border-[#6f4e37] border-t-transparent rounded-full animate-spin' />
            <span className='text-gray-400 text-xs'>Searching...</span>
          </div>
        ) : suggestions.length > 0 ? (
          <>
            <p className='text-[10px] text-gray-400 font-semibold uppercase tracking-widest px-4 pt-3 pb-1'>
              Suggestions
            </p>
            {suggestions.map(product => (
              <button
                key={product.id}
                onClick={() => handleSuggestionClick(product)}
                className='w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[#FAF6F0] transition text-left group'
              >
                <div className='w-10 h-10 rounded-xl overflow-hidden shrink-0 bg-gray-100'>
                  {product.image
                    ? <img src={product.image} alt={product.name} className='w-full h-full object-cover group-hover:scale-105 transition-transform' />
                    : <div className='w-full h-full bg-gray-200 flex items-center justify-center text-sm'>☕</div>
                  }
                </div>
                <div className='flex-1 min-w-0'>
                  <p className='text-[#2C1503] text-sm font-semibold truncate'>{product.name}</p>
                  <p className='text-gray-400 text-xs'>{product.category_name}</p>
                </div>
                <p className='text-[#6f4e37] text-sm font-bold shrink-0'>
                  ₱{parseFloat(product.price).toFixed(2)}
                </p>
              </button>
            ))}
            <button
              onClick={() => { navigate(`/home?search=${encodeURIComponent(searchQuery)}`); setShowSuggestions(false) }}
              className='w-full flex items-center gap-2 px-4 py-3 border-t border-gray-100 hover:bg-[#FAF6F0] transition text-left'
            >
              <HiOutlineSearch size={14} className='text-[#6f4e37]' />
              <span className='text-[#6f4e37] text-xs font-semibold'>
                See all results for "<span className='italic'>{searchQuery}</span>"
              </span>
            </button>
          </>
        ) : (
          <div className='px-4 py-4 text-center'>
            <p className='text-2xl mb-1'>☕</p>
            <p className='text-gray-400 text-xs'>No products found for "{searchQuery}"</p>
          </div>
        )}
      </div>
    ) : null
  )

  return (
    <>
      <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300
        ${scrolled
          ? 'bg-[#2C1503] shadow-2xl shadow-black/30'
          : 'bg-[#3D1F00]'
        }`}
      >
        {/* Top announcement bar */}
        <div className='bg-[#C4A882]/15 border-b border-white/5 hidden sm:block'>
          <div className='max-w-6xl mx-auto px-6 py-1.5 flex items-center justify-between'>
            <p className='text-[#C4A882]/60 text-[10px] tracking-widest uppercase'>
              ☕ Caffeine Corner — Garcia Hernandez, Bohol
            </p>
            <div className='flex items-center gap-4'>
              {!isAuthenticated && (
                <Link to='/signin' className='text-[#C4A882]/50 hover:text-[#C4A882] text-[10px] transition'>
                  Sign in for loyalty points →
                </Link>
              )}
              {isAuthenticated && (
                <Link to='/orders' className='text-[#C4A882]/50 hover:text-[#C4A882] text-[10px] transition'>
                  Track your orders →
                </Link>
              )}
            </div>
          </div>
        </div>

        {/* Main Navbar */}
        <div className='max-w-6xl mx-auto flex items-center justify-between py-3 px-6'>

          {/* Logo */}
          <Link to='/home' className='flex items-center gap-3 group shrink-0'>
            <div className='relative'>
              <img
                src={logo}
                alt='Caffeine Corner'
                className='h-10 w-10 rounded-full object-cover border-2 border-white/10 group-hover:border-[#C4A882]/40 transition shadow-md'
              />
            </div>
            <div className='hidden sm:block'>
              <p className='text-white font-bold tracking-widest text-xs leading-tight'>CAFFEINE</p>
              <p className='text-[#C4A882] font-bold tracking-widest text-xs leading-tight'>CORNER</p>
            </div>
          </Link>

          {/* Search Bar — desktop */}
          <div ref={searchRef} className='hidden sm:flex relative flex-1 max-w-sm mx-6'>
            <div className={`flex items-center bg-white/10 hover:bg-white/15 border rounded-full px-4 py-2 w-full transition-all duration-200
              ${showSuggestions ? 'border-[#C4A882]/40 bg-white/15' : 'border-white/10'}`}
            >
              <HiOutlineSearch size={16} className='text-[#C4A882]/60 shrink-0' />
              <input
                type='text'
                placeholder='Search drinks, pastries...'
                value={searchQuery}
                onChange={e => handleSearchChange(e.target.value)}
                onKeyDown={handleSearch}
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                className='outline-none text-sm text-white placeholder:text-white/30 w-full bg-transparent ml-3'
              />
              {searchQuery && (
                <button
                  onClick={() => { setSearchQuery(''); setSuggestions([]); setShowSuggestions(false) }}
                  className='text-white/30 hover:text-white/60 ml-2 transition'
                >
                  <HiOutlineX size={14} />
                </button>
              )}
            </div>
            <SearchSuggestions />
          </div>

          {/* Right Icons */}
          <div className='flex items-center gap-1'>

            {/* Mobile search toggle */}
            <button
              className='sm:hidden w-9 h-9 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 rounded-full transition'
              onClick={() => setSearchOpen(!searchOpen)}
            >
              {searchOpen ? <HiOutlineX size={20} /> : <HiOutlineSearch size={20} />}
            </button>

            {isAuthenticated ? (
              <>
                {/* Cart */}
                <Link
                  to='/cart'
                  className={`relative w-9 h-9 flex items-center justify-center rounded-full transition
                    ${isActive('/cart') ? 'bg-white/20 text-white' : 'text-white/70 hover:text-white hover:bg-white/10'}`}
                >
                  <HiOutlineShoppingCart size={20} />
                  {cartCount > 0 && (
                    <span className='absolute -top-0.5 -right-0.5 min-w-[16px] h-4 bg-[#C4A882] text-[#2C1503] text-[9px] font-bold rounded-full flex items-center justify-center px-1'>
                      {cartCount > 99 ? '99+' : cartCount}
                    </span>
                  )}
                </Link>

                {/* Orders */}
                <Link
                  to='/orders'
                  className={`w-9 h-9 flex items-center justify-center rounded-full transition
                    ${isActive('/orders') ? 'bg-white/20 text-white' : 'text-white/70 hover:text-white hover:bg-white/10'}`}
                >
                  <HiOutlineClipboardList size={20} />
                </Link>

                {/* Profile */}
                <Link
                  to='/profile'
                  className={`w-9 h-9 flex items-center justify-center rounded-full transition
                    ${isActive('/profile') ? 'bg-white/20 text-white' : 'text-white/70 hover:text-white hover:bg-white/10'}`}
                >
                  <HiOutlineUser size={20} />
                </Link>

                {/* Logout - desktop only */}
                <button
                  onClick={handleLogout}
                  className='hidden sm:flex items-center gap-1.5 border border-white/20 hover:border-white/50 text-white/60 hover:text-white text-xs font-semibold px-3 py-1.5 rounded-full transition ml-1'
                >
                  Logout
                </button>
              </>
            ) : (
              <Link
                to='/signin'
                className='flex items-center gap-1.5 bg-[#C4A882] hover:bg-[#b8976e] text-[#2C1503] text-xs font-bold px-4 py-1.5 rounded-full transition hover:scale-105 shadow-sm ml-1'
              >
                Sign In
              </Link>
            )}
          </div>
        </div>

        {/* Mobile Search Dropdown */}
        <div className={`sm:hidden overflow-hidden transition-all duration-300 ${searchOpen ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}`}>
          <div className='px-4 pb-3'>
            <div ref={searchRef} className='relative'>
              <div className='flex items-center bg-white/10 border border-white/15 rounded-2xl px-4 py-2.5 w-full'>
                <HiOutlineSearch size={16} className='text-[#C4A882]/60 shrink-0' />
                <input
                  type='text'
                  placeholder='Search drinks, pastries...'
                  autoFocus={searchOpen}
                  value={searchQuery}
                  onChange={e => handleSearchChange(e.target.value)}
                  onKeyDown={handleSearch}
                  className='outline-none text-sm text-white placeholder:text-white/30 w-full bg-transparent ml-3'
                />
                {searchQuery && (
                  <button
                    onClick={() => { setSearchQuery(''); setSuggestions([]); setShowSuggestions(false) }}
                    className='text-white/30 hover:text-white/60 transition'
                  >
                    <HiOutlineX size={14} />
                  </button>
                )}
              </div>
              <SearchSuggestions />
            </div>
          </div>
        </div>

      </header>

      {/* Spacer for fixed header */}
      <div className='h-[60px] sm:h-[88px]' />
    </>
  )
}

export default Navbar