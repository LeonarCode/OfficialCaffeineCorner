import React, { useState, useEffect } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { FaStar, FaRegStar, FaShareAlt } from 'react-icons/fa'
import { HiOutlineShoppingCart, HiOutlineHeart, HiHeart } from 'react-icons/hi'
import { BsFillLightningFill } from 'react-icons/bs'
import { getProduct, getReviews, createReview, getProducts } from '../services/productService'
import { addToCart } from '../services/cartService'
import { useAuth } from '../context/AuthContext'
import { useAuth as useAuthCtx } from '../context/AuthContext'
import Card from '../components/Card'

const RATING_LABELS = ['', 'Poor', 'Fair', 'Good', 'Very Good', 'Excellent']

const ProductDetail = () => {
  const { id }       = useParams()
  const navigate     = useNavigate()
  const { isAuthenticated, fetchCartCount } = useAuth()

  const [product,        setProduct]        = useState(null)
  const [loading,        setLoading]        = useState(true)
  const [selectedVariant,setSelectedVariant]= useState(null)
  const [quantity,       setQuantity]       = useState(1)
  const [addingToCart,   setAddingToCart]   = useState(false)
  const [cartSuccess,    setCartSuccess]    = useState(false)
  const [reviews,        setReviews]        = useState([])
  const [loadingReviews, setLoadingReviews] = useState(false)
  const [userRating,     setUserRating]     = useState(0)
  const [hoverRating,    setHoverRating]    = useState(0)
  const [reviewText,     setReviewText]     = useState('')
  const [submitting,     setSubmitting]     = useState(false)
  const [reviewError,    setReviewError]    = useState('')
  const [reviewSuccess,  setReviewSuccess]  = useState(false)
  const [related,        setRelated]        = useState([])
  const [zoomed,         setZoomed]         = useState(false)
  const [wishlisted,     setWishlisted]     = useState(false)
  const [copied,         setCopied]         = useState(false)
  const [activeTab,      setActiveTab]      = useState('reviews') // reviews | details

  useEffect(() => {
    fetchProduct()
    window.scrollTo(0, 0)
  }, [id])

  const fetchProduct = async () => {
    setLoading(true)
    try {
      const [productRes] = await Promise.all([
        getProduct(id),
        fetchReviews(id),
      ])
      setProduct(productRes.data)
      if (productRes.data.variants?.length > 0) {
        setSelectedVariant(productRes.data.variants[0])
      }
      // Fetch related products
      if (productRes.data.category_name) {
        const relatedRes = await getProducts({ category: productRes.data.category_name })
        setRelated(relatedRes.data.filter(p => p.id !== parseInt(id)).slice(0, 4))
      }
    } catch (err) {
      console.error('Failed to fetch product', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchReviews = async (productId) => {
    setLoadingReviews(true)
    try {
      const res = await getReviews(productId)
      setReviews(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingReviews(false)
    }
  }

  const handleSubmitReview = async () => {
    if (!isAuthenticated) { navigate('/signin'); return }
    if (userRating === 0) { setReviewError('Please select a rating.'); return }
    setSubmitting(true)
    setReviewError('')
    try {
      await createReview(id, { rating: userRating, review: reviewText })
      setReviewSuccess(true)
      setUserRating(0)
      setReviewText('')
      fetchReviews(id)
      setTimeout(() => setReviewSuccess(false), 3000)
    } catch (err) {
      setReviewError(err.response?.data?.detail || err.response?.data?.[0] || 'Failed to submit review.')
    } finally {
      setSubmitting(false)
    }
  }

  const getPrice = () => {
    const base  = parseFloat(product?.price || 0)
    const extra = parseFloat(selectedVariant?.additional_price || 0)
    return base + extra
  }

  const handleAddToCart = async () => {
    if (!isAuthenticated) { navigate('/signin'); return }
    setAddingToCart(true)
    try {
      await addToCart({ product: product.id, variant: selectedVariant?.id || null, quantity })
      setCartSuccess(true)
      fetchCartCount()
      setTimeout(() => setCartSuccess(false), 2000)
    } catch (err) {
      console.error(err)
    } finally {
      setAddingToCart(false)
    }
  }

  const handleBuyNow = () => {
    if (!isAuthenticated) { navigate('/signin'); return }
    navigate('/checkout', {
      state: { product: product.id, variant: selectedVariant?.id || null, name: product.name, image: product.image, price: getPrice(), quantity }
    })
  }

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Rating breakdown
  const ratingBreakdown = [5, 4, 3, 2, 1].map(star => ({
    star,
    count: reviews.filter(r => r.rating === star).length,
    pct:   reviews.length ? Math.round((reviews.filter(r => r.rating === star).length / reviews.length) * 100) : 0,
  }))

  if (loading) return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0]'>
      <div className='max-w-5xl mx-auto w-full px-6 py-10 flex flex-col sm:flex-row gap-8'>
        <div className='w-full sm:w-96 h-80 bg-gray-200 rounded-2xl animate-pulse shrink-0' />
        <div className='flex flex-col gap-3 flex-1'>
          <div className='h-6 bg-gray-200 rounded animate-pulse w-2/3' />
          <div className='h-4 bg-gray-100 rounded animate-pulse w-full' />
          <div className='h-4 bg-gray-100 rounded animate-pulse w-5/6' />
          <div className='h-8 bg-gray-200 rounded animate-pulse w-1/3 mt-4' />
        </div>
      </div>
    </div>
  )

  if (!product) return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0] items-center justify-center'>
      <p className='text-gray-400'>Product not found.</p>
      <Link to='/home' className='text-[#6f4e37] mt-2 text-sm hover:underline'>← Back to Home</Link>
    </div>
  )

  return (
    <div className='flex flex-col min-h-screen bg-[#FAF6F0]'>

      {/* Header Banner */}
      <div className='bg-[#3D1F00] px-6 sm:px-20 py-6'>
        <div className='flex items-center gap-2 text-[#C4A882]/60 text-xs font-semibold tracking-widest uppercase'>
          <Link to='/home' className='hover:text-[#C4A882] transition'>Home</Link>
          <span>›</span>
          <button onClick={() => navigate('/home')} className='hover:text-[#C4A882] transition text-[#C4A882]/40'>{product.category_name}</button>
          <span>›</span>
          <span className='text-[#C4A882] truncate max-w-xs'>{product.name}</span>
        </div>
      </div>

      {/* Main Content */}
      <div className='max-w-5xl mx-auto w-full px-6 py-10'>
        <div className='flex flex-col sm:flex-row gap-8'>

          {/* Product Image */}
          <div className='w-full sm:w-96 shrink-0'>
            <div
              className={`relative w-full h-80 rounded-2xl overflow-hidden bg-gray-100 cursor-zoom-in transition-all duration-300 ${zoomed ? 'scale-105 shadow-2xl' : ''}`}
              onClick={() => setZoomed(!zoomed)}
            >
              {product.image ? (
                <img
                  src={product.image}
                  alt={product.name}
                  className={`w-full h-full object-cover transition-transform duration-500 ${zoomed ? 'scale-110' : 'hover:scale-105'}`}
                />
              ) : (
                <div className='w-full h-full bg-gray-200 flex items-center justify-center'>
                  <span className='text-4xl'>☕</span>
                </div>
              )}
              {zoomed && (
                <div className='absolute inset-0 bg-black/10 flex items-center justify-center'>
                  <span className='text-white/60 text-xs bg-black/30 px-2 py-1 rounded-full'>Click to zoom out</span>
                </div>
              )}
            </div>

            {/* Badges + Actions */}
            <div className='flex items-center justify-between mt-3'>
              <div className='flex gap-2 flex-wrap'>
                {product.is_featured && (
                  <span className='bg-[#3D1F00] text-[#C4A882] text-xs font-bold px-3 py-1 rounded-full'>⭐ PREMIUM</span>
                )}
                {product.is_seasonal && (
                  <span className='bg-amber-100 text-amber-700 text-xs font-bold px-3 py-1 rounded-full'>🍂 SEASONAL</span>
                )}
                {!product.is_available && (
                  <span className='bg-red-100 text-red-600 text-xs font-bold px-3 py-1 rounded-full'>✗ UNAVAILABLE</span>
                )}
              </div>
              <div className='flex gap-2'>
                <button
                  onClick={() => setWishlisted(!wishlisted)}
                  className={`w-8 h-8 rounded-full flex items-center justify-center transition ${wishlisted ? 'bg-red-50 text-red-400' : 'bg-gray-100 text-gray-400 hover:text-red-400'}`}
                >
                  {wishlisted ? <HiHeart size={16} /> : <HiOutlineHeart size={16} />}
                </button>
                <button
                  onClick={handleShare}
                  className='w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-gray-400 hover:text-[#6f4e37] transition'
                >
                  {copied ? <span className='text-[10px] font-bold text-green-500'>✓</span> : <FaShareAlt size={12} />}
                </button>
              </div>
            </div>
          </div>

          {/* Product Info */}
          <div className='flex flex-col flex-1'>
            <p className='text-[#C4A882] text-xs font-semibold tracking-widest uppercase mb-1'>{product.category_name}</p>
            <h1 className='text-[#2C1503] text-3xl font-bold mb-2'>{product.name}</h1>

            {/* Rating Summary */}
            <div className='flex items-center gap-3 mb-4'>
              <div className='flex gap-0.5'>
                {[1,2,3,4,5].map(star => (
                  star <= Math.floor(product.average_rating || 0)
                    ? <FaStar key={star} size={14} className='text-amber-400' />
                    : <FaRegStar key={star} size={14} className='text-gray-300' />
                ))}
              </div>
              <span className='text-gray-500 text-xs font-semibold'>
                {product.average_rating ? parseFloat(product.average_rating).toFixed(1) : '—'}
              </span>
              <span className='text-gray-300 text-xs'>·</span>
              <button
                onClick={() => setActiveTab('reviews')}
                className='text-[#6f4e37] text-xs font-semibold hover:underline'
              >
                {product.rating_count} review{product.rating_count !== 1 ? 's' : ''}
              </button>
            </div>

            {/* Description */}
            <p className='text-gray-500 text-sm leading-relaxed mb-6'>{product.description}</p>

            {/* Variants */}
            {product.variants?.length > 0 && (
              <div className='mb-5'>
                <p className='text-[#2C1503] text-xs font-semibold uppercase tracking-wide mb-2'>Size</p>
                <div className='flex gap-2 flex-wrap'>
                  {product.variants.map(variant => (
                    <button
                      key={variant.id}
                      onClick={() => setSelectedVariant(variant)}
                      className={`px-4 py-2 rounded-xl border text-sm font-semibold capitalize transition
                        ${selectedVariant?.id === variant.id
                          ? 'bg-[#3D1F00] text-white border-[#3D1F00] shadow-md'
                          : 'bg-white text-[#2C1503] border-gray-200 hover:border-[#3D1F00]'
                        }`}
                    >
                      {variant.size}
                      {parseFloat(variant.additional_price) > 0 && (
                        <span className='text-xs ml-1 opacity-70'>+₱{parseFloat(variant.additional_price).toFixed(2)}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Quantity */}
            <div className='mb-5'>
              <p className='text-[#2C1503] text-xs font-semibold uppercase tracking-wide mb-2'>Quantity</p>
              <div className='flex items-center gap-3'>
                <button
                  onClick={() => setQuantity(q => Math.max(1, q - 1))}
                  className='w-9 h-9 rounded-xl border border-gray-200 text-[#2C1503] font-bold hover:bg-gray-100 transition flex items-center justify-center'
                >
                  −
                </button>
                <span className='text-[#2C1503] font-bold text-lg w-8 text-center'>{quantity}</span>
                <button
                  onClick={() => setQuantity(q => q + 1)}
                  className='w-9 h-9 rounded-xl border border-gray-200 text-[#2C1503] font-bold hover:bg-gray-100 transition flex items-center justify-center'
                >
                  +
                </button>
              </div>
            </div>

            {/* Price */}
            <div className='mb-6 flex items-end gap-3'>
              <div>
                <p className='text-[#2C1503] text-3xl font-bold'>
                  <sup className='text-lg'>₱</sup>{(getPrice() * quantity).toFixed(2)}
                </p>
                {quantity > 1 && (
                  <p className='text-gray-400 text-xs mt-0.5'>₱{getPrice().toFixed(2)} each</p>
                )}
              </div>
              {product.is_featured && (
                <span className='text-green-600 text-xs font-semibold bg-green-50 px-2 py-1 rounded-lg mb-1'>
                  Best Seller
                </span>
              )}
            </div>

            {/* Buttons */}
            <div className='flex gap-3'>
              <button
                onClick={handleAddToCart}
                disabled={addingToCart || !product.is_available}
                className={`flex items-center justify-center gap-2 border text-sm font-bold px-6 py-3 rounded-xl transition flex-1
                  ${cartSuccess
                    ? 'border-green-400 text-green-600 bg-green-50'
                    : 'border-gray-300 text-[#2C1503] hover:bg-gray-100'
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <HiOutlineShoppingCart size={18} />
                {addingToCart ? 'Adding...' : cartSuccess ? '✓ Added!' : 'Add to Cart'}
              </button>
              <button
                onClick={handleBuyNow}
                disabled={!product.is_available}
                className='flex items-center justify-center gap-2 bg-[#2C1503] hover:bg-[#5a2f00] text-white text-sm font-bold px-6 py-3 rounded-xl transition flex-1 disabled:opacity-50 disabled:cursor-not-allowed'
              >
                <BsFillLightningFill size={14} /> Buy Now
              </button>
            </div>

            {/* Share Copied Toast */}
            {copied && (
              <p className='text-green-600 text-xs mt-2 flex items-center gap-1'>
                ✓ Link copied to clipboard!
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Tabs — Reviews / Details */}
      <div className='max-w-5xl mx-auto w-full px-6 pb-10'>

        {/* Tab Header */}
        <div className='flex gap-4 border-b border-gray-200 mb-6'>
          {['reviews', 'details'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-sm font-semibold capitalize transition border-b-2 -mb-px
                ${activeTab === tab
                  ? 'border-[#3D1F00] text-[#2C1503]'
                  : 'border-transparent text-gray-400 hover:text-gray-600'
                }`}
            >
              {tab === 'reviews' ? `Reviews (${reviews.length})` : 'Product Details'}
            </button>
          ))}
        </div>

        {/* Reviews Tab */}
        {activeTab === 'reviews' && (
          <>
            {/* Rating Breakdown */}
            {reviews.length > 0 && (
              <div className='bg-white rounded-2xl p-6 shadow-sm mb-6 flex flex-col sm:flex-row gap-6'>
                {/* Overall */}
                <div className='flex flex-col items-center justify-center shrink-0 w-32'>
                  <p className='text-[#2C1503] text-5xl font-bold'>{parseFloat(product.average_rating).toFixed(1)}</p>
                  <div className='flex gap-0.5 my-1'>
                    {[1,2,3,4,5].map(star => (
                      star <= Math.round(product.average_rating)
                        ? <FaStar key={star} size={12} className='text-amber-400' />
                        : <FaRegStar key={star} size={12} className='text-gray-300' />
                    ))}
                  </div>
                  <p className='text-gray-400 text-xs'>{reviews.length} reviews</p>
                </div>

                {/* Breakdown Bars */}
                <div className='flex flex-col gap-2 flex-1'>
                  {ratingBreakdown.map(({ star, count, pct }) => (
                    <div key={star} className='flex items-center gap-3'>
                      <span className='text-xs text-gray-500 w-4 text-right'>{star}</span>
                      <FaStar size={10} className='text-amber-400 shrink-0' />
                      <div className='flex-1 h-2 bg-gray-100 rounded-full overflow-hidden'>
                        <div
                          className='h-full bg-amber-400 rounded-full transition-all duration-500'
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className='text-xs text-gray-400 w-8 text-right'>{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Write a Review */}
            <div className='bg-white rounded-2xl p-6 shadow-sm mb-6'>
              <h3 className='text-[#2C1503] font-semibold text-sm mb-4'>Write a Review</h3>
              <div className='flex gap-1 mb-4'>
                {[1,2,3,4,5].map(star => (
                  <button
                    key={star}
                    onMouseEnter={() => setHoverRating(star)}
                    onMouseLeave={() => setHoverRating(0)}
                    onClick={() => setUserRating(star)}
                    className='transition-transform hover:scale-110'
                  >
                    {star <= (hoverRating || userRating)
                      ? <FaStar size={24} className='text-amber-400' />
                      : <FaRegStar size={24} className='text-gray-300' />
                    }
                  </button>
                ))}
                {userRating > 0 && (
                  <span className='text-gray-400 text-xs ml-2 self-center'>{RATING_LABELS[userRating]}</span>
                )}
              </div>
              <textarea
                placeholder='Share your experience with this product...'
                value={reviewText}
                onChange={e => setReviewText(e.target.value)}
                rows={3}
                className='w-full border border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-600 outline-none focus:border-[#C4A882] transition bg-[#FAF6F0] resize-none mb-3'
              />
              {reviewError   && <p className='text-red-500 text-xs mb-3'>{reviewError}</p>}
              {reviewSuccess && <p className='text-green-600 text-xs mb-3'>✓ Review submitted successfully!</p>}
              <button
                onClick={handleSubmitReview}
                disabled={submitting || userRating === 0}
                className='bg-[#2C1503] hover:bg-[#5a2f00] disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-bold px-6 py-2.5 rounded-xl transition'
              >
                {submitting ? 'Submitting...' : 'Submit Review'}
              </button>
            </div>

            {/* Reviews List */}
            {loadingReviews ? (
              <div className='flex flex-col gap-3'>
                {[1,2].map(i => (
                  <div key={i} className='bg-white rounded-2xl p-5 animate-pulse'>
                    <div className='h-4 bg-gray-200 rounded w-1/4 mb-2' />
                    <div className='h-3 bg-gray-100 rounded w-full' />
                  </div>
                ))}
              </div>
            ) : reviews.length === 0 ? (
              <div className='bg-white rounded-2xl p-8 text-center shadow-sm'>
                <p className='text-3xl mb-2'>☕</p>
                <p className='text-gray-400 text-sm'>No reviews yet. Be the first to review!</p>
              </div>
            ) : (
              <div className='flex flex-col gap-3'>
                {reviews.map(review => (
                  <div key={review.id} className='bg-white rounded-2xl p-5 shadow-sm hover:shadow-md transition'>
                    <div className='flex items-start justify-between mb-2'>
                      <div className='flex items-center gap-3'>
                        <div className='w-9 h-9 rounded-full bg-[#3D1F00] flex items-center justify-center shrink-0'>
                          <span className='text-[#C4A882] text-sm font-bold'>{review.user_initial}</span>
                        </div>
                        <div>
                          <p className='text-[#2C1503] text-sm font-semibold'>{review.user_email}</p>
                          <p className='text-gray-400 text-xs'>
                            {new Date(review.created_at).toLocaleDateString('en-PH', { year: 'numeric', month: 'long', day: 'numeric' })}
                          </p>
                        </div>
                      </div>
                      <div className='flex gap-0.5'>
                        {[1,2,3,4,5].map(star => (
                          star <= review.rating
                            ? <FaStar key={star} size={12} className='text-amber-400' />
                            : <FaRegStar key={star} size={12} className='text-gray-200' />
                        ))}
                      </div>
                    </div>
                    {review.review && (
                      <p className='text-gray-500 text-sm leading-relaxed ml-12'>{review.review}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* Details Tab */}
        {activeTab === 'details' && (
          <div className='bg-white rounded-2xl p-6 shadow-sm'>
            <div className='grid grid-cols-1 sm:grid-cols-2 gap-4'>
              {[
                { label: 'Category',     value: product.category_name },
                { label: 'SKU',          value: product.sku || '—' },
                { label: 'Type',         value: product.is_seasonal ? '🍂 Seasonal' : '🔄 Regular' },
                { label: 'Availability', value: product.is_available ? '✓ In Stock' : '✗ Out of Stock' },
                { label: 'Added',        value: new Date(product.created_at).toLocaleDateString('en-PH', { year: 'numeric', month: 'long', day: 'numeric' }) },
                { label: 'Base Price',   value: `₱${parseFloat(product.price).toFixed(2)}` },
              ].map(({ label, value }) => (
                <div key={label} className='bg-[#FAF6F0] rounded-xl p-4'>
                  <p className='text-gray-400 text-xs mb-1'>{label}</p>
                  <p className='text-[#2C1503] text-sm font-semibold'>{value}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Related Products */}
      {related.length > 0 && (
        <div className='max-w-5xl mx-auto w-full px-6 pb-10'>
          <div className='flex items-center gap-4 mb-6'>
            <div className='flex-1 h-px bg-[#6f4e37]/10' />
            <p className='text-[#6f4e37] text-xs font-semibold tracking-widest uppercase'>More from {product.category_name}</p>
            <div className='flex-1 h-px bg-[#6f4e37]/10' />
          </div>
          <div className='grid grid-cols-2 sm:grid-cols-4 gap-4'>
            {related.map(p => (
              <Card
                key={p.id}
                productId={p.id}
                image={p.image || null}
                name={p.name}
                description={p.description}
                price={parseFloat(p.price)}
                rating={p.average_rating || 0}
                reviewCount={p.rating_count || 0}
                premium={p.is_featured}
              />
            ))}
          </div>
        </div>
      )}

    </div>
  )
}

export default ProductDetail