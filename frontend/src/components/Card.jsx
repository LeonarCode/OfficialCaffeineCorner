import React, { useState } from 'react'
import { HiOutlineShoppingCart } from 'react-icons/hi'
import { BsFillLightningFill } from 'react-icons/bs'
import { FaStar, FaRegStar } from 'react-icons/fa'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { addToCart } from '../services/cartService'
import { Link } from 'react-router-dom'

const Card = ({ image, name, description, price, rating = 0, reviewCount = 0, premium = false, productId }) => {
  const [hovered, setHovered] = useState(false)
  const [addingToCart, setAddingToCart] = useState(false)
  const [cartSuccess, setCartSuccess] = useState(false)
  const { isAuthenticated, fetchCartCount } = useAuth()
  const navigate = useNavigate()

  const handleAddToCart = async () => {
    if (!isAuthenticated) { navigate('/signin'); return }
    setAddingToCart(true)
    try {
      await addToCart({ product: productId, quantity: 1 })
      setCartSuccess(true)
      fetchCartCount()  // ← dagdag
      setTimeout(() => setCartSuccess(false), 2000)
    } catch (err) {
      console.error('Failed to add to cart', err)
    } finally {
      setAddingToCart(false)
    }
  }

  const handleBuyNow = () => {
    if (!isAuthenticated) {
      navigate('/signin')
      return
    }
    navigate('/checkout', {
      state: {
        product: productId,
        name: name,
        image: image,
        price: price,
        quantity: 1,
      }
    })
  }

  return (
    <div className='flex flex-col bg-white rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-300'>

      {/* Product Image */}
      <Link to={`/product/${productId}`}>
        <div
          className='relative w-full h-44 overflow-hidden cursor-pointer'
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          {image ? (
            <img
              src={image}
              alt={name}
              className={`w-full h-full object-cover transition-transform duration-300 ${hovered ? 'scale-105 brightness-75' : 'scale-100'}`}
            />
          ) : (
            <div className='w-full h-full bg-gray-200 animate-pulse' />
          )}

          {/* Premium Badge */}
          {premium && (
            <span className='absolute top-3 left-3 bg-white text-[#3D1F00] text-xs font-bold px-3 py-1 rounded-full shadow z-10'>
              PREMIUM
            </span>
          )}

          {/* Quick View Overlay */}
          {hovered && image && (
            <div className='absolute inset-0 flex items-end justify-center pb-4 z-10'>
              <button className='bg-white/90 text-[#2C1503] text-xs font-semibold px-5 py-2 rounded-full shadow hover:bg-white transition'>
                QUICK VIEW →
              </button>
            </div>
          )}
        </div>
      </Link>

      {/* Card Body */}
      <div className='p-4 flex flex-col flex-1'>

        {/* Name */}
        <h3 className='text-[#2C1503] font-semibold text-sm mb-1'>
          {name || <div className='h-4 bg-gray-200 rounded animate-pulse w-3/4' />}
        </h3>

        {/* Description */}
        <p className='text-gray-400 text-xs leading-relaxed line-clamp-3 mb-3'>
          {description || (
            <>
              <div className='h-3 bg-gray-100 rounded animate-pulse w-full mb-1' />
              <div className='h-3 bg-gray-100 rounded animate-pulse w-5/6' />
            </>
          )}
        </p>

        {/* Star Rating */}
        <div className='flex items-center gap-1 mb-3'>
          {[1, 2, 3, 4, 5].map((star) => (
            star <= Math.floor(rating)
              ? <FaStar key={star} size={11} className='text-gray-400' />
              : <FaRegStar key={star} size={11} className='text-gray-300' />
          ))}
          {reviewCount > 0 && (
            <span className='text-gray-400 text-xs ml-1'>— {reviewCount}</span>
          )}
        </div>

        {/* Divider */}
        <hr className='border-gray-100 mb-3' />

        {/* Price */}
        <p className='text-[#2C1503] font-bold text-lg mb-3'>
          {price !== undefined ? (
            <><sup className='text-sm font-semibold'>₱</sup>{price.toFixed(2)}</>
          ) : (
            <div className='h-5 bg-gray-200 rounded animate-pulse w-1/3' />
          )}
        </p>

        {/* Buttons */}
        <div className='flex flex-row gap-2 mt-auto'>
          <button
            onClick={handleAddToCart}
            disabled={addingToCart}
            className={`flex items-center justify-center gap-1.5 border text-xs font-semibold px-4 py-2 rounded-lg transition flex-1
              ${cartSuccess
                ? 'border-green-400 text-green-600 bg-green-50'
                : 'border-gray-300 text-[#2C1503] hover:bg-gray-100'
              }`}
          >
            <HiOutlineShoppingCart size={14} />
            {addingToCart ? 'Adding...' : cartSuccess ? 'Added! ✓' : 'CART'}
          </button>
          <button
            onClick={handleBuyNow}
            className='flex items-center justify-center gap-1.5 bg-[#2C1503] text-white text-xs font-semibold px-4 py-2 rounded-lg hover:bg-[#5a2f00] transition flex-1'
          >
            <BsFillLightningFill size={11} /> BUY NOW
          </button>
        </div>

      </div>
    </div>
  )
}

export default Card