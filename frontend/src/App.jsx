import { BrowserRouter, Routes, Route } from "react-router-dom"
// Layout
import PublicLayout from "./layout/PublicLayout.jsx"
import AuthLayout from "./layout/AuthLayout.jsx"
// Pages
import Welcome from "./pages/Welcome.jsx"
import Homepage from "./pages/Homepage.jsx"
import Signin from "./pages/auth/Signin.jsx"
import EmailSignin from "./pages/auth/EmailSignin.jsx"
import Cart from "./pages/Cart.jsx"
import Checkout from "./pages/Checkout.jsx"
import Orders from "./pages/Orders.jsx"
import ProductDetail from "./pages/ProductDetail.jsx"
import Profile from "./pages/Profile.jsx"
import DineInMenu from "./pages/DineInMenu.jsx"


const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route index element={<Welcome />} />
        <Route element={<AuthLayout />}>
          <Route path="/signin" element={<Signin />} />
          <Route path="/email-signin" element={<EmailSignin />} />
        </Route>
        <Route element={<PublicLayout />}>
          <Route path="/home" element={<Homepage />} />
          <Route path="/cart" element={<Cart />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/orders" element={<Orders />} />
          <Route path='/product/:id' element={<ProductDetail />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/menu" element={<DineInMenu />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
