import { createContext, useContext, useState, useEffect } from 'react'
import { getCart } from '../services/cartService'

const AuthContext = createContext()

export const AuthProvider = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [cartCount, setCartCount] = useState(0)

  const isRiderRoute = () => window.location.pathname.startsWith('/rider')

  useEffect(() => {
    if (isRiderRoute()) {
      setLoading(false)
      return  // ← huwag mag-check ng customer auth sa rider routes
    }
    const token = localStorage.getItem('access')
    setIsAuthenticated(!!token)
    setLoading(false)
  }, [])

  useEffect(() => {
    if (isRiderRoute()) return  // ← huwag mag-fetch ng cart sa rider routes
    if (isAuthenticated) {
      fetchCartCount()
    } else {
      setCartCount(0)
    }
  }, [isAuthenticated])

  const fetchCartCount = async () => {
    if (isRiderRoute()) return  // ← safety net
    try {
      const res = await getCart()
      const total = res.data.reduce((sum, item) => sum + item.quantity, 0)
      setCartCount(total)
    } catch {
      setCartCount(0)
    }
  }

  const logout = () => {
    localStorage.removeItem('access')
    localStorage.removeItem('refresh')
    setIsAuthenticated(false)
    setCartCount(0)
  }

  return (
    <AuthContext.Provider value={{
      isAuthenticated,
      setIsAuthenticated,
      logout,
      loading,
      cartCount,
      setCartCount,
      fetchCartCount,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)