import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { compliance, agents } from '../api/client';

const QUESTIONNAIRE = {
  steps: [
    {
      id: 'step_1',
      title: 'AI System Type',
      question: 'What type of AI system is this?',
      options: [
        { id: 'prohibited', label: 'Prohibited AI practices', description: 'Social scoring, real-time biometric identification in public spaces, emotion recognition in workplace/education, manipulation techniques', leads_to: 'unacceptable' },
        { id: 'general_purpose', label: 'General-purpose AI system', description: 'Foundation model or general-purpose AI model', leads_to: 'step_gpai' },
        { id: 'specific_purpose', label: 'Specific-purpose AI system', description: 'AI system designed for a specific use case', leads_to: 'step_2' },
      ],
    },
    {
      id: 'step_gpai',
      title: 'General-Purpose AI Classification',
      question: 'Does this GPAI model pose systemic risk (>10^25 FLOPs training compute)?',
      options: [
        { id: 'systemic', label: 'Yes, systemic risk GPAI', leads_to: 'high' },
        { id: 'non_systemic', label: 'No, standard GPAI', leads_to: 'step_2' },
      ],
    },
    {
      id: 'step_2',
      title: 'Use Domain (Annex III)',
      question: 'In which domain is this AI system used?',
      options: [
        { id: 'biometrics', label: 'Biometrics', domain: 'biometrics', description: 'Remote biometric identification, emotion recognition, biometric categorisation', leads_to: 'high' },
        { id: 'critical_infrastructure', label: 'Critical infrastructure', domain: 'critical_infrastructure', description: 'Safety components of critical infrastructure', leads_to: 'high' },
        { id: 'education', label: 'Education and vocational training', domain: 'education', description: 'Access to education, evaluation, monitoring', leads_to: 'high' },
        { id: 'employment', label: 'Employment and workers management', domain: 'employment', description: 'Recruitment, HR decisions, performance monitoring', leads_to: 'high' },
        { id: 'essential_services', label: 'Essential private and public services', domain: 'essential_services', description: 'Creditworthiness, insurance, emergency services', leads_to: 'high' },
        { id: 'law_enforcement', label: 'Law enforcement', domain: 'law_enforcement', description: 'Risk assessment, profiling, crime analytics', leads_to: 'high' },
        { id: 'migration_border', label: 'Migration, asylum and border control', domain: 'migration_border', description: 'Document verification, risk assessment', leads_to: 'high' },
        { id: 'justice_democracy', label: 'Administration of justice and democratic processes', domain: 'justice_democracy', description: 'AI assisting judicial authorities', leads_to: 'high' },
        { id: 'general', label: 'General / Other', domain: 'general', description: 'None of the above high-risk domains', leads_to: 'step_3' },
      ],
    },
    {
      id: 'step_3',
      title: 'Transparency Obligations',
      question: 'Does this AI system have transparency obligations?',
      options: [
        { id: 'interacts_users', label: 'Yes - interacts directly with natural persons', description: 'Chatbots, virtual assistants, customer service AI', leads_to: 'limited' },
        { id: 'generates_content', label: 'Yes - generates synthetic content', description: 'Content generation, deepfakes, synthetic media', leads_to: 'limited' },
        { id: 'emotion_recognition', label: 'Yes - emotion recognition or biometric categorisation', leads_to: 'limited' },
        { id: 'no_transparency', label: 'No specific transparency obligations', leads_to: 'minimal' },
      ],
    },
  ],
  outcomes: {
    unacceptable: { risk_category: 'unacceptable', description: 'This AI system falls under prohibited AI practices (Article 5). It cannot be placed on the EU market.', color: 'red-900' },
    high: { risk_category: 'high', description: 'This AI system is classified as high-risk under the EU AI Act (Annex III). Full compliance requirements apply.', color: 'red-500' },
    limited: { risk_category: 'limited', description: 'This AI system has limited risk with transparency obligations (Article 50).', color: 'amber-500' },
    minimal: { risk_category: 'minimal', description: 'This AI system is classified as minimal risk. Voluntary codes of conduct are encouraged.', color: 'green-500' },
  },
};

