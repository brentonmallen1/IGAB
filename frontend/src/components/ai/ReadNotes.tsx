import { Info } from 'lucide-react'
import type { AIJobRead } from '../../api/aiJobs'
import { readNotes } from './draftNotes'
import './ReadNotes.css'

/** What differed from the default in how this read was made — a retry, the
 *  thinking fallback, a Thinking setting that isn't Auto — as quiet pills.
 *  Renders nothing for an ordinary read, so the usual case stays clean. */
export function ReadNotes({ read }: { read: AIJobRead | undefined }) {
  const notes = readNotes(read)
  if (notes.length === 0) return null
  return (
    <ul className="read-notes" aria-label="How this was read">
      {notes.map((note) => (
        <li key={note} className="read-notes__pill">
          <Info size={11} aria-hidden="true" />
          {note}
        </li>
      ))}
    </ul>
  )
}
