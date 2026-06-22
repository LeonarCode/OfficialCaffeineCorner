import React from 'react'
import AuthNavbar from '../components/auth/AuthNavbar.jsx'
import { Outlet } from 'react-router-dom'

const AuthLayout = () => {
  return (
    <div>
      <AuthNavbar />
      <main>
        <Outlet />
      </main>
    </div>
  )
}

export default AuthLayout