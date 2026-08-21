import React from 'react'
import { motion } from 'framer-motion'

interface PageContainerProps {
  children: React.ReactNode
  className?: string
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'full'
  noPadding?: boolean
}

const maxWClasses = {
  sm: 'max-w-screen-sm',
  md: 'max-w-screen-md',
  lg: 'max-w-screen-lg',
  xl: 'max-w-screen-xl',
  '2xl': 'max-w-7xl', // Usually standard for modern dashboards
  full: 'max-w-full',
}

export default function PageContainer({ 
  children, 
  className = '', 
  maxWidth = '2xl', 
  noPadding = false 
}: PageContainerProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`w-full mx-auto ${maxWClasses[maxWidth]} ${noPadding ? '' : 'px-4 sm:px-6 lg:px-8 py-8 lg:py-10'} space-y-6 sm:space-y-8 ${className}`}
    >
      {children}
    </motion.div>
  )
}
