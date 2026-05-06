import { useRef } from 'react'

export default function FileUpload({ onFileSelect, disabled }) {
  const inputRef = useRef(null)

  const handleChange = (e) => {
    const selected = e.target.files[0]
    if (selected) {
      onFileSelect(selected)
      e.target.value = '' // Reset so same file can be re-selected
    }
  }

  return (
    <>
      <button
        onClick={() => inputRef.current?.click()}
        className="p-2.5 text-gray-400 hover:text-bank-teal hover:bg-bank-teal/10 rounded-xl transition-colors"
        title="Upload document"
        disabled={disabled}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
        </svg>
      </button>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept="image/*,.pdf"
        onChange={handleChange}
      />
    </>
  )
}
