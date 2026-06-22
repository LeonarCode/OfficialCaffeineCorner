import React from 'react'
import Navbar from '../components/Navbar.jsx'
import { Outlet } from 'react-router-dom'
import Footer from '../components/Footer.jsx'

const PublicLayout = () => {
  return (
    <div>
      <Navbar />
      <main className='pt-18'>
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}

export default PublicLayout