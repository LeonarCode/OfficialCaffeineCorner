import React, { useState, useEffect } from 'react'

const TermsModal = () => {
  const [show, setShow] = useState(false)

  useEffect(() => {
    const accepted = sessionStorage.getItem('terms_accepted')
    if (!accepted) {
      setShow(true)
    }
  }, [])

  const handleAccept = () => {
    sessionStorage.setItem('terms_accepted', 'true')
    setShow(false)
  }

  if (!show) return null

  return (
    <div className='fixed inset-0 z-[100] flex items-center justify-center p-4'>
      <div className='absolute inset-0 bg-black/60 backdrop-blur-sm' style={{ animation: 'fadeIn 0.3s ease' }} />

      <div
        className='relative bg-white rounded-3xl w-full max-w-md overflow-hidden shadow-2xl max-h-[90vh] flex flex-col'
        style={{ animation: 'slideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)' }}
      >
        {/* Header */}
        <div className='bg-[#2C1503] px-6 pt-7 pb-5 flex flex-col items-center shrink-0'>
          <div className='w-14 h-14 rounded-full border-2 border-[#C4A882] flex items-center justify-center mb-3 text-2xl'>
            📋
          </div>
          <h2 className='text-white text-xl font-bold text-center'>
            Terms & <em className='text-[#C4A882] italic font-serif'>Conditions</em>
          </h2>
          <p className='text-[#C4A882]/60 text-xs tracking-widest uppercase mt-1'>Please read before ordering</p>
        </div>

        {/* Scrollable Content */}
        <div className='px-6 py-5 overflow-y-auto flex-1'>

          {/* Highlighted Delivery Notice */}
          <div className='bg-amber-50 border border-amber-200 rounded-xl p-4 mb-4'>
            <div className='flex items-start gap-2'>
              <span className='text-lg shrink-0'>🚚</span>
              <div>
                <p className='text-amber-800 text-sm font-bold mb-1'>Limited Delivery Coverage</p>
                <p className='text-amber-700 text-xs leading-relaxed'>
                  Delivery service is only available within our selected delivery zones. Orders outside these areas will not be accommodated for delivery — please choose Pick-up instead if your location is not listed.
                </p>
              </div>
            </div>
          </div>

          <div className='flex flex-col gap-4 text-sm text-gray-600'>
            <div>
              <p className='text-[#2C1503] font-semibold text-sm mb-1'>1. Delivery Zones</p>
              <p className='text-xs leading-relaxed'>
                We currently deliver only to the town zones listed at checkout. Delivery fees vary depending on the selected zone. Orders placed outside our coverage will need to be picked up at our store instead.
              </p>
            </div>

            <div>
              <p className='text-[#2C1503] font-semibold text-sm mb-1'>2. Order Confirmation</p>
              <p className='text-xs leading-relaxed'>
                Orders reaching ₱1,000 (including delivery fee) for Regular orders require a 30% downpayment to confirm. Remaining balance is collected upon delivery or pick-up.
              </p>
            </div>

            <div>
              <p className='text-[#2C1503] font-semibold text-sm mb-1'>3. Contact Verification</p>
              <p className='text-xs leading-relaxed'>
                A valid Philippine mobile number is required for every order. We may contact you to verify or confirm order details before processing.
              </p>
            </div>

            <div>
              <p className='text-[#2C1503] font-semibold text-sm mb-1'>4. Payment</p>
              <p className='text-xs leading-relaxed'>
                We accept Cash and GCash payments. Full payment (or downpayment where applicable) must be settled according to the order type selected.
              </p>
            </div>

            <div>
              <p className='text-[#2C1503] font-semibold text-sm mb-1'>5. Order Changes & Cancellations</p>
              <p className='text-xs leading-relaxed'>
                Please contact us as soon as possible for any changes to your order. Cancellations may not be accepted once preparation has started.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className='px-6 pb-6 pt-2 shrink-0 border-t border-gray-100'>
          <button
            onClick={handleAccept}
            className='w-full bg-[#C4A882] hover:bg-[#b8976e] text-[#2C1503] font-bold text-sm py-3 rounded-xl transition-all duration-200 hover:scale-[1.01]'
          >
            I Understand & Agree
          </button>
          <p className='text-gray-400 text-[10px] text-center mt-3'>
            By continuing, you agree to our terms and conditions.
          </p>
        </div>
      </div>

      <style>{`
        @keyframes fadeIn  { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(40px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }
      `}</style>
    </div>
  )
}

export default TermsModal