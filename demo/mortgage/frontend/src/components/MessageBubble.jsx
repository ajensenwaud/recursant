import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[75%] ${isUser ? 'order-2' : 'order-1'}`}>
        {/* Avatar + Name */}
        <div className={`flex items-center gap-2 mb-1 ${isUser ? 'flex-row-reverse' : ''}`}>
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold
            ${isUser ? 'bg-bank-accent text-white' : 'bg-bank-teal text-white'}`}>
            {isUser ? 'You' : 'AB'}
          </div>
          <span className="text-xs text-gray-500">
            {isUser ? 'You' : 'Mortgage Advisor'}
          </span>
        </div>

        {/* Message bubble */}
        <div className={`rounded-2xl px-4 py-3 shadow-sm
          ${isUser
            ? 'bg-bank-accent text-white rounded-tr-md'
            : message.isError
              ? 'bg-amber-50 text-amber-800 rounded-tl-md border border-amber-200'
              : 'bg-white text-gray-800 rounded-tl-md border border-gray-100'
          }`}>
          {isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="text-sm leading-relaxed markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
          {message.fileName && (
            <div className={`mt-2 flex items-center gap-2 text-xs
              ${isUser ? 'text-blue-200' : 'text-gray-500'}`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
              {message.fileName}
            </div>
          )}
        </div>

        {/* Streaming indicator */}
        {message.streaming && (
          <div className="flex gap-1 mt-2 ml-2">
            <span className="w-1.5 h-1.5 bg-bank-teal rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
            <span className="w-1.5 h-1.5 bg-bank-teal rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
            <span className="w-1.5 h-1.5 bg-bank-teal rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
          </div>
        )}
      </div>
    </div>
  )
}
