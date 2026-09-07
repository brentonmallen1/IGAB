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

/**
 * What each migration notice says.
 *
 * Out of the JSX because there are two now, and a ternary chain in a render is
 * where the third one gets written as a bare key. Falls back to the key rather
 * than rendering nothing: a notice with no copy is a bug worth seeing.
 */
function noticeText(key: string, payload: Record<string, unknown>): string {
  const removed = Number(payload.payee_tags_removed ?? 0)
  const tags = `${removed} payee tag${removed === 1 ? ' was' : 's were'} removed`
  if (key === 'subscription_tag_moved') {
    return (
      `Subscription is now a category tag. ${tags} — tag the categories your ` +
      `subscriptions are filed to (Streaming, Software…) and the report follows them.`
    )
  }
  if (key === 'payee_tags_retired') {
    return (
      `Tags now apply to categories only. ${tags} — nothing read them, so no ` +
      `figure changes. Tag the categories those payees are filed to and every ` +
      `report that uses tags follows.`
    )
  }
  return key
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
                  <span className="tags-panel__counts">
                    {tag.category_count} categor{tag.category_count === 1 ? 'y' : 'ies'}
                  </span>
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
                        <span
                          className="tags-panel__system-icon"
                          role="img"
                          aria-label="System tag"
                        >
                          <Lock size={14} />
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
