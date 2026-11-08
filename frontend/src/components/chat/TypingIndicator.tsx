import { motion } from 'framer-motion'
import { Bot } from 'lucide-react'
import { cn } from '../../lib/utils'

export function TypingIndicator() {
  return (
    <motion.div
      className="flex gap-3 animate-slide-up"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
    >
      <div className="w-8 flex-shrink-0 mt-1">
        <div className="w-8 h-8 rounded-full bg-oss-500/20 flex items-center justify-center">
          <Bot className="w-5 h-5 text-oss-400" />
        </div>
      </motion.div>

      <div className="flex-1">
        <div className="relative bg-dark-800 text-slate-100 rounded-2xl rounded-tr-xl rounded-bl-xl rounded-br-xl border border-dark-600 p-4">
          <div className="flex items-center gap-1.5">
            <motion.span
              className="w-2 h-2 bg-oss-500 rounded-full"
              animate={{ scale: [1, 1.2, 1], opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 0.6, repeat: Infinity, delay: 0 }}
            />
            <motion.span
              className="w-2 h-2 bg-oss-500 rounded-full"
              animate={{ scale: [1, 1.2, 1], opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 0.6, repeat: Infinity, delay: 0.15 }}
            />
            <motion.span
              className="w-2 h-2 bg-oss-500 rounded-full"
              animate={{ scale: [1, 1.2, 1], opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 0.6, repeat: Infinity, delay: 0.3 }}
            />
            <span className="text-xs text-dark-400 ml-2 font-mono">
              OS_V1 thinking...
            </span>
          </div>
        </div>
      </motion.div>
    )
  )
}

export default TypingIndicator