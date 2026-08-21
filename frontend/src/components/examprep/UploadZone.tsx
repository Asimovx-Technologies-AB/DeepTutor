import React, { useState, useRef } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { UploadCloud, FileText, CheckCircle2, AlertCircle, X, FileQuestion } from 'lucide-react'
import { scaleIn, errorShake, checkmarkPath } from '../../utils/animations'

interface UploadZoneProps {
  label: string
  sublabel: string
  accept?: string
  icon?: 'book' | 'pyq'
  selectedFile: File | null
  onFileSelect: (file: File | null) => void
  onError?: (msg: string) => void
  className?: string
}

export default function UploadZone({
  label,
  sublabel,
  accept = '.pdf,.docx,.doc,.txt',
  icon = 'book',
  selectedFile,
  onFileSelect,
  onError,
  className = '',
}: UploadZoneProps) {
  const shouldReduceMotion = useReducedMotion()
  const [isDragging, setIsDragging] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number>(selectedFile ? 100 : 0)
  const [isShaking, setIsShaking] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const allowedExtensions = accept.split(',').map((ext) => ext.trim().toLowerCase())

  const validateAndProcessFile = (file: File) => {
    const fileExt = '.' + file.name.split('.').pop()?.toLowerCase()
    const isValidType = allowedExtensions.some((ext) => ext === fileExt || file.type.includes(ext.replace('.', '')))

    if (!isValidType) {
      setIsShaking(true)
      setTimeout(() => setIsShaking(false), 500)
      if (onError) onError(`Invalid file format "${file.name}". Please upload PDF, Word, or text files.`)
      return
    }

    // Simulate snappy realistic upload progress
    setUploadProgress(15)
    onFileSelect(file)

    const timer1 = setTimeout(() => setUploadProgress(65), 80)
    const timer2 = setTimeout(() => setUploadProgress(100), 220)
    return () => {
      clearTimeout(timer1)
      clearTimeout(timer2)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndProcessFile(e.dataTransfer.files[0])
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndProcessFile(e.target.files[0])
    }
  }

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation()
    onFileSelect(null)
    setUploadProgress(0)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <motion.div
      variants={shouldReduceMotion ? undefined : errorShake}
      animate={isShaking ? 'shake' : 'idle'}
      onClick={() => fileInputRef.current?.click()}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      whileHover={shouldReduceMotion ? undefined : { scale: 1.01 }}
      whileTap={shouldReduceMotion ? undefined : { scale: 0.99 }}
      className={`relative p-6 rounded-3xl border-2 transition-all cursor-pointer select-none overflow-hidden ${
        isDragging
          ? 'border-[#0284C7] bg-[#E0F2FE] shadow-[0_0_20px_rgba(2,132,199,0.25)]'
          : selectedFile
          ? 'border-[#10B981] bg-[#ECFDF5] shadow-2xs'
          : 'border-dashed border-[#BAE0FF] bg-[#F0F7FF] hover:border-[#0284C7] hover:bg-[#E8F4FF] shadow-2xs'
      } ${className}`}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={handleFileChange}
      />

      <div className="flex flex-col items-center text-center space-y-3">
        {/* Animated Icon Avatar */}
        <motion.div
          key={selectedFile ? 'file-selected' : 'file-empty'}
          variants={shouldReduceMotion ? undefined : scaleIn}
          initial="initial"
          animate="animate"
          className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-xs transition-colors ${
            selectedFile
              ? 'bg-[#10B981] text-white'
              : icon === 'pyq'
              ? 'bg-white text-[#F28A45]'
              : 'bg-white text-[#0284C7]'
          }`}
        >
          {selectedFile ? (
            /* Animated SVG Checkmark */
            <svg className="w-7 h-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3}>
              <motion.path
                d="M5 13l4 4L19 7"
                variants={shouldReduceMotion ? undefined : checkmarkPath}
                initial="hidden"
                animate="visible"
              />
            </svg>
          ) : icon === 'pyq' ? (
            <FileQuestion size={26} />
          ) : (
            <UploadCloud size={26} />
          )}
        </motion.div>

        {/* Text Details */}
        <div className="space-y-1 max-w-full px-2">
          <h4 className="text-sm font-bold text-[#0C4A6E] truncate">
            {selectedFile ? selectedFile.name : label}
          </h4>
          <p className="text-xs text-[#64748B] font-medium leading-tight">
            {selectedFile
              ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Uploaded & Ready`
              : isDragging
              ? 'Drop file here to upload...'
              : sublabel}
          </p>
        </div>

        {/* Animated Progress Bar on Upload */}
        {selectedFile && uploadProgress > 0 && (
          <div className="w-full max-w-xs bg-white/70 rounded-full h-1.5 overflow-hidden border border-[#A7F3D0]">
            <motion.div
              className="bg-[#10B981] h-full rounded-full"
              initial={{ width: '0%' }}
              animate={{ width: `${uploadProgress}%` }}
              transition={{ ease: 'easeInOut', duration: 0.3 }}
            />
          </div>
        )}

        {/* Remove Button if file attached */}
        {selectedFile && (
          <button
            onClick={handleRemove}
            className="text-[11px] font-bold text-[#065F46] hover:text-[#C85C52] flex items-center gap-1 transition-colors pt-1"
          >
            <X size={12} />
            <span>Remove / Replace file</span>
          </button>
        )}
      </div>
    </motion.div>
  )
}
