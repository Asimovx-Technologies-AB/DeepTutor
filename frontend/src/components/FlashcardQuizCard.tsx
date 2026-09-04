import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import {
  HelpCircle, CheckCircle2, AlertCircle, ChevronLeft, ChevronRight,
  Layers, Check, RotateCw, Trophy, ArrowRight, RotateCcw, BookOpen
} from 'lucide-react'

interface Option {
  id: string
  text: string
}

interface Question {
  id: string
  question_type: string
  prompt: string
  options: Option[]
  correct_option_id: string
  explanation: string
  hint?: string
  correct_feedback?: string
  incorrect_feedback?: string
}

interface QuizData {
  title?: string
  description?: string
  initial_mode?: 'flashcards' | 'quiz'
  questions: Question[]
}

interface FlashcardQuizCardProps {
  quizData: QuizData
  className?: string
}

export const FlashcardQuizCard: React.FC<FlashcardQuizCardProps> = ({ quizData, className = '' }) => {
  const questions = quizData?.questions || []
  const [mode, setMode] = useState<'flashcards' | 'quiz'>(quizData?.initial_mode || 'flashcards')
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [showHint, setShowHint] = useState(false)
  const [showResults, setShowResults] = useState(false)

  // Quiz Mode state
  const [userAnswers, setUserAnswers] = useState<Record<string, string>>({})

  if (!questions.length) return null

  const currentQ = questions[currentIndex] || questions[0]
  const totalCards = questions.length

  const handleNext = () => {
    setIsFlipped(false)
    setShowHint(false)
    if (currentIndex === totalCards - 1 && mode === 'quiz' && answeredCount === totalCards) {
      setShowResults(true)
    } else {
      setCurrentIndex((prev) => (prev + 1) % totalCards)
    }
  }

  const handlePrev = () => {
    setIsFlipped(false)
    setShowHint(false)
    setCurrentIndex((prev) => (prev - 1 + totalCards) % totalCards)
  }

  const handleSelectOption = (optionId: string) => {
    if (userAnswers[currentQ.id]) return
    const updated = { ...userAnswers, [currentQ.id]: optionId }
    setUserAnswers(updated)
    // If this was the last question answered and all questions are done, prompt results
    if (Object.keys(updated).length === totalCards && currentIndex === totalCards - 1) {
      setTimeout(() => setShowResults(true), 1200)
    }
  }

  const handleRetakeQuiz = () => {
    setUserAnswers({})
    setShowResults(false)
    setCurrentIndex(0)
    setIsFlipped(false)
  }

  const answeredCount = Object.keys(userAnswers).length
  const correctCount = Object.entries(userAnswers).filter(
    ([qId, ans]) => {
      const q = questions.find((item) => item.id === qId)
      return q && q.correct_option_id.toLowerCase() === ans.toLowerCase()
    }
  ).length

  const scorePercentage = Math.round((correctCount / totalCards) * 100)

  // Find the text of the correct option for clean Claude flashcard headline
  const correctOption = currentQ.options?.find(
    (o) => o.id.toLowerCase() === currentQ.correct_option_id.toLowerCase()
  )
  const answerHeadline = correctOption ? correctOption.text : currentQ.correct_feedback || 'Correct Answer'

  return (
    <div className={`my-4 p-5 sm:p-6 rounded-2xl bg-white border border-[#E5E3DA] shadow-xs text-[#1F1E1D] font-serif max-w-2xl mx-auto w-full transition-all ${className}`}>
      {/* ─── Header: Deck Title & Claude-style Segmented Switcher ─── */}
      <div className="flex items-center justify-between pb-4 mb-4 border-b border-[#EFECE6]">
        <div className="pr-3">
          <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#7C7A74] font-sans">
            <Layers size={13} className="text-[#996515]" />
            <span>Interactive Study Deck</span>
          </div>
          <h3 className="text-base font-bold text-[#1F1E1D] mt-0.5 truncate font-serif">
            {quizData.title || 'Review Deck'}
          </h3>
        </div>

        {/* Claude Segmented Switcher */}
        <div className="flex items-center p-1 rounded-xl bg-[#F0EFEA] border border-[#E4E1D8] font-sans text-xs shrink-0">
          <button
            onClick={() => {
              setMode('quiz')
              setIsFlipped(false)
            }}
            className={`px-3 py-1.5 rounded-lg font-medium transition cursor-pointer ${
              mode === 'quiz'
                ? 'bg-white text-[#1F1E1D] font-semibold shadow-xs'
                : 'text-[#6B6964] hover:text-[#1F1E1D]'
            }`}
          >
            Quiz
          </button>
          <button
            onClick={() => {
              setMode('flashcards')
              setShowResults(false)
              setIsFlipped(false)
            }}
            className={`px-3 py-1.5 rounded-lg font-medium transition cursor-pointer ${
              mode === 'flashcards'
                ? 'bg-white text-[#1F1E1D] font-semibold shadow-xs'
                : 'text-[#6B6964] hover:text-[#1F1E1D]'
            }`}
          >
            Flashcards
          </button>
        </div>
      </div>

      {/* ─── FLASHCARD MODE (Exact Claude Minimalist View) ─── */}
      {mode === 'flashcards' && (
        <div className="space-y-3">
          <div
            onClick={() => setIsFlipped(!isFlipped)}
            className="min-h-[270px] p-6 sm:p-8 rounded-2xl bg-[#FAF9F5] border border-[#ECE9DF] flex flex-col justify-between cursor-pointer transition-all hover:border-[#D5D1C5] select-none"
          >
            {/* Top Bar: Card counter & Hint button */}
            <div className="flex items-center justify-between text-xs text-[#8C8980] font-sans">
              <span className="font-medium">Card {currentIndex + 1} of {totalCards}</span>
              {currentQ.hint && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setShowHint(!showHint)
                  }}
                  className="flex items-center gap-1 text-xs text-[#996515] font-medium hover:text-[#7D5210] bg-[#F5EFE6] px-2.5 py-1 rounded-full border border-[#E6DACB] transition cursor-pointer"
                >
                  <HelpCircle size={13} /> {showHint ? 'Hide Hint' : 'Hint'}
                </button>
              )}
            </div>

            {/* Optional Hint Dropdown */}
            {showHint && currentQ.hint && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="my-2 p-3 rounded-xl bg-[#FBF7EE] border border-[#E8DFC8] text-xs text-[#6E4F18] font-serif leading-relaxed"
                onClick={(e) => e.stopPropagation()}
              >
                <strong>Hint:</strong> {currentQ.hint}
              </motion.div>
            )}

            {/* Center Area: Front Prompt OR Claude Back Answer Display */}
            <div className="my-auto py-5 px-2">
              <AnimatePresence mode="wait">
                {!isFlipped ? (
                  /* FRONT: Question Prompt */
                  <motion.div
                    key="front"
                    initial={{ opacity: 0, y: 3 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -3 }}
                    transition={{ duration: 0.15 }}
                    className="text-center"
                  >
                    <h4 className="text-lg sm:text-xl font-bold text-[#1F1E1D] leading-snug font-serif max-w-xl mx-auto">
                      {currentQ.prompt}
                    </h4>
                  </motion.div>
                ) : (
                  /* BACK: Claude-style Bold Answer Headline + Explanation Paragraph */
                  <motion.div
                    key="back"
                    initial={{ opacity: 0, y: 3 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -3 }}
                    transition={{ duration: 0.15 }}
                    className="text-center space-y-3.5 max-w-xl mx-auto"
                  >
                    {/* Bold Answer Title (Referencing Screenshot 2) */}
                    <h4 className="text-lg sm:text-xl font-bold text-[#1F1E1D] leading-snug font-serif">
                      {answerHeadline}
                    </h4>

                    {/* Markdown / LaTeX Explanation */}
                    {currentQ.explanation && (
                      <div className="markdown-content text-sm sm:text-[15px] text-[#4A4843] leading-relaxed font-serif text-center pt-1">
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                          {currentQ.explanation}
                        </ReactMarkdown>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Bottom Flip Link (Exact Claude Minimal Style: "View question" / "View answer") */}
            <div className="pt-2 text-center">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  setIsFlipped(!isFlipped)
                }}
                className="text-xs text-[#7C7A74] hover:text-[#1F1E1D] font-medium transition cursor-pointer underline-offset-4 hover:underline font-sans"
              >
                {isFlipped ? 'View question' : 'View answer'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── QUIZ RESULTS VIEW (Claude-Style Clean Summary) ─── */}
      {mode === 'quiz' && showResults && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-5"
        >
          {/* Summary Banner */}
          <div className="p-6 rounded-2xl bg-[#FAF9F5] border border-[#ECE9DF] text-center space-y-3">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold font-sans">
              {scorePercentage >= 80 ? (
                <span className="bg-[#EDF7EE] text-[#1B4D25] border border-[#86C995] px-3 py-1 rounded-full">
                  Mastery Achieved
                </span>
              ) : scorePercentage >= 50 ? (
                <span className="bg-[#FDF6E9] text-[#6E4F18] border border-[#EBD5A2] px-3 py-1 rounded-full">
                  Good Progress
                </span>
              ) : (
                <span className="bg-[#F0EFEA] text-[#4A4843] border border-[#DCD9CE] px-3 py-1 rounded-full">
                  Review Recommended
                </span>
              )}
            </div>

            <div className="space-y-1">
              <div className="text-3xl font-bold font-serif text-[#1F1E1D]">
                {correctCount} / {totalCards}
              </div>
              <div className="text-xs text-[#7C7A74] font-sans">
                {scorePercentage}% accuracy across {totalCards} questions
              </div>
            </div>

            <p className="text-xs sm:text-sm text-[#4A4843] font-serif max-w-md mx-auto leading-relaxed">
              {scorePercentage === 100
                ? "Flawless score! You have thoroughly mastered all key concepts in this deck."
                : scorePercentage >= 70
                ? "Solid understanding of the fundamental principles. Review any missed concepts below."
                : "Great practice effort! Review the detailed explanations below to strengthen key theoretical areas."}
            </p>

            {/* Quick Action Buttons */}
            <div className="flex items-center justify-center gap-2 pt-2 font-sans text-xs">
              <button
                onClick={handleRetakeQuiz}
                className="py-2 px-4 rounded-xl border border-[#DCD9CE] bg-white hover:bg-[#FAF9F5] text-[#1F1E1D] font-semibold transition cursor-pointer flex items-center gap-1.5 shadow-xs"
              >
                <RotateCcw size={13} /> Retake Quiz
              </button>
              <button
                onClick={() => {
                  setMode('flashcards')
                  setShowResults(false)
                  setCurrentIndex(0)
                }}
                className="py-2 px-4 rounded-xl bg-[#1F1E1D] hover:bg-[#343330] text-white font-semibold transition cursor-pointer flex items-center gap-1.5 shadow-xs"
              >
                <BookOpen size={13} /> Study in Flashcards
              </button>
            </div>
          </div>

          {/* Question-by-Question Detailed Breakdown */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#7C7A74] font-sans px-1">
              Question Breakdown
            </h4>

            <div className="space-y-2.5">
              {questions.map((q, idx) => {
                const userAns = userAnswers[q.id]
                const isCorrect = userAns && userAns.toLowerCase() === q.correct_option_id.toLowerCase()
                const correctOptionObj = q.options?.find(o => o.id.toLowerCase() === q.correct_option_id.toLowerCase())
                const userOptionObj = q.options?.find(o => o.id.toLowerCase() === userAns?.toLowerCase())

                return (
                  <div
                    key={q.id}
                    onClick={() => {
                      setShowResults(false)
                      setCurrentIndex(idx)
                    }}
                    className={`p-4 rounded-xl border transition cursor-pointer text-left ${
                      isCorrect
                        ? 'bg-white hover:bg-[#FAF9F5] border-[#E5E3DA]'
                        : 'bg-[#FDFBF7] hover:bg-[#FAF6ED] border-[#EBD5A2]'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2.5">
                        <span className={`w-5 h-5 rounded-full text-[11px] font-mono font-bold flex items-center justify-center shrink-0 mt-0.5 ${
                          isCorrect
                            ? 'bg-[#EDF7EE] text-[#1B4D25]'
                            : 'bg-[#FDF0EE] text-[#7D2218]'
                        }`}>
                          {idx + 1}
                        </span>
                        <div>
                          <p className="text-xs sm:text-sm font-semibold text-[#1F1E1D] font-serif leading-snug">
                            {q.prompt}
                          </p>
                          <div className="mt-1.5 text-xs font-sans flex flex-wrap items-center gap-2">
                            {isCorrect ? (
                              <span className="text-[#2E7D32] flex items-center gap-1 font-medium">
                                <CheckCircle2 size={13} /> {correctOptionObj?.text || `Option ${q.correct_option_id.toUpperCase()}`}
                              </span>
                            ) : (
                              <>
                                <span className="text-[#C62828] line-through opacity-80">
                                  {userOptionObj?.text || `Option ${userAns?.toUpperCase() || 'Skipped'}`}
                                </span>
                                <span className="text-[#2E7D32] font-semibold flex items-center gap-1">
                                  <ArrowRight size={11} /> {correctOptionObj?.text || `Option ${q.correct_option_id.toUpperCase()}`}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <span className="text-[11px] text-[#7C7A74] hover:text-[#1F1E1D] font-medium font-sans shrink-0">
                        Review &rarr;
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </motion.div>
      )}

      {/* ─── QUIZ MODE (Individual Question View) ─── */}
      {mode === 'quiz' && !showResults && (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-[#8C8980] font-sans mb-1">
            <span className="font-medium">Question {currentIndex + 1} of {totalCards}</span>
            <div className="flex items-center gap-2">
              {answeredCount > 0 && (
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#F0EFEA] text-[#4A4843]">
                  Score: {correctCount} / {answeredCount}
                </span>
              )}
              {answeredCount === totalCards && (
                <button
                  onClick={() => setShowResults(true)}
                  className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-[#1F1E1D] text-white hover:bg-[#343330] transition cursor-pointer"
                >
                  View Summary
                </button>
              )}
            </div>
          </div>

          {/* Question Prompt */}
          <h4 className="text-base sm:text-lg font-bold text-[#1F1E1D] leading-snug font-serif">
            {currentQ.prompt}
          </h4>

          {/* Options */}
          <div className="space-y-2.5 pt-1">
            {currentQ.options?.map((opt) => {
              const selectedOption = userAnswers[currentQ.id]
              const isSelected = selectedOption === opt.id
              const isCorrectOpt = opt.id.toLowerCase() === currentQ.correct_option_id.toLowerCase()

              let buttonStyle = 'bg-white hover:bg-[#FAF9F5] border-[#E5E3DA] text-[#1F1E1D]'

              if (selectedOption) {
                if (isCorrectOpt) {
                  buttonStyle = 'bg-[#EDF7EE] border-[#86C995] text-[#1B4D25] font-semibold'
                } else if (isSelected) {
                  buttonStyle = 'bg-[#FDF0EE] border-[#E89E94] text-[#7D2218] font-semibold'
                } else {
                  buttonStyle = 'bg-[#F8F7F3] border-[#ECE9DF] text-[#8C8980] opacity-60'
                }
              }

              return (
                <button
                  key={opt.id}
                  onClick={() => handleSelectOption(opt.id)}
                  disabled={!!selectedOption}
                  className={`w-full p-3.5 rounded-xl border text-left text-xs sm:text-sm transition flex items-center justify-between cursor-pointer font-serif ${buttonStyle}`}
                >
                  <div className="flex items-center gap-3">
                    <span className={`w-6 h-6 rounded-full border text-xs font-mono font-medium flex items-center justify-center shrink-0 ${
                      isSelected && isCorrectOpt
                        ? 'bg-[#2E7D32] text-white border-[#2E7D32]'
                        : isSelected
                        ? 'bg-[#C62828] text-white border-[#C62828]'
                        : isCorrectOpt && selectedOption
                        ? 'bg-[#2E7D32] text-white border-[#2E7D32]'
                        : 'bg-[#F0EFEA] text-[#4A4843] border-[#DCD9CE]'
                    }`}>
                      {opt.id.toUpperCase()}
                    </span>
                    <span className="leading-normal">{opt.text}</span>
                  </div>

                  {selectedOption && isCorrectOpt && (
                    <CheckCircle2 size={16} className="text-[#2E7D32] shrink-0 ml-2" />
                  )}
                  {selectedOption && isSelected && !isCorrectOpt && (
                    <AlertCircle size={16} className="text-[#C62828] shrink-0 ml-2" />
                  )}
                </button>
              )
            })}
          </div>

          {/* Explanation Callout in Quiz Mode */}
          {userAnswers[currentQ.id] && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className={`p-4 rounded-xl border text-xs leading-relaxed font-serif ${
                userAnswers[currentQ.id].toLowerCase() === currentQ.correct_option_id.toLowerCase()
                  ? 'bg-[#EDF7EE] border-[#86C995] text-[#1B4D25]'
                  : 'bg-[#FDF6E9] border-[#EBD5A2] text-[#6E4F18]'
              }`}
            >
              <div className="font-sans font-bold text-xs flex items-center gap-1.5 mb-1.5">
                {userAnswers[currentQ.id].toLowerCase() === currentQ.correct_option_id.toLowerCase() ? (
                  <>
                    <CheckCircle2 size={14} className="text-[#2E7D32]" />
                    <span>{currentQ.correct_feedback || 'Correct!'}</span>
                  </>
                ) : (
                  <>
                    <AlertCircle size={14} className="text-[#B45309]" />
                    <span>{currentQ.incorrect_feedback || `Incorrect. The answer is Option ${currentQ.correct_option_id.toUpperCase()}.`}</span>
                  </>
                )}
              </div>

              <div className="markdown-content text-xs leading-relaxed font-serif pt-1">
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {currentQ.explanation}
                </ReactMarkdown>
              </div>
            </motion.div>
          )}
        </div>
      )}

      {/* ─── Bottom Stepper (Claude Clean Style) ─── */}
      {(!showResults || mode === 'flashcards') && (
        <div className="mt-5 pt-4 border-t border-[#EFECE6] flex items-center justify-between font-sans">
          <button
            onClick={handlePrev}
            className="py-1.5 px-3.5 rounded-xl border border-[#DCD9CE] bg-white hover:bg-[#FAF9F5] text-[#4A4843] text-xs font-semibold transition cursor-pointer flex items-center gap-1"
          >
            <ChevronLeft size={14} /> Previous
          </button>

          {/* Circular Number Dots */}
          <div className="flex items-center gap-1.5 overflow-x-auto max-w-[200px] sm:max-w-xs px-1 scrollbar-none">
            {questions.map((_, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setIsFlipped(false)
                  setShowHint(false)
                  setShowResults(false)
                  setCurrentIndex(idx)
                }}
                className={`w-7 h-7 rounded-full text-xs font-mono font-medium transition cursor-pointer shrink-0 ${
                  currentIndex === idx
                    ? 'bg-[#1F1E1D] text-white font-bold shadow-xs'
                    : userAnswers[questions[idx].id]
                    ? 'bg-[#E3EFE4] text-[#1B4D25] hover:bg-[#D4E8D6]'
                    : 'bg-[#F0EFEA] text-[#6B6964] hover:bg-[#E4E1D8]'
                }`}
              >
                {idx + 1}
              </button>
            ))}
          </div>

          <button
            onClick={handleNext}
            className="py-1.5 px-4 rounded-xl bg-[#1F1E1D] hover:bg-[#343330] text-white text-xs font-semibold transition cursor-pointer shadow-xs flex items-center gap-1"
          >
            {currentIndex === totalCards - 1 && mode === 'quiz' && answeredCount === totalCards
              ? 'Results'
              : 'Next'} <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  )
}

export default FlashcardQuizCard


