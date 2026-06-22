import React from 'react'
import logo from '../../assets/Logo.jpg'

const AuthNavbar = () => {
  return (
    <header className="bg-coffee pb-2 fixed top-0 left-0 right-0 z-50">
      <div className='flex flex-row py-3 px-6 sm:px-25 items-center justify-between'>
        <div className="flex items-center gap-3">
          <img src={logo} alt="Caffeine Corner Logo" className="h-12 w-12 rounded-full"/>
          <div>
            <p className="text-white font-bold font-montserrat tracking-widest text-sm">CAFFEINE</p>
            <p className="text-white font-bold font-montserrat tracking-widest text-sm">CORNER</p>
          </div>
        </div>
      </div>  
    </header>
  )
}

export default AuthNavbar