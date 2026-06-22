import React, { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Card from '../components/Card'
import { getProducts, getCategories } from '../services/productService'
import { useAuth } from '../context/AuthContext'

const Homepage = () => {
  const [products,       setProducts]       = useState([])
  const [featured,       setFeatured]       = useState([])
  const [categories,     setCategories]     = useState([])
  const [activeCategory, setActiveCategory] = useState('All')
  const [loading,        setLoading]        = useState(true)
  const [showAll,        setShowAll]        = useState(false)
  const { isAuthenticated }                 = useAuth()
  const location                            = useLocation()
  const navigate                            = useNavigate()

  const searchQuery = new URLSearchParams(location.search).get('search') || ''

  useEffect(() => {
    fetchCategories()
    if (searchQuery) {
      fetchProducts(null, searchQuery)
      setActiveCategory('All')
    } else {
      fetchProducts()
      fetchFeatured()
    }
  }, [location.search])

  const fetchCategories = async () => {
    try {
      const res = await getCategories()
      setCategories(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const fetchProducts = async (category = null, search = null) => {
    setLoading(true)
    try {
      const params = {}
      if (category) params.category = category
      if (search)   params.search   = search
      const res = await getProducts(params)
      setProducts(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const fetchFeatured = async () => {
    try {
      const res = await getProducts({ featured: true })
      setFeatured(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const handleCategoryFilter = (category) => {
    setActiveCategory(category)
    setShowAll(false)
    navigate('/home', { replace: true })
    if (category === 'All') {
      fetchProducts()
    } else {
      fetchProducts(category)
    }
  }

  const displayedProducts = showAll ? products : products.slice(0, 8)

  return (
    <div className='flex flex-col bg-[#FAF6F0] min-h-screen'>

      {/* Hero Section */}
      {!searchQuery && activeCategory === 'All' && (
        <div className='relative bg-[#2C1503] overflow-hidden'>
          <div className='absolute inset-0 bg-[radial-gradient(ellipse_at_70%_50%,rgba(196,168,130,0.15)_0%,transparent_70%)] pointer-events-none' />
          <div className='max-w-6xl mx-auto px-6 py-14 sm:py-20 flex flex-col sm:flex-row items-center gap-8'>
            <div className='flex-1 z-10'>
              <p className='text-[#C4A882]/60 text-xs font-semibold tracking-[0.3em] uppercase mb-3'>
                Garcia Hernandez, Bohol
              </p>
              <h1 className='text-white text-4xl sm:text-5xl font-bold leading-tight mb-3'
                style={{ fontFamily: "'Playfair Display', serif" }}>
                Every Sip
                <br />
                <em className='text-[#C4A882] italic'>Tells a Story</em>
              </h1>
              <p className='text-[#C4A882]/60 text-sm leading-relaxed mb-6 max-w-md'>
                Handcrafted coffee blends made with love. From our farm to your cup — experience Bohol's finest brew.
              </p>
              <div className='flex gap-3 flex-wrap'>
                <button
                  onClick={() => document.getElementById('products-section')?.scrollIntoView({ behavior: 'smooth' })}
                  className='bg-[#C4A882] hover:bg-[#b8976e] text-[#2C1503] font-bold text-sm px-6 py-3 rounded-full transition'
                >
                  Order Now ☕
                </button>
                {!isAuthenticated && (
                  <Link
                    to='/signin'
                    className='border border-white/30 hover:border-white text-white font-semibold text-sm px-6 py-3 rounded-full transition'
                  >
                    Sign In
                  </Link>
                )}
              </div>
            </div>

            {/* Stats */}
            <div className='flex sm:flex-col gap-4 z-10'>
              {[
                { value: '100%', label: 'Locally Sourced' },
                { value: '5★',   label: 'Customer Rating' },
                { value: '50+',  label: 'Menu Items' },
              ].map((stat, i) => (
                <div key={i} className='text-center bg-white/5 rounded-2xl px-6 py-4'>
                  <p className='text-[#C4A882] text-2xl font-bold'>{stat.value}</p>
                  <p className='text-white/50 text-xs'>{stat.label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Feature Badges */}
      <div className='bg-[#3D1F00]'>
        <div className='max-w-6xl mx-auto grid grid-cols-2 md:grid-cols-4'>
          {[
            { icon: '🌿', title: 'Ethically Sourced',  sub: 'Direct trade with farmers' },
            { icon: '🔬', title: 'Lab-Tested Quality', sub: 'Every batch, guaranteed' },
            { icon: '📦', title: 'Fast Delivery',      sub: 'Delivered within 24 hours' },
            { icon: '♻️', title: 'Eco Packaging',      sub: 'Recyclable & biodegradable', last: true },
          ].map((item, i) => (
            <div key={i} className={`group flex items-center gap-3 px-5 py-4 border-b border-white/10 hover:bg-[#C4A882]/10 transition cursor-default ${!item.last ? 'border-r border-white/10' : ''}`}>
              <span className='text-xl shrink-0 group-hover:scale-110 group-hover:-rotate-6 transition-transform'>{item.icon}</span>
              <div>
                <p className='text-[#C4A882] font-semibold text-xs leading-tight mb-0.5'>{item.title}</p>
                <p className='text-[#C4A882]/55 text-xs font-light hidden sm:block'>{item.sub}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className='max-w-6xl mx-auto w-full px-6 py-10'>

        {/* Featured Products */}
        {!searchQuery && activeCategory === 'All' && featured.length > 0 && (
          <div className='mb-12'>
            <div className='flex items-center justify-between mb-6'>
              <div>
                <p className='text-[#C4A882] text-xs font-semibold tracking-widest uppercase mb-1'>Staff Picks</p>
                <h2 className='text-[#2C1503] text-xl font-bold'>Featured Items</h2>
              </div>
            </div>
            <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5'>
              {featured.slice(0, 4).map(product => (
                <Card
                  key={product.id}
                  productId={product.id}
                  image={product.image || null}
                  name={product.name}
                  description={product.description}
                  price={parseFloat(product.price)}
                  rating={product.average_rating || 0}
                  reviewCount={product.rating_count || 0}
                  premium={product.is_featured}
                />
              ))}
            </div>
            <div className='flex items-center gap-4 mt-10 mb-2'>
              <div className='flex-1 h-px bg-gradient-to-r from-transparent to-[#6f4e37]/20'/>
              <span className='w-2 h-2 rounded-full bg-[#6f4e37]/40'/>
              <div className='flex-1 h-px bg-gradient-to-l from-transparent to-[#6f4e37]/20'/>
            </div>
          </div>
        )}

        {/* Search Results Header */}
        {searchQuery && (
          <div className='flex items-center justify-between mb-6'>
            <div>
              <p className='text-[#2C1503] font-bold text-lg'>
                Results for "<span className='text-[#6f4e37] italic'>{searchQuery}</span>"
              </p>
              <p className='text-gray-400 text-xs mt-0.5'>
                {products.length} product{products.length !== 1 ? 's' : ''} found
              </p>
            </div>
            <button
              onClick={() => navigate('/home', { replace: true })}
              className='text-[#6f4e37] text-xs font-semibold hover:underline flex items-center gap-1'
            >
              ✕ Clear search
            </button>
          </div>
        )}

        {/* All Products Section */}
        <div id='products-section'>
          <div className='flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6'>
            <div>
              {!searchQuery && (
                <>
                  <p className='text-[#C4A882] text-xs font-semibold tracking-widest uppercase mb-1'>Our Menu</p>
                  <h2 className='text-[#2C1503] text-xl font-bold'>
                    {activeCategory === 'All' ? 'All Products' : activeCategory}
                  </h2>
                  <p className='text-gray-400 text-xs mt-0.5'>
                    {products.length} item{products.length !== 1 ? 's' : ''} available
                  </p>
                </>
              )}
            </div>

            {/* Category Pills */}
            <div className='flex gap-2 flex-wrap'>
              <button
                onClick={() => handleCategoryFilter('All')}
                className={`px-4 py-1.5 rounded-full border text-xs font-bold tracking-widest uppercase transition-all duration-200
                  ${activeCategory === 'All' && !searchQuery
                    ? 'border-[#6f4e37] bg-[#6f4e37] text-white'
                    : 'border-gray-300 bg-white text-[#6f4e37] hover:border-[#6f4e37]'
                  }`}
              >
                All
              </button>
              {categories.map(cat => (
                <button
                  key={cat.id}
                  onClick={() => handleCategoryFilter(cat.name)}
                  className={`px-4 py-1.5 rounded-full border text-xs font-bold tracking-widest uppercase transition-all duration-200
                    ${activeCategory === cat.name
                      ? 'border-[#6f4e37] bg-[#6f4e37] text-white'
                      : 'border-gray-300 bg-white text-[#6f4e37] hover:border-[#6f4e37]'
                    }`}
                >
                  {cat.name}
                </button>
              ))}
            </div>
          </div>

          {/* Product Cards */}
          <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5'>
            {loading ? (
              [...Array(8)].map((_, i) => (
                <div key={i} className='flex flex-col bg-white rounded-2xl overflow-hidden shadow-sm'>
                  <div className='w-full h-44 bg-gray-200 animate-pulse' />
                  <div className='p-4 flex flex-col gap-2'>
                    <div className='h-3.5 bg-gray-200 rounded animate-pulse w-3/4' />
                    <div className='h-3 bg-gray-100 rounded animate-pulse w-full' />
                    <div className='h-4 bg-gray-200 rounded animate-pulse w-1/3 mt-2' />
                  </div>
                </div>
              ))
            ) : products.length > 0 ? (
              displayedProducts.map(product => (
                <Card
                  key={product.id}
                  productId={product.id}
                  image={product.image || null}
                  name={product.name}
                  description={product.description}
                  price={parseFloat(product.price)}
                  rating={product.average_rating || 0}
                  reviewCount={product.rating_count || 0}
                  premium={product.is_featured}
                />
              ))
            ) : (
              <div className='col-span-4 flex flex-col items-center py-16 gap-3'>
                <p className='text-3xl'>☕</p>
                <p className='text-gray-400 text-sm'>
                  {searchQuery ? `No products found for "${searchQuery}"` : 'No products available.'}
                </p>
                {searchQuery && (
                  <button
                    onClick={() => navigate('/home', { replace: true })}
                    className='text-[#6f4e37] text-xs font-semibold hover:underline'
                  >
                    Browse all products
                  </button>
                )}
              </div>
            )}
          </div>

          {/* View All Button */}
          {!loading && products.length > 8 && (
            <div className='flex justify-center mt-10'>
              <button
                onClick={() => setShowAll(!showAll)}
                className='flex items-center gap-3 bg-transparent hover:bg-[#4a2910] text-[#4a2910] hover:text-white text-[10px] font-bold tracking-[0.2em] uppercase px-6 py-2.5 rounded-full border border-[#4a2910]/40 hover:border-transparent transition-all duration-200'
              >
                {showAll ? 'View Less' : `View All ${products.length} Products`}
                <span className='text-sm'>{showAll ? '↑' : '→'}</span>
              </button>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}

export default Homepage