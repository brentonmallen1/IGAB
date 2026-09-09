import { useState } from 'react'
import { CheckCircle, XCircle, Loader2, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAIStatus, useTestAIConnection, useOllamaModels } from '../../api/ai'
import { useSettings, useUpdateSetting } from '../../api/settings'
import { AIModelSettings } from './AIModelSettings'
import { AIAssistantSettings } from './AIAssistantSettings'
import { AIAdvancedSettings } from './AIAdvancedSettings'
import { AIPromptSettings } from './AIPromptSettings'
import './AISettingsPanel.css'
import { Surface } from '../common/Surface'

/**
 * The AI section, in the order a person sets it up: switch it on, point it
 * at Ollama, choose models, tune the assistant, and only then the knobs
 * most households never touch. Each group has a title, because one long
 * column of rows hid the model overrides well enough that people asked
 * where they were.
 */
export function AISettingsPanel() {
  const { data: appSettings } = useSettings()
  const updateSetting = useUpdateSetting()
  const aiStatus = useAIStatus()
  const testConnection = useTestAIConnection()
  const { refetch: refetchModels } = useOllamaModels()

  const aiEnabled = appSettings?.find((s) => s.key === 'ai_enabled')?.value === 'true'
  const ollamaHost = appSettings?.find((s) => s.key === 'ollama_host')?.value ?? ''

  const [editHost, setEditHost] = useState('')
  const [editing, setEditing] = useState(false)
  const [retentionDraft, setRetentionDraft] = useState<string | null>(null)

  const retentionDays =
    appSettings?.find((s) => s.key === 'ai_activity_retention_days')?.value ?? '30'
  // Shows the server value until typed in; the draft wins until saved.
  const editRetention = retentionDraft ?? retentionDays
  const retentionValid = /^\d+$/.test(editRetention)

  async function saveRetention() {
    await updateSetting.mutateAsync({
      key: 'ai_activity_retention_days',
      value: String(parseInt(editRetention, 10)),
    })
    setRetentionDraft(null)
    toast.success('Saved')
  }

  async function toggleEnabled() {
    const newValue = aiEnabled ? 'false' : 'true'
    await updateSetting.mutateAsync({ key: 'ai_enabled', value: newValue })
    if (newValue === 'true') {
      const result = await testConnection.mutateAsync()
      if (result.available) {
        toast.success('AI connected')
        refetchModels()
      } else {
        toast.error('AI enabled but Ollama not reachable — check the host')
      }
    }
  }

  async function saveHost() {
    if (!editHost.trim()) return
    await updateSetting.mutateAsync({ key: 'ollama_host', value: editHost.trim() })
    setEditing(false)
    const result = await testConnection.mutateAsync()
    if (result.available) {
      toast.success('Connected to Ollama')
      refetchModels()
    } else {
      toast.error('Could not connect to Ollama at this host')
    }
  }

  async function handleTestConnection() {
    const result = await testConnection.mutateAsync()
    if (result.available) {
      toast.success('Connected to Ollama')
      refetchModels()
    } else {
      toast.error('Could not connect — is Ollama running?')
    }
  }

  const statusIcon = !aiEnabled ? (
    <span className="ai-panel__status ai-panel__status--disabled">Disabled</span>
  ) : aiStatus.isLoading || testConnection.isPending ? (
    <span className="ai-panel__status ai-panel__status--loading">
      <Loader2 size={12} className="spin" /> Checking…
    </span>
  ) : aiStatus.data?.available ? (
    <span className="ai-panel__status ai-panel__status--connected">
      <CheckCircle size={12} /> Connected
    </span>
  ) : (
    <span className="ai-panel__status ai-panel__status--error">
      <XCircle size={12} /> Not connected
    </span>
  )

  return (
    <Surface
      as="section"
      className="settings-section"
      id="ai"
      header={
        <>
          <span className="section-label surface__title settings-section__title--icon">
            <Zap size={16} />
            AI (Ollama)
          </span>
          {statusIcon}
        </>
      }
    >
      <div className="settings-section__body">
        <div className="settings-row">
          <div>
            <div className="settings-row__label">Enable AI features</div>
            <div className="settings-row__desc">
              Receipt scanning, category suggestions, natural-language entry, and the budget
              assistant. Everything runs on your own Ollama server.
            </div>
          </div>
          <label className="ai-panel__toggle">
            <input
              type="checkbox"
              checked={aiEnabled}
              onChange={toggleEnabled}
              disabled={updateSetting.isPending}
              aria-label="Enable AI features"
            />
            <span className="ai-panel__toggle-slider" />
          </label>
        </div>

        {aiEnabled && (
          <>
            <div className="settings-row">
              <div className="ai-panel__host">
                <label className="settings-row__label" htmlFor="ai-host">
                  Ollama host
                </label>
                {!editing ? (
                  <div className="settings-row__desc">{ollamaHost || 'http://localhost:11434'}</div>
                ) : (
                  <input
                    id="ai-host"
                    type="text"
                    className="settings-input"
                    value={editHost}
                    onChange={(e) => setEditHost(e.target.value)}
                    placeholder="http://localhost:11434"
                    autoFocus
                  />
                )}
              </div>
              {!editing ? (
                <div className="ai-panel__actions">
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={() => {
                      // Seeded when editing starts, not synced by an effect.
                      setEditHost(ollamaHost)
                      setEditing(true)
                    }}
                  >
                    Edit
                  </button>
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={handleTestConnection}
                    disabled={testConnection.isPending}
                  >
                    {testConnection.isPending ? 'Testing…' : 'Test connection'}
                  </button>
                </div>
              ) : (
                <div className="ai-panel__actions">
                  <button className="settings-btn settings-btn--primary" onClick={saveHost}>
                    Save
                  </button>
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={() => {
                      setEditing(false)
                      setEditHost(ollamaHost)
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>

            <AIModelSettings />
            <AIAssistantSettings />

            <div className="settings-subsection">
              <div className="settings-subsection__title">Activity log</div>
              <div className="settings-row">
                <div>
                  <label className="settings-row__label" htmlFor="ai-retention">
                    Keep finished entries for
                  </label>
                  <div className="settings-row__desc">
                    Scans, model calls and their stored prompts older than this are cleaned up
                    nightly. 0 keeps them forever. Transactions, receipt images and chat history are
                    never touched.
                  </div>
                </div>
                <div className="ai-panel__actions">
                  <input
                    id="ai-retention"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    className="settings-input ai-panel__retention-input"
                    value={editRetention}
                    onChange={(e) => setRetentionDraft(e.target.value)}
                  />
                  <span className="ai-panel__retention-unit">days</span>
                  <button
                    className="settings-btn settings-btn--secondary"
                    onClick={() => void saveRetention()}
                    disabled={!retentionValid || updateSetting.isPending}
                  >
                    Save
                  </button>
                </div>
              </div>
            </div>

            <AIAdvancedSettings />
            <AIPromptSettings />
          </>
        )}
      </div>
    </Surface>
  )
}
