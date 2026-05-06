const STEPS = [
  { label: 'Verify Identity', phases: ['GREETING', 'AUTHENTICATING'] },
  { label: 'Upload ID', phases: ['AWAITING_PASSPORT', 'VERIFYING_KYC'] },
  { label: 'Income', phases: ['AWAITING_PAYSLIP', 'ASSESSING_CREDIT'] },
  { label: 'Property', phases: ['PRESENTING_OFFER'] },
  { label: 'Decision', phases: ['DECIDING_CREDIT', 'COMPLIANCE_REVIEW'] },
  { label: 'Contract', phases: ['AWAITING_CONTRACT', 'DISBURSING'] },
  { label: 'Complete', phases: ['COMPLETED'] },
]

export default function PhaseIndicator({ phase }) {
  const currentStepIndex = STEPS.findIndex(step => step.phases.includes(phase))

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-100">
      {STEPS.map((step, idx) => {
        const isCompleted = idx < currentStepIndex
        const isCurrent = idx === currentStepIndex

        return (
          <div key={step.label} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-colors
                ${isCompleted
                  ? 'bg-bank-teal text-white'
                  : isCurrent
                    ? 'bg-bank-teal/20 text-bank-teal border-2 border-bank-teal'
                    : 'bg-gray-100 text-gray-400'
                }`}>
                {isCompleted ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  idx + 1
                )}
              </div>
              <span className={`text-[10px] mt-1 whitespace-nowrap
                ${isCompleted || isCurrent ? 'text-bank-teal font-medium' : 'text-gray-400'}`}>
                {step.label}
              </span>
            </div>
            {idx < STEPS.length - 1 && (
              <div className={`flex-1 h-0.5 mx-2 mt-[-12px] transition-colors
                ${isCompleted ? 'bg-bank-teal' : 'bg-gray-200'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}
