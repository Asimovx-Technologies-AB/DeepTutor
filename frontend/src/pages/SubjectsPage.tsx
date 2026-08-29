import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ArrowRight, BookOpen, FileText, Search, Sparkles, UploadCloud } from 'lucide-react'
import { documentsApi } from '../services/api'
import { useLanguageStore } from '../stores/languageStore'

interface StudyDocument {
  id: string
  topic_id: string
  file_name: string
  file_type: string
  indexed: boolean
  index_status?: string
  index_progress?: number
  key_topics?: string[]
  detected_subject?: string
}

function displayName(fileName: string) {
  return fileName.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim()
}

export default function SubjectsPage() {
  const navigate = useNavigate()
  const { uiLanguage } = useLanguageStore()
  const [search, setSearch] = useState('')
  const { data: documents = [], isLoading } = useQuery<StudyDocument[]>({
    queryKey: ['documents'],
    queryFn: async () => (await documentsApi.list()).data,
    refetchInterval: (query) =>
      (query.state.data || []).some((doc) => doc.index_status === 'indexing' || doc.index_status === 'pending') ? 3000 : false,
  })

  const filtered = documents.filter((doc) =>
    `${doc.file_name} ${(doc.key_topics || []).join(' ')}`.toLowerCase().includes(search.toLowerCase()),
  )
  const copy = uiLanguage === 'sv'
    ? {
        eyebrow: 'Ditt studiebibliotek', title: 'Mina material',
        subtitle: 'Ladda upp ditt eget material. AI identifierar ämnet och viktiga områden automatiskt.',
        upload: 'Ladda upp material', search: 'Sök dokument eller ämne...',
        emptyTitle: 'Inget studiematerial ännu',
        emptyBody: 'Ladda upp en PDF eller andra anteckningar för att skapa ditt första AI-studierum.',
        processing: 'Bearbetar', ready: 'Redo att studera', topics: 'AI-identifierade områden', open: 'Öppna studierum',
      }
    : {
        eyebrow: 'Your study library', title: 'My Materials',
        subtitle: 'Upload your own material. AI automatically identifies its subject and key topics.',
        upload: 'Upload material', search: 'Search documents or topics...',
        emptyTitle: 'No study material yet',
        emptyBody: 'Upload a PDF, notes, or another supported file to create your first AI study workspace.',
        processing: 'Processing', ready: 'Ready to study', topics: 'AI-detected topics', open: 'Open workspace',
      }

  return (
    <div className="min-h-screen bg-[#F7F7F7] pb-12">
      <div className="bg-white border-b border-[#E2E8F0] pt-8 pb-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 sm:px-8 flex flex-col sm:flex-row sm:items-end justify-between gap-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-2xl">
            <div className="flex items-center gap-2 mb-4 text-[#4F46E5]"><Sparkles size={16} /><span className="text-xs font-black uppercase tracking-widest">{copy.eyebrow}</span></div>
            <h1 className="text-4xl sm:text-5xl font-black text-[#3C3C3C] tracking-tight">{copy.title}</h1>
            <p className="text-[#777777] text-sm sm:text-base font-medium mt-3 max-w-xl">{copy.subtitle}</p>
          </motion.div>
          <button onClick={() => navigate('/chat')} className="btn-primary px-5 py-3 rounded-2xl flex items-center justify-center gap-2 font-black"><UploadCloud size={18} /> {copy.upload}</button>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 sm:px-8 mt-8">
        {documents.length > 0 && <div className="relative max-w-md mb-7"><Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#AFAFAF]" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={copy.search} className="w-full pl-12 pr-4 py-3.5 rounded-2xl bg-white border border-[#E2E8F0] text-sm font-bold focus:outline-none focus:border-[#4F46E5]" /></div>}

        {isLoading ? <div className="py-20 text-center text-sm font-bold text-[#777777]">Loading your materials...</div> : filtered.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map((doc, index) => {
              const ready = doc.indexed || doc.index_status === 'done'
              return <motion.button key={doc.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} disabled={!ready} onClick={() => navigate(`/chat/${doc.topic_id}`)} className="text-left bg-white border border-[#E2E8F0] rounded-[2rem] p-6 shadow-sm hover:shadow-lg hover:border-[#4F46E5]/40 transition-all disabled:cursor-wait">
                <div className="flex items-start justify-between gap-3"><div className="w-14 h-14 rounded-2xl bg-[#EEF2FF] text-[#4F46E5] flex items-center justify-center"><FileText size={26} /></div><span className={`text-[10px] font-black uppercase px-2.5 py-1 rounded-full ${ready ? 'bg-[#D7FFB8] text-[#46A302]' : 'bg-amber-100 text-amber-700'}`}>{ready ? copy.ready : `${copy.processing} ${doc.index_progress || 0}%`}</span></div>
                <h2 className="font-black text-xl text-[#3C3C3C] mt-5 capitalize line-clamp-2">{displayName(doc.file_name)}</h2>
                <p className="text-[11px] text-[#777777] font-bold uppercase tracking-wide mt-1">{doc.detected_subject || 'Detecting subject'} · {doc.file_type}</p>
                <div className="mt-5 min-h-20"><p className="text-[10px] font-black uppercase tracking-wider text-[#777777] mb-2">{copy.topics}</p><div className="flex flex-wrap gap-1.5">{(doc.key_topics || []).slice(0, 5).map((topic) => <span key={topic} className="px-2.5 py-1 rounded-full bg-[#F7F7F7] border border-[#E2E8F0] text-[11px] font-bold text-[#555]">{topic}</span>)}{ready && !doc.key_topics?.length && <span className="text-xs text-[#999]">Topics are being prepared</span>}</div></div>
                <div className="border-t border-[#E2E8F0] mt-5 pt-4 flex items-center justify-between text-sm font-black text-[#4F46E5]"><span>{copy.open}</span><ArrowRight size={17} /></div>
              </motion.button>
            })}
          </div>
        ) : <div className="bg-white border border-dashed border-[#C7D2FE] rounded-[2rem] py-20 px-6 text-center"><div className="w-20 h-20 rounded-[2rem] bg-[#EEF2FF] text-[#4F46E5] flex items-center justify-center mx-auto mb-5"><BookOpen size={34} /></div><h2 className="text-2xl font-black text-[#3C3C3C]">{search ? 'No matching material' : copy.emptyTitle}</h2><p className="text-[#777777] text-sm font-medium max-w-md mx-auto mt-2">{search ? copy.search : copy.emptyBody}</p>{!search && <button onClick={() => navigate('/chat')} className="btn-primary mt-6 px-6 py-3 rounded-2xl inline-flex items-center gap-2 font-black"><UploadCloud size={18} /> {copy.upload}</button>}</div>}
      </div>
    </div>
  )
}
