import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Trophy,
  Layers,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ChevronRight,
  ChevronLeft,
  RotateCcw,
  Sparkles,
  Zap,
  BookOpen
} from 'lucide-react'
import { trackingApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

export interface Option {
  id: string
  text: string
}

export interface QuestionCard {
  id: string
  prompt: string
  options: Option[]
  correct_option_id: string
  explanation: string
  hint?: string
}

export interface FlashcardQuizData {
  title: string
  topic: string
  mode?: 'quiz' | 'flashcards'
  questions: QuestionCard[]
}

interface Props {
  data: FlashcardQuizData
  className?: string
}

export default function FlashcardQuizView({ data, className = '' }: Props) {
  const [mode, setMode] = useState<'quiz' | 'flashcards'>(data.mode || 'quiz')
  const [currentIdx, setCurrentIdx] = useState(0)

  // Quiz Mode State
  const [selectedOption, setSelectedOption] = useState<string | null>(null)
  const [answeredMap, setAnsweredMap] = useState<Record<string, { selected: string; isCorrect: boolean }>>({})
  const [showHint, setShowHint] = useState(false)
  const [quizFinished, setQuizFinished] = useState(false)

  // Flashcards Mode State
  const [isFlipped, setIsFlipped] = useState(false)

  const user = useAuthStore((s) => s.user)
  const studentId = user?.id || localStorage.getItem('student_id') || 'default_user'

  const questions = data.questions || []
  const totalQuestions = questions.length
  const currentQ = questions[currentIdx]

  // Running Score
  const answeredCount = Object.keys(answeredMap).length
  const correctCount = Object.values(answeredMap).filter((a) => a.isCorrect).length
  const accuracy = answeredCount > 0 ? Math.round((correctCount / answeredCount) * 100) : 0

  if (!questions || questions.length === 0) {
    return (
      <div className="p-4 rounded-2xl bg-stone-50 border border-stone-200 text-xs text-stone-500">
        No question cards available.
      </div>
    )
  }

  // Handle Option Click in Quiz Mode
  const handleSelectOption = async (optionId: string) => {
    if (selectedOption !== null || !currentQ) return

    const isCorrect = optionId === currentQ.correct_option_id
    setSelectedOption(optionId)

    setAnsweredMap((prev) => ({
      ...prev,
      [currentQ.id]: { selected: optionId, isCorrect },
    }))

    // Emit event to Tracking Agent
    try {
      await trackingApi.emitAnswerEvent({
        topic: data.topic,
        is_correct: isCorrect,
        student_id: studentId,
        question_id: currentQ.id,
        timestamp: new Date().toISOString(),
        mode: 'quiz',
      })
    } catch (err) {
      console.warn('[FlashcardQuizView] Failed to record tracking event:', err)
    }
  }

  // Handle Next Question in Quiz
  const handleNextQuestion = () => {
    if (currentIdx < totalQuestions - 1) {
      setCurrentIdx((prev) => prev + 1)
      setSelectedOption(null)
      setShowHint(false)
    } else {
      setQuizFinished(true)
    }
  }

  // Reset Quiz
  const handleRestartQuiz = () => {
    setCurrentIdx(0)
    setSelectedOption(null)
    setAnsweredMap({})
    setShowHint(false)
    setQuizFinished(false)
  }

  // Flashcard Flip Feedback
  const handleFlashcardFeedback = async (isCorrect: boolean) => {
    try {
      await trackingApi.emitAnswerEvent({
        topic: data.topic,
        is_correct: isCorrect,
        student_id: studentId,
        question_id: currentQ.id,
        timestamp: new Date().toISOString(),
        mode: 'flashcards',
      })
    } catch (err) {
      console.warn('[FlashcardQuizView] Tracking event failed:', err)
    }

    setIsFlipped(false)
    if (currentIdx < totalQuestions - 1) {
      setCurrentIdx((prev) => prev + 1)
    }
  }

  return (
    <div className={`my-4 w-full rounded-3xl border border-[#E8E4DD] bg-[#FAF8F5] shadow-sm overflow-hidden text-[#2C2A29] font-sans ${className}`}>
      {/* ─── Header: Title & Mode Switcher ─── */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-[#E8E4DD] bg-white/70 backdrop-blur-sm">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-[#4F46E5] shadow-2xs">
            {mode === 'quiz' ? <Trophy size={16} /> : <Layers size={16} />}
          </div>
          <div>
            <h4 className="text-sm font-bold text-[#1C1A17] tracking-tight">{data.title}</h4>
            <div className="flex items-center gap-2 text-[11px] text-[#78716C]">
              <span className="font-semibold text-indigo-700">{data.topic}</span>
              <span>•</span>
              <span>{totalQuestions} interactive cards</span>
            </div>
          </div>
        </div>

        {/* Mode Toggle Switcher */}
        <div className="flex items-center bg-[#EFECE6] p-1 rounded-2xl border border-[#E0DCD4]">
          <button
            type="button"
            onClick={() => {
              setMode('quiz')
              setSelectedOption(null)
            }}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              mode === 'quiz'
                ? 'bg-white text-[#1C1A17] shadow-xs'
                : 'text-[#78716C] hover:text-[#1C1A17]'
            }`}
          >
            <Trophy size={13} className={mode === 'quiz' ? 'text-[#4F46E5]' : ''} />
            <span>Quiz Mode</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('flashcards')
              setIsFlipped(false)
            }}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              mode === 'flashcards'
                ? 'bg-white text-[#1C1A17] shadow-xs'
                : 'text-[#78716C] hover:text-[#1C1A17]'
            }`}
          >
            <Layers size={13} className={mode === 'flashcards' ? 'text-[#4F46E5]' : ''} />
            <span>Flashcards</span>
          </button>
        </div>
      </div>

      {/* ─── QUIZ MODE ─── */}
      {mode === 'quiz' && (
        <div className="p-5 sm:p-6">
          {!quizFinished ? (
            <div>
              {/* Stepper Progress & Score Banner */}
              <div className="flex items-center justify-between text-xs font-semibold text-[#78716C] mb-2.5">
                <span className="uppercase tracking-wider font-mono text-[11px]">
                  Question {currentIdx + 1} of {totalQuestions}
                </span>
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100 font-bold text-[11px]">
                  <Zap size={11} />
                  Score: {correctCount}/{answeredCount} ({accuracy}%)
                </span>
              </div>

              {/* Progress Bar */}
              <div className="w-full h-1.5 rounded-full bg-[#E8E4DD] overflow-hidden mb-5">
                <motion.div
                  className="h-full bg-indigo-600 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${((currentIdx + 1) / totalQuestions) * 100}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>

              {/* Question Prompt */}
              <div className="p-4 rounded-2xl bg-white border border-[#E8E4DD] shadow-xs mb-4">
                <h3 className="text-base font-bold text-[#1C1A17] leading-snug">
                  {currentQ.prompt}
                </h3>
              </div>

              {/* Options List */}
              <div className="space-y-2.5 mb-5">
                {currentQ.options.map((opt, i) => {
                  const isSelected = selectedOption === opt.id
                  const isCorrect = opt.id === currentQ.correct_option_id
                  const isAnswered = selectedOption !== null

                  let btnStyle = 'bg-white border-[#E8E4DD] hover:border-indigo-300 hover:bg-stone-50 text-[#2C2A29]'
                  if (isAnswered) {
                    if (isCorrect) {
                      btnStyle = 'bg-emerald-50 border-emerald-500 text-emerald-950 font-bold shadow-xs'
                    } else if (isSelected) {
                      btnStyle = 'bg-rose-50 border-rose-400 text-rose-950 font-bold shadow-xs'
                    } else {
                      btnStyle = 'bg-white/60 border-stone-200 text-stone-400 opacity-60'
                    }
                  }

                  return (
                    <motion.button
                      key={opt.id}
                      type="button"
                      whileHover={!isAnswered ? { scale: 1.005 } : {}}
                      whileTap={!isAnswered ? { scale: 0.995 } : {}}
                      onClick={() => handleSelectOption(opt.id)}
                      disabled={isAnswered}
                      className={`w-full p-3.5 rounded-2xl border text-left flex items-center justify-between gap-3 transition-all cursor-pointer ${btnStyle}`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="w-6 h-6 rounded-lg bg-stone-100 border border-stone-200 text-xs font-bold flex items-center justify-center text-stone-600 shrink-0">
                          {String.fromCharCode(65 + i)}
                        </span>
                        <span className="text-sm font-medium leading-snug">{opt.text}</span>
                      </div>
                      {isAnswered && isCorrect && (
                        <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
                      )}
                      {isAnswered && isSelected && !isCorrect && (
                        <XCircle size={18} className="text-rose-600 shrink-0" />
                      )}
                    </motion.button>
                  )
                })}
              </div>

              {/* Explanation & Hint Box */}
              <AnimatePresence>
                {selectedOption !== null && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="p-4 rounded-2xl bg-indigo-50/70 border border-indigo-100 text-xs space-y-2 mb-5"
                  >
                    <div className="flex items-center gap-1.5 font-bold text-indigo-900">
                      <Sparkles size={14} className="text-indigo-600" />
                      <span>Conceptual Explanation</span>
                    </div>
                    <p className="text-indigo-950 leading-relaxed font-normal">{currentQ.explanation}</p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Hint Accordion */}
              {currentQ.hint && selectedOption === null && (
                <div className="mb-4">
                  <button
                    type="button"
                    onClick={() => setShowHint(!showHint)}
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-[#78716C] hover:text-indigo-600 transition-colors cursor-pointer"
                  >
                    <HelpCircle size={14} />
                    <span>{showHint ? 'Hide Hint' : 'Need a Hint?'}</span>
                  </button>
                  {showHint && (
                    <motion.p
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="mt-2 p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 leading-relaxed font-medium"
                    >
                      💡 {currentQ.hint}
                    </motion.p>
                  )}
                </div>
              )}

              {/* Next Button */}
              {selectedOption !== null && (
                <div className="flex justify-end pt-2">
                  <button
                    type="button"
                    onClick={handleNextQuestion}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-2xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-sm transition-all cursor-pointer"
                  >
                    <span>{currentIdx < totalQuestions - 1 ? 'Next Question' : 'Complete Quiz'}</span>
                    <ChevronRight size={14} />
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Quiz Completion Screen */
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center py-6 space-y-5"
            >
              <div className="w-16 h-16 rounded-3xl bg-indigo-100 border border-indigo-200 text-indigo-600 flex items-center justify-center mx-auto shadow-sm">
                <Trophy size={32} />
              </div>

              <div className="space-y-1">
                <h3 className="text-xl font-bold text-[#1C1A17]">Quiz Completed!</h3>
                <p className="text-xs text-[#78716C]">
                  You scored <span className="font-bold text-indigo-700">{correctCount}</span> out of {totalQuestions} ({accuracy}%)
                </p>
              </div>

              {/* Gamification Badge */}
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 font-bold text-xs">
                <Sparkles size={14} className="text-emerald-600" />
                <span>+ {correctCount * 15 + (totalQuestions - correctCount) * 5} XP Earned</span>
              </div>

              <div className="flex items-center justify-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleRestartQuiz}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-[#E8E4DD] hover:border-stone-400 text-xs font-bold text-[#2C2A29] shadow-2xs transition-colors cursor-pointer"
                >
                  <RotateCcw size={13} />
                  <span>Retake Quiz</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMode('flashcards')
                    setCurrentIdx(0)
                    setIsFlipped(false)
                  }}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-xs font-bold text-white shadow-xs transition-colors cursor-pointer"
                >
                  <Layers size={13} />
                  <span>Review as Flashcards</span>
                </button>
              </div>
            </motion.div>
          )}
        </div>
      )}

      {/* ─── FLASHCARDS MODE ─── */}
      {mode === 'flashcards' && (
        <div className="p-5 sm:p-6 space-y-5">
          {/* Card Indicator */}
          <div className="flex items-center justify-between text-xs text-[#78716C] font-mono">
            <span className="font-bold uppercase tracking-wider text-[11px]">
              Card {currentIdx + 1} of {totalQuestions}
            </span>
            <span className="text-[11px] text-[#A8A29E]">Click card to flip</span>
          </div>

          {/* Interactive Flip Card */}
          <div
            onClick={() => setIsFlipped(!isFlipped)}
            className="min-h-[220px] p-6 rounded-3xl bg-white border border-[#E8E4DD] shadow-xs cursor-pointer select-none transition-all hover:border-indigo-300 hover:shadow-sm flex flex-col justify-between"
          >
            {!isFlipped ? (
              /* Front of Card */
              <div className="space-y-4">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-bold text-[10px] uppercase tracking-wider border border-indigo-100">
                  <BookOpen size={11} />
                  <span>Question Prompt</span>
                </div>
                <h3 className="text-base sm:text-lg font-bold text-[#1C1A17] leading-relaxed">
                  {currentQ.prompt}
                </h3>
                <p className="text-xs text-indigo-600 font-semibold pt-2">
                  🔄 Tap to reveal answer and explanation
                </p>
              </div>
            ) : (
              /* Back of Card */
              <div className="space-y-3">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 font-bold text-[10px] uppercase tracking-wider border border-emerald-200">
                  <CheckCircle2 size={11} />
                  <span>Correct Answer</span>
                </div>
                <p className="text-sm sm:text-base font-bold text-emerald-950">
                  {currentQ.options.find((o) => o.id === currentQ.correct_option_id)?.text || currentQ.correct_option_id}
                </p>
                <div className="p-3 rounded-xl bg-stone-50 border border-stone-200 text-xs text-stone-700 leading-relaxed">
                  <span className="font-bold text-stone-900 block mb-0.5">Explanation:</span>
                  {currentQ.explanation}
                </div>
              </div>
            )}

            <div className="pt-4 border-t border-stone-100 flex items-center justify-between text-[11px] text-stone-400 font-medium">
              <span>{isFlipped ? 'Showing Answer' : 'Showing Prompt'}</span>
              <span>{data.topic}</span>
            </div>
          </div>

          {/* Flashcard Review Controls */}
          {isFlipped ? (
            <div className="flex items-center justify-center gap-3 pt-1">
              <button
                type="button"
                onClick={() => handleFlashcardFeedback(false)}
                className="px-4 py-2 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <XCircle size={14} />
                <span>Need Practice</span>
              </button>
              <button
                type="button"
                onClick={() => handleFlashcardFeedback(true)}
                className="px-4 py-2 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <CheckCircle2 size={14} />
                <span>Mastered It</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between pt-1">
              <button
                type="button"
                onClick={() => {
                  if (currentIdx > 0) {
                    setCurrentIdx((prev) => prev - 1)
                    setIsFlipped(false)
                  }
                }}
                disabled={currentIdx === 0}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-[#E8E4DD] bg-white text-xs font-bold text-[#78716C] hover:text-[#1C1A17] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronLeft size={14} />
                <span>Previous</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  if (currentIdx < totalQuestions - 1) {
                    setCurrentIdx((prev) => prev + 1)
                    setIsFlipped(false)
                  }
                }}
                disabled={currentIdx === totalQuestions - 1}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-[#E8E4DD] bg-white text-xs font-bold text-[#78716C] hover:text-[#1C1A17] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <span>Next Card</span>
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
