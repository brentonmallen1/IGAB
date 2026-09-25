import { useState } from 'react'
import { Lock } from 'lucide-react'
import {
  useTags,
  useCreateTag,
  useUpdateTag,
  useDeleteTag,
  useTagNotices,
  useDismissTagNotice,
  type Tag,
} from '../../../api/tags'
import { TagChip, type TagColorSlot } from '../../common/TagChip'
import { Tooltip } from '../../common/Tooltip/Tooltip'
import { noticeOpensPicker, noticeText } from './tagNotices'
import { TagMembershipDialog } from '../../tags/TagMembershipDialog'
import { EmergencyFundPicker } from '../../emergencyFund/EmergencyFundPicker'
import './TagsPanel.css'
import { confirmAsync } from '../../../stores/confirmStore'

const COLOR_SLOTS: TagColorSlot[] = [
  'red',
  'orange',
  'yellow',
  'green',
  'teal',
  'blue',
  'purple',
  'pink',
]

interface TagsPanelProps {
  budgetId: string
}

export function TagsPanel({ budgetId }: TagsPanelProps) {
  const { data: tags, isLoading } = useTags(budgetId)
  const { data: notices = [] } = useTagNotices(budgetId)
  const dismissNotice = useDismissTagNotice(budgetId)
  const createTag = useCreateTag(budgetId)
  const updateTag = useUpdateTag(budgetId)
  const deleteTag = useDeleteTag(budgetId)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editColor, setEditColor] = useState<TagColorSlot | null>(null)

  // The tag whose checklist is open.
  const [choosing, setChoosing] = useState<Tag | null>(null)
  // The Emergency fund row and its notices open the picker instead: the fund
  // is envelopes AND accounts AND what is kept elsewhere, chosen in one place.
  const [pickingFund, setPickingFund] = useState(false)

  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState<TagColorSlot | null>(null)

  function startEdit(tag: Tag) {
    setEditingId(tag.id)
    setEditName(tag.name)
    setEditColor(tag.color_slot)
  }

  async function saveEdit() {
    if (!editingId || !editName.trim()) return
    const editing = tags?.find((t) => t.id === editingId)
    // A system tag's name is part of what it does (the server refuses a
    // rename); only its colour is the user's to change.
    await updateTag.mutateAsync(
      editing?.system_key
        ? { id: editingId, color_slot: editColor }
        : { id: editingId, name: editName.trim(), color_slot: editColor }
    )
    setEditingId(null)
  }

  function cancelEdit() {
    setEditingId(null)
  }

  async function handleDelete(id: string, name: string) {
    const ok = await confirmAsync({
      title: `Delete tag "${name}"?`,
      message: 'It will be removed from all categories and payees.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    await deleteTag.mutateAsync(id)
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    await createTag.mutateAsync({ name: newName.trim(), color_slot: newColor })
    setNewName('')
    setNewColor(null)
  }

  if (isLoading) {
    return <div className="tags-panel__empty">Loading tags...</div>
  }

  return (
    <div className="tags-panel">
      {notices.map((n) => (
        <div key={n.key} className="tags-panel__notice" role="status">
          <span>{noticeText(n.key, n.payload)}</span>
          {noticeOpensPicker(n.key) && (
            <button
              type="button"
              className="tags-panel__notice-action"
              onClick={() => setPickingFund(true)}
            >
              Choose what counts
            </button>
          )}
          <button
            type="button"
            className="tags-panel__notice-dismiss"
            onClick={() => dismissNotice.mutate(n.key)}
          >
            Got it
          </button>
        </div>
      ))}
      {tags && tags.length > 0 ? (
        <div className="tags-panel__list">
          {tags.map((tag) => (
            <div
              key={tag.id}
              className={`tags-panel__item ${editingId === tag.id ? 'tags-panel__item--editing' : ''}`}
            >
              {editingId === tag.id ? (
                <>
                  <div className="tags-panel__preview">
                    <TagChip name={editName || 'Preview'} colorSlot={editColor} />
                  </div>
                  <div className="tags-panel__edit-row">
                    {tag.system_key ? (
                      <Tooltip content="System tag — its name is fixed">
                        <span
                          className="tags-panel__locked-name"
                          aria-label={`${tag.name} — name is fixed`}
                        >
                          <Lock size={12} aria-hidden />
                          {tag.name}
                        </span>
                      </Tooltip>
                    ) : (
                      <input
                        type="text"
                        className="tags-panel__input"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Tag name"
                        autoFocus
                      />
                    )}
                    <div className="tags-panel__colors">
                      {COLOR_SLOTS.map((slot) => (
                        <button
                          key={slot}
                          type="button"
                          className={`tags-panel__color-btn tags-panel__color-btn--${slot} ${editColor === slot ? 'tags-panel__color-btn--selected' : ''}`}
                          onClick={() => setEditColor(slot)}
                          title={slot}
                        />
                      ))}
                    </div>
                    <button
                      type="button"
                      className="tags-panel__btn tags-panel__btn--primary"
                      onClick={saveEdit}
                    >
                      Save
                    </button>
                    <button type="button" className="tags-panel__btn" onClick={cancelEdit}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="tags-panel__preview">
                    <TagChip name={tag.name} colorSlot={tag.color_slot} />
                  </div>
                  {tag.hand_settable ? (
                    <button
                      type="button"
                      className="tags-panel__counts tags-panel__counts--button"
                      onClick={() =>
                        tag.system_key === 'emergency_fund'
                          ? setPickingFund(true)
                          : setChoosing(tag)
                      }
                      aria-label={`${countLabel(tag.category_count)} tagged ${tag.name} — choose`}
                    >
                      {countLabel(tag.category_count)}
                    </button>
                  ) : (
                    <span className="tags-panel__counts">{countLabel(tag.category_count)}</span>
                  )}
                  <div className="tags-panel__actions">
                    <button
                      type="button"
                      className="tags-panel__btn"
                      onClick={() => startEdit(tag)}
                    >
                      Edit
                    </button>
                    {tag.system_key ? (
                      <Tooltip content="System tag — changes how money is counted (see the ⓘ beside the section title). Colour can be changed; the name cannot.">
                        <span className="tags-panel__system">
                          <Lock size={12} aria-hidden />
                          System
                        </span>
                      </Tooltip>
                    ) : (
                      <button
                        type="button"
                        className="tags-panel__btn tags-panel__btn--danger"
                        onClick={() => handleDelete(tag.id, tag.name)}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="tags-panel__empty">No tags yet. Create one below.</div>
      )}

      {choosing && (
        <TagMembershipDialog
          budgetId={budgetId}
          tagId={choosing.id}
          tagName={choosing.name}
          onClose={() => setChoosing(null)}
        />
      )}

      {pickingFund && (
        <EmergencyFundPicker budgetId={budgetId} onClose={() => setPickingFund(false)} />
      )}

      <form className="tags-panel__add-form" onSubmit={handleAdd}>
        <input
          type="text"
          className="tags-panel__input"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New tag name…"
        />
        <div className="tags-panel__colors">
          {COLOR_SLOTS.map((slot) => (
            <button
              key={slot}
              type="button"
              className={`tags-panel__color-btn tags-panel__color-btn--${slot} ${newColor === slot ? 'tags-panel__color-btn--selected' : ''}`}
              onClick={() => setNewColor(newColor === slot ? null : slot)}
              title={slot}
            />
          ))}
        </div>
        <button
          type="submit"
          className="tags-panel__btn tags-panel__btn--primary"
          disabled={!newName.trim()}
        >
          Add
        </button>
      </form>
    </div>
  )
}

function countLabel(n: number): string {
  return `${n} categor${n === 1 ? 'y' : 'ies'}`
}
