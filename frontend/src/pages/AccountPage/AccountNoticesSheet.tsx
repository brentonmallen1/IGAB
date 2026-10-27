import { AlertTriangle, Copy, Info } from 'lucide-react'
import { BottomSheet } from '../../components/common/BottomSheet/BottomSheet'
import type { AccountNotice, NoticeKind } from './accountNotices'
import './AccountSheets.css'

interface Props {
  open: boolean
  onClose: () => void
  notices: readonly AccountNotice[]
  onReviewDuplicates: () => void
  onViewReview: () => void
}

const ICON: Record<NoticeKind, typeof Info> = {
  duplicates: Copy,
  bank: AlertTriangle,
  review: Info,
}

/**
 * What the header's notice pill stands for, one row each with the way to
 * deal with it — the desktop's three bands (duplicates, the bank's figure,
 * rows to review) as one list.
 *
 * The bank row has no button: its sentence already says what to do, and the
 * one action it can name (fetching again) lives in Edit account, a tap away
 * in Tools.
 */
export function AccountNoticesSheet({
  open,
  onClose,
  notices,
  onReviewDuplicates,
  onViewReview,
}: Props) {
  const action: Partial<Record<NoticeKind, { label: string; run: () => void }>> = {
    duplicates: { label: 'Review', run: onReviewDuplicates },
    review: { label: 'View', run: onViewReview },
  }

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      height="auto"
      title="Needs a look"
      historyKey="account-notices"
    >
      <ul className="account-sheet account-sheet__notices">
        {/* Answered from inside the sheet, the list can empty while it is
            open; say so rather than show a blank sheet. */}
        {notices.length === 0 && <li className="account-sheet__empty">Nothing is waiting.</li>}
        {notices.map((notice) => {
          const Icon = ICON[notice.kind]
          const act = action[notice.kind]
          return (
            <li key={notice.kind} className="account-sheet__notice">
              <Icon
                size={18}
                aria-hidden="true"
                className={`account-sheet__notice-icon account-sheet__notice-icon--${notice.tone}`}
              />
              <div className="account-sheet__notice-text">
                <span className="account-sheet__notice-title">{notice.title}</span>
                <span className="account-sheet__notice-detail">{notice.detail}</span>
              </div>
              {act && (
                <button
                  type="button"
                  className="account-sheet__notice-btn"
                  onClick={() => {
                    onClose()
                    act.run()
                  }}
                >
                  {act.label}
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </BottomSheet>
  )
}
