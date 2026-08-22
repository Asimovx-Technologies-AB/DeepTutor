import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type UiLanguage = 'en' | 'sv'
export type AiLanguage = 'english' | 'swedish'

interface LanguageState {
  uiLanguage: UiLanguage
  aiLanguage: AiLanguage
  setUiLanguage: (lang: UiLanguage) => void
  setAiLanguage: (lang: AiLanguage) => void
}

export const useLanguageStore = create<LanguageState>()(
  persist(
    (set) => ({
      uiLanguage: 'en',
      aiLanguage: 'english',
      setUiLanguage: (uiLanguage) => set({ uiLanguage }),
      setAiLanguage: (aiLanguage) => set({ aiLanguage }),
    }),
    {
      name: 'indietutor-language-v1',
    }
  )
)
