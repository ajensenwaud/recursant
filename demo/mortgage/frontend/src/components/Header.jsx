export default function Header() {
  return (
    <header className="bg-bank-dark text-white px-6 py-4 flex items-center gap-4 shadow-lg">
      <div className="flex items-center gap-3">
        <svg className="w-8 h-8" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="32" height="32" rx="6" fill="#14B8A6"/>
          <path d="M16 6L6 12V14H26V12L16 6Z" fill="white"/>
          <rect x="8" y="15" width="3" height="9" fill="white"/>
          <rect x="14.5" y="15" width="3" height="9" fill="white"/>
          <rect x="21" y="15" width="3" height="9" fill="white"/>
          <rect x="6" y="25" width="20" height="2" fill="white"/>
        </svg>
        <div>
          <h1 className="text-xl font-bold tracking-tight">Agentic Bank</h1>
          <p className="text-xs text-gray-400">Mortgage Application Assistant</p>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <span className="inline-block w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
        <span className="text-sm text-gray-400">Powered by Recursant Mesh</span>
      </div>
    </header>
  )
}