export default function EUAIClassificationWizard() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState(null);
  const [currentStepId, setCurrentStepId] = useState('step_1');
  const [responses, setResponses] = useState({});
  const [selectedDomain, setSelectedDomain] = useState('general');
  const [outcome, setOutcome] = useState(null);
  const [rationale, setRationale] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [isUpdate, setIsUpdate] = useState(false);

  useEffect(() => {
    loadAgent();
  }, [agentId]);

  const loadAgent = async () => {
    try {
      const data = await agents.get(agentId);
      setAgent(data);

      // Check if already classified
      try {
        await compliance.classification.get(agentId);
        setIsUpdate(true);
      } catch { /* not classified yet */ }
    } catch (err) {
      setError(err.message);
    }
  };

  const currentStep = QUESTIONNAIRE.steps.find(s => s.id === currentStepId);
  const isOutcome = ['unacceptable', 'high', 'limited', 'minimal'].includes(currentStepId);

  const handleSelect = (option) => {
    const newResponses = { ...responses, [currentStepId]: option.id };
    setResponses(newResponses);

    if (option.domain) {
      setSelectedDomain(option.domain);
    }

    if (['unacceptable', 'high', 'limited', 'minimal'].includes(option.leads_to)) {
      setOutcome(QUESTIONNAIRE.outcomes[option.leads_to]);
      setCurrentStepId(option.leads_to);
    } else {
      setCurrentStepId(option.leads_to);
    }
  };

  const handleBack = () => {
    const stepOrder = QUESTIONNAIRE.steps.map(s => s.id);
    const history = Object.keys(responses);
    if (history.length > 0) {
      const prevStep = history[history.length - 1];
      const newResponses = { ...responses };
      delete newResponses[prevStep];
      setResponses(newResponses);
      setCurrentStepId(prevStep);
      setOutcome(null);
    }
  };

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      const data = {
        eu_risk_category: outcome.risk_category,
        use_domain: selectedDomain,
        questionnaire_responses: responses,
        classification_rationale: rationale,
        is_confirmed: true,
      };

      if (isUpdate) {
        await compliance.classification.update(agentId, data);
      } else {
        await compliance.classification.create(agentId, data);
      }

      navigate(`/compliance/${agentId}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const stepIndex = QUESTIONNAIRE.steps.findIndex(s => s.id === currentStepId);
  const totalSteps = QUESTIONNAIRE.steps.length;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <button onClick={() => navigate(`/compliance/${agentId}`)} className="text-sm text-teal-600 hover:text-teal-800 mb-1">
          &larr; Back
        </button>
        <h1 className="text-2xl font-bold text-gray-900">EU AI Act Risk Classification</h1>
        <p className="text-sm text-gray-500 mt-1">{agent?.name || 'Agent'}</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Progress */}
      {!isOutcome && (
        <div className="flex items-center gap-2">
          {QUESTIONNAIRE.steps.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 flex-1 rounded-full ${i <= stepIndex ? 'bg-teal-500' : 'bg-gray-200'}`}
            />
          ))}
        </div>
      )}

      {/* Question Step */}
      {!isOutcome && currentStep && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-1">{currentStep.title}</h2>
          <p className="text-sm text-gray-600 mb-6">{currentStep.question}</p>

          <div className="space-y-3">
            {currentStep.options.map((option) => (
              <button
                key={option.id}
                onClick={() => handleSelect(option)}
                className="w-full text-left p-4 border border-gray-200 rounded-lg hover:border-teal-500 hover:bg-teal-50 transition-colors"
              >
                <p className="font-medium text-gray-900">{option.label}</p>
                {option.description && (
                  <p className="text-sm text-gray-500 mt-1">{option.description}</p>
                )}
              </button>
            ))}
          </div>

          {Object.keys(responses).length > 0 && (
            <button
              onClick={handleBack}
              className="mt-4 text-sm text-gray-500 hover:text-gray-700"
            >
              &larr; Go back
            </button>
          )}
        </div>
      )}

      {/* Outcome */}
      {isOutcome && outcome && (
        <div className="space-y-4">
          <div className={`bg-white rounded-lg border-2 border-${outcome.color} p-6`}>
            <div className="flex items-center gap-3 mb-3">
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-bold text-white bg-${outcome.color}`}>
                {outcome.risk_category.toUpperCase()}
              </span>
              <h2 className="text-lg font-semibold text-gray-900">Classification Result</h2>
            </div>
            <p className="text-gray-600">{outcome.description}</p>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Classification Rationale (optional)
            </label>
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              rows={3}
              className="w-full border border-gray-300 rounded-md p-2 text-sm"
              placeholder="Add any notes about this classification..."
            />
          </div>

          <div className="flex items-center justify-between">
            <button
              onClick={handleBack}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              &larr; Go back
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-6 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700 disabled:opacity-50"
            >
              {submitting ? 'Saving...' : isUpdate ? 'Update Classification' : 'Confirm Classification'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
